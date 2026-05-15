"""Pure regex + sentinel helpers for docintel-generate.

Single canonical home for the chunk_id extraction regex ``_CHUNK_RE`` (D-12).
Plan 06-05 re-imports this regex into the stub adapter
(``packages/docintel-core/src/docintel_core/adapters/stub/llm.py``),
retiring the in-stub definition. Between Wave 1 (this plan, 06-03) and
Wave 3 (Plan 06-05), the two definitions live in parallel — they are
byte-identical (``r"\\[([^\\]]+)\\]"``).

The :func:`is_refusal` helper provides a single boolean check for the
canonical refusal sentinel (D-13 step 5). Plan 06-04 Generator Step D
consumes it for refusal-flag construction; Phase 7 Citation parser
consumes it to skip refusal answers (no citations expected); Phase 9
faithfulness tests assert byte-exact sentinel matching against this
helper's output. No imports outside stdlib + ``docintel_core.types``.

Pitfall 9 (RESEARCH Open Question 1) resolution: the refusal sentinel
string lives in ``docintel_core.types``; ``is_refusal`` imports it
upward-stack. ``docintel-generate → docintel-core``; never the reverse.
"""

from __future__ import annotations

import re
from typing import Final

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
