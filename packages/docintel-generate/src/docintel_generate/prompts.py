"""Phase 6 canonical prompt home — GEN-01 + GEN-02 contracts.

Three module-level ``Final[str]`` prompts (``SYNTHESIS_PROMPT``,
``REFUSAL_PROMPT``, ``JUDGE_PROMPT``) plus three per-prompt
SHA256[:12] hashes and one combined ``PROMPT_VERSION_HASH``. All four
hashes are computed at module import via :func:`_h`; ``mypy --strict``
verifies the ``Final[str]`` annotations so the constants cannot be
mutated after import (defense-in-depth against silent prompt drift —
Pitfall 3).

D-07 / D-08 / D-10 / D-11 (06-CONTEXT.md) anchor the contract:

* D-07 — Three named prompts (synthesis, refusal, judge). ``SYNTHESIS_PROMPT``
  embeds the refusal instruction verbatim AND the comparative-question
  structuring guidance (Pitfall 10).
* D-08 — Per-prompt hashes + combined ``PROMPT_VERSION_HASH`` (lowercase
  12-char hex truncation of sha256). Phase 10 EVAL-02 manifest header
  surfaces the combined hash; Phase 11 ablation reports + the
  ``generator_completed`` structlog line surface per-prompt hashes for
  localised drift detection.
* D-10 — Inline ``[chunk_id]`` bracket citations; locked fenced example
  using ``AAPL-FY2024-Item-1A-018`` + ``NVDA-FY2024-Item-7-042``.
* D-11 — Canonical refusal sentinel. ``REFUSAL_PROMPT`` byte-equals
  ``REFUSAL_TEXT_SENTINEL`` from ``docintel_core.types`` per Pitfall 9
  single-source-of-truth.

Pitfall 9 cycle-resolution: the sentinel string lives in
``docintel_core.types`` (upward-stack), NOT here. This module imports
it; the stub adapter (Plan 06-05) imports it too. Import direction is
strictly ``docintel-generate → docintel-core``; never the reverse.

Plan 06-06 imports :func:`build_judge_user_prompt` to replace the Phase 2
placeholder ``_build_judge_prompt`` helper in ``adapters/real/judge.py``
(D-09 migration).
"""

# DO NOT reformat the body of these prompts — the SHA256[:12] hash is byte-exact.
# Whitespace, encoding, or line-ending changes drift the hash. See Pitfall 3.

from __future__ import annotations

import hashlib
from typing import Final

from docintel_core.types import REFUSAL_TEXT_SENTINEL


def _h(s: str) -> str:
    """SHA256 truncated to 12 hex chars — manifest-friendly."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


SYNTHESIS_PROMPT: Final[str] = """\
You are answering a question using ONLY the retrieved 10-K excerpts in the <context> block below.

Rules:
1. Every factual sentence in your answer MUST end with one or more [chunk_id] citations
   referencing the chunks provided. Do not invent chunk_ids; only cite from <context>.
2. If a claim cannot be grounded in the provided context, omit the claim.
3. If the context does not contain enough information to answer the question, emit
   verbatim and ONLY this sentence (a single line, no line break):
   "I cannot answer this question from the retrieved 10-K excerpts."
4. For comparative questions across companies, structure the answer to enumerate each
   compared entity's grounded evidence before reaching a comparison conclusion.

Example:
Apple highlighted supplier concentration in China and Taiwan as a key risk in its
FY2024 10-K [AAPL-FY2024-Item-1A-018]. NVIDIA disclosed revenue concentration with a
single hyperscaler customer [NVDA-FY2024-Item-7-042].
"""
"""Canonical synthesis system prompt for the answer-with-citations path (D-07).

Body locked per RESEARCH §Code Example 1 (lines 874-891). Contains:

