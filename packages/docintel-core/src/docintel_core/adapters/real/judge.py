"""Cross-family LLMJudge with provider-native structured-output deserialization.

D-04: The judge uses the OTHER provider from the generator to avoid circular-judge
bias (a model rubber-stamping its own output). Factory wiring:
  - generator = AnthropicAdapter → judge wraps OpenAIAdapter
  - generator = OpenAIAdapter    → judge wraps AnthropicAdapter

D-09 (Wave 3 migration): the Phase 2 placeholder system-prompt constant, the
inline prompt-builder helper, and the heuristic score-extraction regex have all
been retired. The canonical prompt body now lives in
``docintel_generate.prompts.JUDGE_PROMPT``; the user-prompt builder is
``docintel_generate.prompts.build_judge_user_prompt``. The heuristic parser is
replaced with provider-native structured output:
  - Anthropic: ``tools=[{"name": "submit_verdict", "input_schema": {...}}]`` +
    ``tool_choice={"type": "tool", "name": "submit_verdict"}`` binds the response
    to ``_JUDGE_VERDICT_SCHEMA``; ``response.content[*].input`` carries the dict
    that deserializes directly into ``JudgeVerdict``.
  - OpenAI: ``response_format={"type": "json_schema", "json_schema": {"strict":
    true, "schema": _JUDGE_VERDICT_SCHEMA}}`` binds the response to the same
    schema; ``response.choices[0].message.content`` is the JSON string that
    deserializes into ``JudgeVerdict``.

Tenacity wrap discipline (ADP-06 / D-18): the two raw-SDK helpers
``_judge_via_anthropic_raw`` and ``_judge_via_openai_raw`` are wrapped with the
same ``@retry`` decorator pattern used by ``llm_anthropic.py:102-108`` and
``llm_openai.py:104-110``. Retry triggers on transient HTTP errors only
(``RateLimitError``, ``APIConnectionError``, ``APITimeoutError``); deserialization
failures are NEVER retried (Pitfall 6 — they would cause a retry storm).

Sentinel-on-failure (RESEARCH Pitfall 6): the outer helpers
``_judge_via_anthropic`` / ``_judge_via_openai`` catch any deserialization or
shape error and return a sentinel ``JudgeVerdict(score=0.0, passed=False,
reasoning="<deserialization failed>", unsupported_claims=[])``. Failures emit a
``judge_structured_output_invalid`` structlog warning so Phase 9 can measure the
failure rate; they NEVER raise. This preserves the eval signal as a measurement
rather than promoting a per-call regression into a hard crash.

Phase 2 D-04 cross-family wiring (the ``CrossFamilyJudge`` class shell + the
``Settings.llm_real_provider`` complement-selection in ``make_adapters``) is
preserved untouched. Only the prompt body and the parser changed (D-09: "prompt
+ parser, NOT dispatch").
"""

from __future__ import annotations

import json
import logging
from typing import Any

import structlog
from anthropic import APIConnectionError as AnthropicAPIConnectionError
from anthropic import APITimeoutError as AnthropicAPITimeoutError
from anthropic import RateLimitError as AnthropicRateLimitError
from docintel_generate.prompts import JUDGE_PROMPT, build_judge_user_prompt
from openai import APIConnectionError as OpenAIAPIConnectionError
from openai import APITimeoutError as OpenAIAPITimeoutError
from openai import RateLimitError as OpenAIRateLimitError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from docintel_core.adapters.protocols import LLMClient
from docintel_core.adapters.types import JudgeVerdict
from docintel_core.config import Settings

# Two-logger pattern (SP-3): stdlib logger for tenacity before_sleep_log;
# structlog bound logger for all other structured log lines. Both are used now
# (the @retry decorator's before_sleep_log consumes _retry_log; the
# deserialization-failure warning consumes the structlog logger).
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)


_JUDGE_VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "passed": {"type": "boolean"},
        "reasoning": {"type": "string"},
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "passed", "reasoning", "unsupported_claims"],
}
"""Locked JSON schema for ``JudgeVerdict`` structured-output.

Both providers consume this dict:
  - Anthropic ``tools=[{"name": "submit_verdict", "input_schema": <schema>}]``
  - OpenAI ``response_format={"type": "json_schema", "json_schema": {"schema":
    <schema>}}``

``additionalProperties: false`` AND all four fields in ``required`` are
mandatory for both providers' strict mode. Field order matches
``JudgeVerdict`` (``score`` ∈ [0.0, 1.0], ``passed`` bool, ``reasoning`` str,
``unsupported_claims`` list[str]).
"""


