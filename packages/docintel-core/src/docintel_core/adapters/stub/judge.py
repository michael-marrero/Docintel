"""Deterministic stub LLMJudge -- schema-check citation grounding.

score = fraction of cited chunk_ids that appear in the reference list.
passed = score >= 0.5. Exercises Phase 9 faithfulness (MET-03) and
citation-accuracy (MET-04) without a real model call (D-17).

The judge uses the same bracket-pattern regex as the LLM stub but maintains
its own local regex to keep the judge independent of the LLM client module.
The regex is the contract, not the import.

No randomness, no clock reads (ADP-07).
No retry wrapping -- stubs never make network calls. The CI grep gate for
tenacity is scoped to adapters/real/ only.
"""

from __future__ import annotations

import re

from docintel_core.adapters.types import JudgeVerdict


class StubLLMJudge:
    """Deterministic stub LLMJudge for stub/CI mode.

    Satisfies the LLMJudge Protocol structurally (no inheritance).
    Performs a schema-check: extracts [chunk_id] tokens from prediction,
    intersects with reference strings, computes fraction grounded as score.
    Deterministic: identical inputs always produce identical outputs.
    No external dependencies.
    """

    @property
    def name(self) -> str:
        """Adapter identifier for Phase 10 eval manifest headers."""
        return "stub-judge"

    def judge(
        self,
        prediction: str,
        reference: list[str],
        rubric: str = "",
    ) -> JudgeVerdict:
        """Evaluate prediction faithfulness via schema-check citation grounding.

        Extracts [chunk_id] tokens from prediction text, then checks each
        against the reference list. A chunk ID is considered grounded if it
        appears as a substring in any reference string.

        score = len(supported) / len(cited) if cited else 0.0
        passed = score >= 0.5

        Args:
            prediction: Generated answer text to evaluate (may contain [chunk_id]).
            reference:  List of reference passage strings for grounding check.
            rubric:     Ignored in stub mode (accepted for Protocol conformance).

        Returns:
            JudgeVerdict with score, passed, templated reasoning, unsupported_claims.
        """
        cited = re.findall(r"\[([^\]]+)\]", prediction)
        supported = [c for c in cited if any(c in ref for ref in reference)]
        unsupported = [c for c in cited if c not in supported]
        score = len(supported) / len(cited) if cited else 0.0
        passed = score >= 0.5
        reasoning = (
            f"{len(supported)}/{len(cited)} cited chunks grounded in reference; "
            f"unsupported: {unsupported}"
        )
        return JudgeVerdict(
            score=score,
            passed=passed,
            reasoning=reasoning,
            unsupported_claims=unsupported,
        )
