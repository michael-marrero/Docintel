"""Plan 05-01 Wave 0 xfail scaffolds for RetrievedChunk (RET-04, D-03, CD-02).

Covers VALIDATION.md rows 05-01-05 and 05-01-06 — the Phase 5 → Phase 6/7
public contract:

* test_retrieved_chunk_required_fields — the seven D-03 fields are all
  accepted (chunk_id, text, score, ticker, fiscal_year, item_code,
  char_span_in_section).
* test_char_span_tuple — char_span_in_section round-trips as a tuple[int, int]
  (matches Phase 3 D-16 anchor type; Phase 7 will render the surrounding
  section text and highlight the span via this field).
* test_retrieved_chunk_forbids_extra — extra="forbid" rejects per-stage debug
  fields on the public shape (D-03 keeps the API JSON minimal; per-stage data
  lives in the structlog stream per D-12).
* test_retrieved_chunk_is_frozen — frozen=True; downstream callers must not
  mutate the result list (RESEARCH.md anti-pattern "Don't make RetrievedChunk
  mutable").

All four tests are xfail-strict-marked because ``RetrievedChunk`` does not yet
live in ``docintel_core.types`` at Wave 0 (per CD-02, the model home is
``docintel_core.types``, NOT ``docintel-retrieve.types``). The in-function
``from docintel_core.types import RetrievedChunk`` raises ImportError →
pytest counts this as the expected failure under xfail(strict=True). Plan 05-02
adds ``RetrievedChunk`` to ``docintel_core.types`` and removes these xfail
markers.

Analogs:
* ``tests/test_index_manifest.py`` — Pydantic-schema test patterns.
* ``packages/docintel-core/src/docintel_core/types.py`` ``Chunk`` class
  (lines 104-144) — same Pydantic v2 BaseModel + ConfigDict shape.
* 05-PATTERNS.md ``tests/test_retrieved_chunk_schema.py`` section.
"""

from __future__ import annotations

import pytest


def _ok_payload() -> dict:
    """Canonical D-03 7-field payload — used across every test in this file."""
    return {
        "chunk_id": "AAPL-FY2024-Item-1A-007",
        "text": "Some chunk text.",
        "score": 0.812,
        "ticker": "AAPL",
        "fiscal_year": 2024,
        "item_code": "Item 1A",
        "char_span_in_section": (100, 250),
    }


def test_retrieved_chunk_required_fields() -> None:
    """RET-04 — all seven D-03 fields are accepted (Plan 05-02)."""
    # In-function import: RetrievedChunk does not yet live in docintel_core.types at Wave 0.
    from docintel_core.types import RetrievedChunk  # noqa: WPS433 — intentional in-function import

    rc = RetrievedChunk(**_ok_payload())
    assert rc.chunk_id == "AAPL-FY2024-Item-1A-007"
    assert rc.text == "Some chunk text."
    assert rc.score == 0.812
    assert rc.ticker == "AAPL"
    assert rc.fiscal_year == 2024
    assert rc.item_code == "Item 1A"
    assert rc.char_span_in_section == (100, 250)


def test_char_span_tuple() -> None:
    """RET-04 — char_span_in_section round-trips as tuple[int, int] (D-16; Plan 05-02)."""
    from docintel_core.types import RetrievedChunk  # noqa: WPS433

    rc = RetrievedChunk(**_ok_payload())
    assert rc.char_span_in_section == (100, 250)
    assert isinstance(rc.char_span_in_section, tuple)
    assert len(rc.char_span_in_section) == 2
    assert all(isinstance(v, int) for v in rc.char_span_in_section)


def test_retrieved_chunk_forbids_extra() -> None:
    """RET-04 — extra='forbid' rejects per-stage debug fields on the public shape (D-03; Plan 05-02)."""
    from pydantic import ValidationError  # noqa: WPS433
    from docintel_core.types import RetrievedChunk  # noqa: WPS433

    payload = _ok_payload()
    payload["bm25_rank"] = 3  # forbidden per-stage debug field (D-03 keeps the public shape minimal)
    with pytest.raises(ValidationError):
        RetrievedChunk(**payload)


def test_retrieved_chunk_is_frozen() -> None:
    """RET-04 — Pydantic frozen=True; downstream callers must not mutate (Plan 05-02)."""
    from pydantic import ValidationError  # noqa: WPS433
    from docintel_core.types import RetrievedChunk  # noqa: WPS433

    rc = RetrievedChunk(**_ok_payload())
    with pytest.raises(ValidationError):
        rc.score = 0.99  # type: ignore[misc]
