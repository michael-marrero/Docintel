"""Real LLMClient backed by the OpenAI chat completions API (gpt-4o default).

Model: gpt-4o (default). Fallback: gpt-4.1 (both in pricing table — D-06).
API key is read from Settings.openai_api_key.get_secret_value() exactly
ONCE — in __init__, at SDK client construction. It is NEVER logged, NEVER
passed to tenacity hooks, and NEVER stored in any field other than the SDK
client object (SP-4, T-02-05 mitigation).

Every client.chat.completions.create() call is inside a tenacity @retry
decorator (ADP-06, D-18). The retry policy covers transient failures only:
RateLimitError (HTTP 429), APIConnectionError (network), APITimeoutError.
AuthenticationError and BadRequestError are NOT retried (T-02-01).

Key structural difference from llm_anthropic.py:
- System prompt is inside the messages list (role='system') NOT a top-level arg
- Usage fields: response.usage.prompt_tokens / completion_tokens (not input_/output_)
- Response text: response.choices[0].message.content (not response.content[0].text)

The openai exception classes (RateLimitError, APIConnectionError, APITimeoutError)
are imported at module top-level so they are available when Python evaluates
the @retry(...) decorator at class definition time. This is safe because this
module is only imported inside make_adapters()'s real branch.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import structlog
from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from docintel_core.adapters.types import CompletionResponse, TokenUsage
from docintel_core.config import Settings
from docintel_core.pricing import cost_for

from ._logging import before_sleep_safe

# Two-logger pattern (SP-3): stdlib logger for tenacity before_sleep_safe;
# structlog bound logger for all other structured log lines.
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)

_DEFAULT_MODEL = "gpt-4o"
# EMP-01: per-request timeout (seconds) for the OpenAI-compatible client. Bounds a
# single hung/throttled NIM call so tenacity's retry can take over instead of the
# SDK blocking on its ~10-min default.
_REQUEST_TIMEOUT_S = 60.0
# D-14: reasoning models (e.g. NIM openai/gpt-oss-120b) spend tokens on an internal
# reasoning pass before emitting the final answer. At 2048 a real corpus question
# (~1.7k-token prompt + reasoning) exhausted the budget before any citable content
# was produced → empty message.content → ANS-03 validation crash. 8192 gives the
# reasoning + answer room to complete.
_MAX_TOKENS = 8192


class OpenAIAdapter:
    """Real LLMClient adapter wrapping the OpenAI chat completions API.

    Satisfies the LLMClient Protocol structurally (no inheritance required).
    Default model: gpt-4o. The factory dispatches to this adapter when
    cfg.llm_real_provider == 'openai', or uses it as the judge complement
    when llm_real_provider == 'anthropic' (D-03, D-04).

    D-03: Both OpenAIAdapter and AnthropicAdapter ship as real adapters behind
    the same LLMClient Protocol — the 'seam is the artifact' demonstration.
    """

    def __init__(self, cfg: Settings, model: str | None = None) -> None:
        """Store cfg; defer SDK client construction to first ``.complete()`` call.

        Lazy SDK init means that downstream pipelines which build the full
        AdapterBundle but never call the LLM (``docintel-index build`` and
        ``Retriever.search`` in real-mode workflow_dispatch) can run WITHOUT
        ``DOCINTEL_OPENAI_API_KEY`` set. The API key is only required when
        ``.complete()`` is actually invoked (Phase 6 generation onward).

        SP-4 / T-02-05: ``.get_secret_value()`` is still called EXACTLY ONCE,
        but at first ``.complete()`` rather than at construction.

        D-14: the model is resolved from ``model`` arg → ``cfg.openai_model`` →
        ``_DEFAULT_MODEL``. The factory passes ``model=cfg.judge_model`` to build
        the second (judge) OpenAIAdapter so generator and judge can run distinct
        models against the same OpenAI-compatible endpoint (NIM).

        Args:
            cfg: Settings instance. ``openai_api_key`` is required only when
                ``.complete()`` is called; ``__init__`` accepts None.
            model: Explicit model override. None → ``cfg.openai_model``.
        """
        self._cfg = cfg
        self._client: Any | None = None  # lazy — see _get_client()
        self._model = model or cfg.openai_model or _DEFAULT_MODEL
        log.info("openai_adapter_initialized", model=self._model)

    def _get_client(self) -> Any:
        """Lazy SDK construction. Raises if API key is missing at first use."""
        if self._client is not None:
            return self._client
        import openai  # lazy module import — only executed when real .complete() runs

        if self._cfg.openai_api_key is None:
            raise ValueError("DOCINTEL_OPENAI_API_KEY is required when llm_provider='real'")
        # SP-4: the ONLY call to .get_secret_value() in this file.
        # D-14: base_url=None lets the SDK use its default (api.openai.com); a set
        # value points the adapter at an OpenAI-compatible gateway (e.g. NIM).
        self._client = openai.OpenAI(
            api_key=self._cfg.openai_api_key.get_secret_value(),
            base_url=self._cfg.openai_base_url,
            # EMP-01: bound each call so a throttled NIM response fails fast (60s)
            # instead of blocking on the SDK's ~10-min default — a hung judge call
            # ate the whole 80-min eval budget (run 29041979127). max_retries=0 so
            # tenacity is the SOLE, logged retry authority (AD-4: no silent retries).
            timeout=_REQUEST_TIMEOUT_S,
            max_retries=0,
        )
        return self._client

    @property
    def name(self) -> str:
        """Adapter identifier for Phase 10 eval manifest headers."""
        return self._model

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError)),
        before_sleep=before_sleep_safe(_retry_log, logging.WARNING),
        reraise=True,
    )
    def complete(
        self,
        prompt: str,
        system: str | None = None,
    ) -> CompletionResponse:
        """Generate a completion via the OpenAI chat completions API.

        Structural difference from AnthropicAdapter: system prompt goes inside
        the messages list as a dict with role='system' (not a top-level param).
        Usage fields are prompt_tokens/completion_tokens (not input_/output_).

        Args:
            prompt: The user-facing prompt text.
            system: Optional system/instruction prompt. Defaults to a generic assistant
                    instruction when None. Phase 6 will supply structured system prompts
                    from generation/prompts.py (GEN-01).

        Returns:
            CompletionResponse with text, usage, cost_usd, latency_ms, and model.
        """
        client = self._get_client()
        t0 = time.perf_counter()
        response = client.chat.completions.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            messages=[
                {"role": "system", "content": system or "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        # OpenAI SDK: prompt_tokens / completion_tokens (differs from Anthropic).
        # response.usage is typed as CompletionUsage | None by the openai stubs; for
        # standard chat completions it is always populated. The type: ignore[union-attr]
        # is narrow — only the .prompt_tokens / .completion_tokens field accesses.
        usage = TokenUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )
        cost = cost_for("openai", self._model, usage.prompt_tokens, usage.completion_tokens)

        choice = response.choices[0]
        content = choice.message.content or ""
        if not content:
            # D-14: gpt-oss-120b is a reasoning model. On empty content, surface WHY
            # (length-truncation vs. output routed to a reasoning channel) so an empty
            # answer is diagnosable here rather than a bare ANS-03 crash downstream.
            reasoning = getattr(choice.message, "reasoning_content", None) or getattr(
                choice.message, "reasoning", None
            )
            log.warning(
                "openai_empty_content",
                model=self._model,
                finish_reason=choice.finish_reason,
                completion_tokens=usage.completion_tokens,
                max_tokens=_MAX_TOKENS,
                reasoning_present=bool(reasoning),
                reasoning_chars=len(reasoning) if reasoning else 0,
            )

        return CompletionResponse(
            text=content,
            usage=usage,
            cost_usd=cost,
            latency_ms=latency_ms,
            model=response.model,
        )
