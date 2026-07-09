"""Phase 7 Plan 01-02 tests for ANS-02 Citation Pydantic shape (D-07..D-11).

Covers VALIDATION.md rows for ANS-02 — the Phase 7 Citation schema that
Phase 13 UI uses to render hoverable, highlighted citation quotes:

* test_citation_has_seven_fields — all seven D-07..D-11 fields are accepted
  (chunk_id, company, fiscal_year, item_code, item_title, text,
  char_span_in_section).
* test_char_span_type — char_span_in_section round-trips as tuple[int, int]
  (D-11 citation anchor for the Phase 13 highlight UI).
* test_citation_extra_forbid — extra="forbid" rejects unknown fields.
* test_citation_frozen — frozen=True; downstream callers must not mutate.

Analogs:
* ``tests/test_retrieved_chunk_schema.py`` (full file, 99 lines) —
  Phase 5 D-03 RetrievedChunk analog; exact test structure replicated here
  with RetrievedChunk replaced by Citation.
* 07-PATTERNS.md §"tests/test_citation_schema.py" — payload helper,
  char_span verbatim copy, extra=forbid and frozen patterns.
"""

from __future__ import annotations

import pytest


def _ok_citation_payload() -> dict:
    """Canonical ANS-02 7-field Citation payload — used across every test in this file.

    company is the full name (D-07), fiscal_year is int (D-10), item_code +
    item_title together satisfy D-08 (section identity), text carries the
    excerpt (D-09), char_span_in_section is the highlight anchor (D-11).
    """
    return {
        "chunk_id": "AAPL-FY2024-Item-1A-007",
        "company": "Apple Inc.",
        "fiscal_year": 2024,
        "item_code": "Item 1A",
        "item_title": "Risk Factors",
        "text": "Some chunk text.",
        "char_span_in_section": (100, 250),
    }


def test_citation_has_seven_fields() -> None:
    """ANS-02 + D-07..D-11 — all seven fields accepted on construction.

    chunk_id, company, fiscal_year, item_code, item_title, text,
    char_span_in_section are the exact 7 fields.
    """
    from docintel_core.types import Citation

    citation = Citation(**_ok_citation_payload())
    assert citation.chunk_id == "AAPL-FY2024-Item-1A-007"
    assert citation.company == "Apple Inc."
    assert citation.fiscal_year == 2024
    assert citation.item_code == "Item 1A"
    assert citation.item_title == "Risk Factors"
    assert citation.text == "Some chunk text."
    assert citation.char_span_in_section == (100, 250)


def test_char_span_type() -> None:
    """ANS-02 + D-11 — char_span_in_section round-trips as tuple[int, int].

    Copied verbatim from test_retrieved_chunk_schema.py:67-75, swapping
    RetrievedChunk → Citation and _ok_payload → _ok_citation_payload.
    Phase 13 UI highlights the span; the tuple[int,int] type must survive
    Pydantic round-trip intact.
    """
    from docintel_core.types import Citation

    citation = Citation(**_ok_citation_payload())
    assert citation.char_span_in_section == (100, 250)
    assert isinstance(citation.char_span_in_section, tuple)
    assert len(citation.char_span_in_section) == 2
    assert all(isinstance(v, int) for v in citation.char_span_in_section)


def test_citation_extra_forbid() -> None:
    """ANS-02 + D-02 — extra='forbid' rejects unknown fields on construction.

    Defense against schema drift: passing an unknown field raises
    pydantic.ValidationError (mirrors test_retrieved_chunk_forbids_extra).
    """
    from docintel_core.types import Citation
    from pydantic import ValidationError

    payload = _ok_citation_payload()
    payload["bm25_rank"] = 3  # forbidden per-stage debug field
    with pytest.raises(ValidationError):
        Citation(**payload)


def test_citation_frozen() -> None:
    """ANS-02 + D-02 — Pydantic frozen=True; downstream callers must not mutate.

    Mirrors test_retrieved_chunk_is_frozen; same ConfigDict(frozen=True)
    contract. Phase 13 renders citation.text and citation.char_span_in_section
    directly; immutability prevents accidental downstream mutation.
    """
    from docintel_core.types import Citation
    from pydantic import ValidationError

    citation = Citation(**_ok_citation_payload())
    with pytest.raises(ValidationError):
        citation.fiscal_year = 2025  # type: ignore[misc]
