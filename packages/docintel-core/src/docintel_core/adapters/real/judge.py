"""Cross-family LLMJudge that evaluates predictions via the complement provider.

D-04: The judge uses the OTHER provider from the generator to avoid circular-judge
bias (a model rubber-stamping its own output). Factory wiring:
  - generator = AnthropicAdapter → judge wraps OpenAIAdapter
  - generator = OpenAIAdapter    → judge wraps AnthropicAdapter

The underlying LLMClient.complete() is already tenacity-wrapped (via
AnthropicAdapter or OpenAIAdapter). This module does NOT add a second @retry
layer — double-wrapping would cause retry storms and obscure which provider
is actually being retried.

Tenacity import (ADP-06 gate): 'from tenacity import' must appear in every
real adapter file. This file's judge() method calls self._llm.complete()
which transitively crosses the LLM SDK boundary. The grep gate checks for
'from tenacity import' in any file that contains SDK-adjacent call patterns.
While judge.py's own .complete() call doesn't directly match the SDK patterns
the gate greps for, we include the import here to satisfy the spirit of ADP-06
and to make the dependency explicit to future readers.
"""

from __future__ import annotations

import logging
import re

import structlog
from tenacity import retry  # noqa: F401 — imported for ADP-06 gate; retry delegated to self._llm

# The tenacity import above is intentional even though no @retry decorator
# appears in this file. CrossFamilyJudge delegates retry responsibility to
# self._llm.complete(), which is already @retry-wrapped by AnthropicAdapter
# or OpenAIAdapter. Adding a second @retry here would double-wrap and create
# retry storms. The import satisfies the structural ADP-06 contract (every
# file in real/ with LLM-adjacent call patterns imports tenacity).
# See CONTEXT.md D-18 and PLAN.md Task 02-05-03 note.
from docintel_core.adapters.protocols import LLMClient
from docintel_core.adapters.types import JudgeVerdict
from docintel_core.config import Settings

_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)

_JUDGE_SYSTEM_PROMPT = (
    "You are a strict citation-faithfulness judge. "
    "Evaluate whether each claim in the prediction is supported by the reference passages. "
    "Respond with a score between 0.0 and 1.0 in the format 'score: 0.XX' "
    "followed by your reasoning."
)

# Heuristic pattern to extract score from judge response (Phase 6 replaces with JSON-mode parse)
_SCORE_PATTERN = re.compile(r"score\s*:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)


def _build_judge_prompt(prediction: str, reference: list[str], rubric: str) -> str:
    """Build a placeholder judging prompt (Phase 6 replaces with canonical prompts.py version).

    Args:
        prediction: The generated answer text to evaluate.
        reference:  List of reference passage strings for grounding.
        rubric:     Optional evaluation criteria.

    Returns:
        A string prompt for the judge LLM.
    """
    ref_text = "\n".join(f"[{i}] {r}" for i, r in enumerate(reference))
    rubric_section = f"\nRubric: {rubric}" if rubric else ""
    return (
        f"Score whether each claim in the prediction is supported by the reference passages.\n\n"
        f"Prediction:\n{prediction}\n\n"
        f"Reference passages:\n{ref_text}"
        f"{rubric_section}"
    )


def _parse_judge_response(text: str) -> JudgeVerdict:
    """Parse the judge LLM response into a JudgeVerdict.

    Phase 2 heuristic: extract 'score: 0.XX' pattern from response text.
    Phase 6 will replace this with structured JSON-mode parsing.

    Args:
        text: Raw response text from the judge LLM.

    Returns:
        JudgeVerdict with extracted score and reasoning.
    """
    match = _SCORE_PATTERN.search(text)
    score = float(match.group(1)) if match else 0.0
    # Clamp to [0.0, 1.0] in case the model emits out-of-range values
    score = max(0.0, min(1.0, score))
    return JudgeVerdict(
        score=score,
        passed=score >= 0.5,
        reasoning=text,
        unsupported_claims=[],  # Phase 6 will parse these from structured output
    )


class CrossFamilyJudge:
    """Real LLMJudge that delegates evaluation to the complement provider's LLMClient.

    Satisfies the LLMJudge Protocol structurally (no inheritance required).
    The 'complement' provider is the OTHER provider from the generator:
      - generator = AnthropicAdapter → complement = OpenAIAdapter
      - generator = OpenAIAdapter    → complement = AnthropicAdapter

    This avoids circular-judge bias where a model rubber-stamps its own output.
    Factory wiring is done by make_adapters() (factory.py); this class receives
    an already-constructed LLMClient as complement_llm.
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

        The underlying self._llm.complete() is already @retry-wrapped by
        AnthropicAdapter / OpenAIAdapter. No additional retry here (D-18:
        avoiding double-wrap). The tenacity import at the top of this module
        satisfies the ADP-06 structural property.

        Phase 2 placeholder prompt and heuristic score parsing. Phase 6 will
        replace _build_judge_prompt() and _parse_judge_response() with the
        canonical versions from generation/prompts.py (GEN-01).

        Args:
            prediction: The generated answer text to evaluate.
            reference:  List of reference passage strings for grounding.
            rubric:     Optional evaluation criteria / rubric text.

        Returns:
            JudgeVerdict with score [0,1], passed flag, reasoning, and
            unsupported_claims (empty list until Phase 6 structured parsing).
        """
        prompt = _build_judge_prompt(prediction, reference, rubric)
        response = self._llm.complete(prompt, system=_JUDGE_SYSTEM_PROMPT)
        return _parse_judge_response(response.text)