def _sentinel_judgeverdict() -> JudgeVerdict:
    """Return the sentinel verdict on structured-output deserialization failure.

    Pitfall 6: failures are MEASUREMENTS, not retry triggers. Phase 9 eval
    pipeline counts these as zero-score judgments. The structlog warning
    ``judge_structured_output_invalid`` is the canary; if eval reports show
    consistent sentinel verdicts, investigate model behavior (not retries).
    """
    return JudgeVerdict(
        score=0.0,
        passed=False,
        reasoning="<deserialization failed>",
        unsupported_claims=[],
    )


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=20),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(
        (
            AnthropicRateLimitError,
            AnthropicAPIConnectionError,
            AnthropicAPITimeoutError,
        )
    ),
    before_sleep=before_sleep_log(_retry_log, logging.WARNING),
    reraise=True,
)
def _judge_via_anthropic_raw(client: Any, user_prompt: str) -> dict[str, Any]:
    """Raw Anthropic structured-output SDK call (D-09 + CD-09).

    Calls ``client.messages.create`` with ``tools=[{strict: true}]`` +
    ``tool_choice={"type": "tool", "name": "submit_verdict"}`` per RESEARCH
    Pattern 3 lines 532-551. Extracts the ``submit_verdict`` tool_use block's
    ``.input`` dict and returns it for deserialization upstream.

    Wrapped with the same ``@retry`` pattern as ``llm_anthropic.py:102-108``.
    Retries only on transient HTTP errors (``RateLimitError``,
    ``APIConnectionError``, ``APITimeoutError``); deserialization failures are
    handled OUTSIDE this function (in ``_judge_via_anthropic``) so they do not
    trigger retry storms (Pitfall 6).

    Args:
        client: An ``anthropic.Anthropic`` SDK client instance.
        user_prompt: The user-side prompt built by ``build_judge_user_prompt``.

    Returns:
        The ``.input`` dict from the ``submit_verdict`` tool_use block. If the
        response contains no such block, returns an empty dict so the caller
        treats it as a deserialization failure and emits the sentinel.
    """
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=JUDGE_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[
            {
                "name": "submit_verdict",
                "description": "Submit the faithfulness verdict for the prediction.",
                "input_schema": _JUDGE_VERDICT_SCHEMA,
            }
        ],
        tool_choice={"type": "tool", "name": "submit_verdict"},
    )
    # response.content is a list of blocks; the tool_use block carries .input.
    for block in response.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == "submit_verdict"
        ):
            payload = getattr(block, "input", None)
            if isinstance(payload, dict):
                return payload
    return {}


