"""Pure regex + sentinel helpers for docintel-generate.

Single canonical home for the chunk_id extraction regex ``_CHUNK_RE`` (D-12),
the confidence marker regex ``_CONFIDENCE_RE`` (D-04), and the associated
helper functions :func:`is_refusal` and :func:`parse_confidence`.

Plan 06-05 re-imports ``_CHUNK_RE`` into the stub adapter
(``packages/docintel-core/src/docintel_core/adapters/stub/llm.py``),
retiring the in-stub definition.

The :func:`is_refusal` helper provides a single boolean check for the
canonical refusal sentinel (D-13 step 5). Plan 06-04 Generator Step D
consumes it for refusal-flag construction; Phase 7 Citation parser
consumes it to skip refusal answers (no citations expected); Phase 9
faithfulness tests assert byte-exact sentinel matching against this
helper's output.

The :func:`parse_confidence` helper (D-04) extracts and strips the
``[confidence: high|medium|low]`` marker from synthesis text. Called by
``Answer.from_generation_result`` (the ONE allowed cross-package import
per CONTEXT.md D-12). Must NOT be called on refusal text (Pitfall 1).

No imports outside stdlib + ``docintel_core.types``.

Pitfall 9 (RESEARCH Open Question 1) resolution: the refusal sentinel
string lives in ``docintel_core.types``; ``is_refusal`` imports it
upward-stack. ``docintel-generate → docintel-core``; never the reverse.
"""

from __future__ import annotations

import re
from typing import Final, Literal

from docintel_core.types import REFUSAL_TEXT_SENTINEL

_CHUNK_RE: Final[re.Pattern[str]] = re.compile(r"\[([^\]]+)\]")
"""Module-level compiled regex for extracting [chunk_id] tokens.

Pattern is locked here as the single canonical home (D-12); Plan 06-05
re-imports this into ``adapters/stub/llm.py``, retiring the duplicate
definition there. Phase 7 Citation parser also imports this regex to
enforce single-source consistency across stub + real + parse layers.
Phase 9 faithfulness tests rely on the same regex producing the same
citation extractions in stub and real modes.
"""


def is_refusal(text: str) -> bool:
    """Return True if ``text`` starts with the canonical refusal sentinel.

    D-13 step 5 (Plan 06-04 Generator Step D) consumes this for refusal-flag
    construction. Phase 7 Citation parser consumes it to skip refusal answers
    (no citations expected). Single boolean check; no NLI, no embeddings —
    structural detection of the locked 63-char sentinel string from
    ``docintel_core.types.REFUSAL_TEXT_SENTINEL``.
    """
    return text.startswith(REFUSAL_TEXT_SENTINEL)


_CONFIDENCE_RE: Final[re.Pattern[str]] = re.compile(
    r"\[confidence:\s*(high|medium|low)\]",
    re.IGNORECASE,
)
"""Module-level compiled regex for extracting the [confidence: X] marker.

Pattern mirrors ``docintel_core.types._CONFIDENCE_RE`` (deliberate duplication
per Research Flag 1 in 07-RESEARCH.md — import direction: generate → core;
never the reverse). Accepts only the three canonical levels
``high``, ``medium``, ``low`` (case-insensitive); any other content yields no
match (T-07-T-02 threat mitigation).
"""


def parse_confidence(
    text: str,
) -> tuple[str, Literal["high", "medium", "low"] | None]:
    """Extract and strip the ``[confidence: X]`` marker from synthesis text.

    Returns ``(stripped_text, confidence_level)``. If no marker is found,
    returns ``(text, None)`` — the caller (``Answer.from_generation_result``)
    defaults to ``"medium"``.

    The trailing marker is removed from ``stripped_text`` via
    ``text[:m.start()].rstrip()`` so ``Answer.text`` is never exposed to the
    Phase 13 UI with the raw bracket literal (Pitfall 6 in 07-RESEARCH.md).

    IMPORTANT: this function must NOT be called on refusal text
    (``is_refusal(text) == True`` paths skip this function per D-05 and
    Pitfall 1 in 07-RESEARCH.md). The contract is enforced by the caller
    in ``Answer.from_generation_result``.

    Co-located with ``_CHUNK_RE``/``is_refusal`` per GEN-01 (single canonical
    home for all text-extraction helpers in ``docintel-generate``).
    """
    m = _CONFIDENCE_RE.search(text)
    if m is None:
        return text, None
    confidence = m.group(1).lower()
    stripped = text[: m.start()].rstrip()
    return stripped, confidence  # type: ignore[return-value]