* XML-tag instruction (``<context>``) per Anthropic prompt-engineering convention.
* Numbered rules block enforcing inline ``[chunk_id]`` bracket citations (D-10),
  no-invented-chunk-ids rule, refusal-when-insufficient instruction with the
  exact ``REFUSAL_TEXT_SENTINEL`` body (D-11), comparative-question structuring
  guidance (Pitfall 10 mitigation — the hero question's failure mode).
* Locked fenced example with ``[AAPL-FY2024-Item-1A-018]`` and
  ``[NVDA-FY2024-Item-7-042]`` chunk_ids (D-10 — these substrings are part of
  the contract; Phase 6 acceptance greps for them).
"""

REFUSAL_PROMPT: Final[str] = REFUSAL_TEXT_SENTINEL
"""Canonical refusal prompt body — byte-equals ``REFUSAL_TEXT_SENTINEL`` from
``docintel_core.types`` per Pitfall 9 / RESEARCH Open Question 1.

Single source of truth across stub LLM + generator + Phase 7 Citation parser.
The 64-char string body is HASHED here for ``_REFUSAL_HASH`` and the combined
``PROMPT_VERSION_HASH``; the actual string lives in ``docintel_core.types``.
"""

JUDGE_PROMPT: Final[str] = """\
You are a strict citation-faithfulness judge.

Evaluate whether each claim in the prediction is supported by at least one of the
reference passages provided. Emit a structured verdict via the submit_verdict tool.

Scoring rubric:
- score in [0.0, 1.0] = fraction of prediction claims grounded in the reference set.
- passed = (score >= 0.5).
- reasoning = concise human-readable explanation of how you arrived at the score.
- unsupported_claims = list of prediction claims you could not ground in the references.

Judge ONLY the prediction-vs-reference structural match. Do not infer claims outside
the reference set. Do not penalise the prediction for omitting claims that ARE
supported by references but were not stated.
"""
"""Canonical faithfulness-judge system prompt (D-09; consumed by Plan 06-06).

Body locked per RESEARCH §Code Example 1 (lines 897-912). Contains:

* Role description ("strict citation-faithfulness judge").
* Evaluation task — claim-by-claim grounding against reference passages.
* Scoring rubric naming all four ``JudgeVerdict`` schema fields:
  ``score`` ∈ [0.0, 1.0], ``passed = (score >= 0.5)``, ``reasoning``,
  ``unsupported_claims``. Plan 06-06 wires Anthropic
  ``tools=[{strict:true}]`` / OpenAI ``response_format={'type':
  'json_schema', 'strict': true}`` against this schema.
* Bias-mitigation rules per RESEARCH §"Judging the Judges" — judge ONLY
  prediction-vs-reference structural match; do not infer claims outside
  the reference set; do not penalise for omitted-but-grounded claims.
"""

# Per-prompt + combined hashes, computed at module import. mypy --strict verifies Final[str].
_SYNTHESIS_HASH: Final[str] = _h(SYNTHESIS_PROMPT)
_REFUSAL_HASH: Final[str] = _h(REFUSAL_PROMPT)
_JUDGE_HASH: Final[str] = _h(JUDGE_PROMPT)
PROMPT_VERSION_HASH: Final[str] = _h(_SYNTHESIS_HASH + _REFUSAL_HASH + _JUDGE_HASH)


def build_judge_user_prompt(prediction: str, reference: list[str], rubric: str = "") -> str:
    """Build the user-side prompt for the judge LLM call (D-09 migration helper).

    Plan 06-06 imports this helper inside ``adapters/real/judge.py``, replacing
    the Phase 2 placeholder ``_build_judge_prompt`` function. The format here
    is locked-down: indexed reference passages (``[0]``, ``[1]``, ...) followed
    by an optional rubric block.
    """
    ref_text = "\n".join(f"[{i}] {r}" for i, r in enumerate(reference))
    rubric_section = f"\nAdditional rubric: {rubric}" if rubric else ""
    return (
        f"Prediction to evaluate:\n{prediction}\n\n"
        f"Reference passages:\n{ref_text}"
        f"{rubric_section}"
    )