def _judge_via_anthropic(client: Any, user_prompt: str) -> JudgeVerdict:
    """Anthropic judge dispatch with sentinel-on-failure (D-09 + Pitfall 6).

    Calls ``_judge_via_anthropic_raw`` (which is ``@retry``-wrapped at the SDK
    layer) and deserializes the returned dict into ``JudgeVerdict``. On any
    deserialization or shape error, emits a ``judge_structured_output_invalid``
    structlog warning and returns the sentinel verdict — NEVER raises.

    Args:
        client: An ``anthropic.Anthropic`` SDK client instance.
        user_prompt: The user-side prompt built by ``build_judge_user_prompt``.

    Returns:
        A ``JudgeVerdict`` deserialized from the structured-output response, or
        the sentinel verdict from ``_sentinel_judgeverdict`` on failure.
    """
    try:
        payload = _judge_via_anthropic_raw(client, user_prompt)
    except (
        AnthropicRateLimitError,
        AnthropicAPIConnectionError,
        AnthropicAPITimeoutError,
    ) as exc:
        # Transient errors after the @retry decorator exhausted its budget;
        # surface as a sentinel rather than crashing the eval run.
        log.warning(
            "judge_structured_output_invalid",
            provider="anthropic",
            error=str(exc),
            error_class=type(exc).__name__,
            reason="transient_after_retries",
        )
        return _sentinel_judgeverdict()
    if not payload:
        log.warning(
            "judge_structured_output_invalid",
            provider="anthropic",
            error="missing_tool_use_block_or_empty_input",
        )
        return _sentinel_judgeverdict()
    try:
        return JudgeVerdict(**payload)
    except Exception as exc:
        log.warning(
            "judge_structured_output_invalid",
            provider="anthropic",
            error=str(exc),
            error_class=type(exc).__name__,
            payload_preview=str(payload)[:200],
        )
        return _sentinel_judgeverdict()


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=20),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(
        (
            OpenAIRateLimitError,
            OpenAIAPIConnectionError,
            OpenAIAPITimeoutError,
        )
    ),
    before_sleep=before_sleep_log(_retry_log, logging.WARNING),
    reraise=True,
)
def _judge_via_openai_raw(client: Any, user_prompt: str) -> dict[str, Any]:
    """Raw OpenAI structured-output SDK call (D-09 + CD-09).

    Calls ``client.chat.completions.create`` with ``response_format={"type":
    "json_schema", "json_schema": {"strict": true, "schema": ...}}`` per
    RESEARCH Pattern 3 lines 553-581 (the stable path; avoids ``.beta.parse()``
    instability per RESEARCH Sources tertiary issue #1733/#1763).

    Wrapped with the same ``@retry`` pattern as ``llm_openai.py:104-110``.
    Retries only on transient HTTP errors; deserialization failures are handled
    OUTSIDE this function so they do not trigger retry storms (Pitfall 6).

    Args:
        client: An ``openai.OpenAI`` SDK client instance.
        user_prompt: The user-side prompt built by ``build_judge_user_prompt``.

    Returns:
        The decoded JSON dict from ``response.choices[0].message.content``. If
        the content is missing or fails to JSON-decode, returns an empty dict
        so the caller treats it as a deserialization failure.
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=2048,
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "submit_verdict",
                "strict": True,
                "schema": _JUDGE_VERDICT_SCHEMA,
            },
        },
    )
    content = response.choices[0].message.content
    if not content:
        return {}
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return decoded


def _judge_via_openai(client: Any, user_prompt: str) -> JudgeVerdict:
    """OpenAI judge dispatch with sentinel-on-failure (D-09 + Pitfall 6).

    Calls ``_judge_via_openai_raw`` (which is ``@retry``-wrapped at the SDK
    layer) and deserializes the returned dict into ``JudgeVerdict``. On any
    deserialization or shape error, emits a ``judge_structured_output_invalid``
    structlog warning and returns the sentinel verdict — NEVER raises.

    Args:
        client: An ``openai.OpenAI`` SDK client instance.
        user_prompt: The user-side prompt built by ``build_judge_user_prompt``.

    Returns:
        A ``JudgeVerdict`` deserialized from the structured-output response, or
        the sentinel verdict from ``_sentinel_judgeverdict`` on failure.
    """
    try:
        payload = _judge_via_openai_raw(client, user_prompt)
    except (
        OpenAIRateLimitError,
        OpenAIAPIConnectionError,
        OpenAIAPITimeoutError,
    ) as exc:
        log.warning(
            "judge_structured_output_invalid",
            provider="openai",
            error=str(exc),
            error_class=type(exc).__name__,
            reason="transient_after_retries",
        )
        return _sentinel_judgeverdict()
    if not payload:
        log.warning(
            "judge_structured_output_invalid",
            provider="openai",
            error="missing_or_undecodable_response_content",
        )
        return _sentinel_judgeverdict()
    try:
        return JudgeVerdict(**payload)
    except Exception as exc:
        log.warning(
            "judge_structured_output_invalid",
            provider="openai",
            error=str(exc),
            error_class=type(exc).__name__,
            payload_preview=str(payload)[:200],
        )
        return _sentinel_judgeverdict()


class CrossFamilyJudge:
    """Real LLMJudge that delegates evaluation to the complement provider's LLMClient.

    Satisfies the LLMJudge Protocol structurally (no inheritance required).
    The 'complement' provider is the OTHER provider from the generator:
      - generator = AnthropicAdapter → complement = OpenAIAdapter
      - generator = OpenAIAdapter    → complement = AnthropicAdapter

    This avoids circular-judge bias where a model rubber-stamps its own output.
    Factory wiring is done by make_adapters() (factory.py); this class receives
    an already-constructed LLMClient as complement_llm.

    Phase 6 D-09 migration: ``.judge()`` no longer calls ``self._llm.complete()``
    with a placeholder prompt + heuristic regex parser. Instead, it dispatches
    by underlying adapter family (``AnthropicAdapter`` / ``OpenAIAdapter``) to
    the matching structured-output helper (``_judge_via_anthropic`` /
    ``_judge_via_openai``), which calls the SDK directly with provider-native
    structured-output bindings and deserializes into ``JudgeVerdict``. The class
    shell, ``__init__``, degraded-mode detection, and ``.name`` property are
    preserved untouched (Phase 2 D-04 contract).
    """

    def __init__(self, complement_llm: LLMClient, cfg: Settings) -> None:
        """Store the complement LLMClient and log initialization state.

        Degraded mode detection: if the complement key was missing at factory
        time, the factory currently raises ValueError (does not fall back).
        The detection code below is present for when a future wave adds the
        fallback path — at that point, the WARNING log becomes reachable.

        TODO: Wire the same-family fallback in factory.py (Wave 5+) so that
        CrossFamilyJudge works when only one API key is set. The WARNING log
        here will surface the degraded state in eval reports (Pitfall 5).

        Args:
            complement_llm: The LLMClient instance to use for judging (the
                            complement provider).
            cfg:            Settings instance for degraded-mode key detection.
        """
        self._llm = complement_llm

        # Degraded-mode detection (T-02-W4-01): check whether the complement
        # provider's key was actually present. Lazy local imports to avoid
        # circular imports at module top-level.
        try:
            from docintel_core.adapters.real.llm_anthropic import AnthropicAdapter
            from docintel_core.adapters.real.llm_openai import OpenAIAdapter

            degraded = (
                isinstance(complement_llm, AnthropicAdapter) and cfg.anthropic_api_key is None
            ) or (isinstance(complement_llm, OpenAIAdapter) and cfg.openai_api_key is None)
        except ImportError:
            degraded = False

        if degraded:
            # TODO: This path is currently unreachable — factory raises ValueError on
            # missing keys. Wire the fallback in factory.py (Wave 5+) to make this
            # warning reachable when only one key is present.
            log.warning(
                "cross_family_judge_degraded",
                reason="complement_provider_key_missing",
                judge_adapter=complement_llm.name,
            )

        log.info("cross_family_judge_initialized", judge_adapter=complement_llm.name)

    @property
    def name(self) -> str:
        """Adapter identifier for Phase 10 eval manifest headers."""
        return f"{self._llm.name}/judge"

    def judge(
        self,
        prediction: str,
        reference: list[str],
        rubric: str = "",
    ) -> JudgeVerdict:
        """Evaluate prediction faithfulness via the complement provider's LLM.

        Phase 6 D-09 migration: the prompt body now lives in
        ``docintel_generate.prompts.JUDGE_PROMPT``; the user-prompt builder is
        ``docintel_generate.prompts.build_judge_user_prompt``; the parser is
        provider-native structured output (Anthropic ``tools=[{strict: true}]``
        / OpenAI ``response_format={'type': 'json_schema', 'strict': true}``).
        Phase 2 D-04 cross-family wiring (the factory dispatch in
        ``make_adapters``) is preserved untouched — this method dispatches by
        adapter family at the SDK call layer, not at the protocol layer.

        Deserialization failures emit a ``judge_structured_output_invalid``
        structlog warning and return the sentinel
        ``JudgeVerdict(score=0.0, passed=False, reasoning="<deserialization
        failed>", unsupported_claims=[])`` — NEVER raise (Pitfall 6: failures
        are measurements, not retry triggers).

        Args:
            prediction: The generated answer text to evaluate.
            reference:  List of reference passage strings for grounding.
            rubric:     Optional evaluation criteria / rubric text.

        Returns:
            JudgeVerdict with score [0,1], passed flag, reasoning, and
            unsupported_claims, deserialized directly from the provider's
            structured-output response (or the sentinel on failure).
        """
        user_prompt = build_judge_user_prompt(prediction, reference, rubric)

        # Lazy imports to avoid circular core→real→core cycles at module load.
        from docintel_core.adapters.real.llm_anthropic import AnthropicAdapter
        from docintel_core.adapters.real.llm_openai import OpenAIAdapter

        if isinstance(self._llm, AnthropicAdapter):
            return _judge_via_anthropic(self._llm._get_client(), user_prompt)
        elif isinstance(self._llm, OpenAIAdapter):
            return _judge_via_openai(self._llm._get_client(), user_prompt)
        else:
            raise TypeError(
                f"unsupported judge adapter type: {type(self._llm).__name__}; "
                f"expected AnthropicAdapter or OpenAIAdapter (Phase 2 D-04 contract)"
            )
