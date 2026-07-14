"""Story 1.1 Task 1 — filing_type + fiscal_period provenance on the ingest schemas.

FR-A6 (provenance) / AC-1, AC-2: ``Chunk`` and ``NormalizedFiling`` carry the
form type and fiscal period so a 10-Q or 8-K chunk is self-describing. Both
default to the 10-K values (``"10-K"`` / ``"FY"``) so every existing 10-K
construction path stays byte-stable once the corpus is re-baselined (AC-4).
Both models are ``extra="forbid"``, so these must be *declared* fields.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from docintel_core.types import Chunk, NormalizedFiling, NormalizedFilingManifest


def _chunk(**overrides: object) -> Chunk:
    kwargs: dict[str, object] = dict(
        chunk_id="AAPL-FY2024-Item-1A-000",
        ticker="AAPL",
        fiscal_year=2024,
        accession="0000320193-24-000123",
        item_code="Item 1A",
        item_title="Risk Factors",
        text="placeholder",
        char_span_in_section=(0, 11),
        n_tokens=1,
        prev_chunk_id=None,
        next_chunk_id=None,
        sha256_of_text="0" * 16,
    )
    kwargs.update(overrides)
    return Chunk(**kwargs)  # type: ignore[arg-type]


def _normalized(**overrides: object) -> NormalizedFiling:
    kwargs: dict[str, object] = dict(
        ticker="AAPL",
        fiscal_year=2024,
        accession="0000320193-24-000123",
        fetched_at="2026-01-01T00:00:00Z",
        raw_path="data/corpus/raw/AAPL/FY2024.html",
        sections={"Item 1A": "text"},
        manifest=NormalizedFilingManifest(
            items_found=["Item 1A"], items_missing=[], ordering_valid=True, tables_dropped=0
        ),
    )
    kwargs.update(overrides)
    return NormalizedFiling(**kwargs)  # type: ignore[arg-type]


def test_chunk_defaults_to_10k_fy() -> None:
    """Omitting the new fields yields the 10-K defaults (byte-stability guard, AC-4)."""
    chunk = _chunk()
    assert chunk.filing_type == "10-K"
    assert chunk.fiscal_period == "FY"


def test_normalized_defaults_to_10k_fy() -> None:
    nf = _normalized()
    assert nf.filing_type == "10-K"
    assert nf.fiscal_period == "FY"


@pytest.mark.parametrize("filing_type", ["10-K", "10-Q", "8-K"])
def test_chunk_accepts_all_form_types(filing_type: str) -> None:
    assert _chunk(filing_type=filing_type).filing_type == filing_type


@pytest.mark.parametrize("fiscal_period", ["FY", "Q1", "Q2", "Q3"])
def test_chunk_accepts_all_periods(fiscal_period: str) -> None:
    assert _chunk(fiscal_period=fiscal_period).fiscal_period == fiscal_period


def test_chunk_rejects_unknown_form_type() -> None:
    with pytest.raises(ValidationError):
        _chunk(filing_type="10-Q/A")


def test_normalized_rejects_unknown_period() -> None:
    # Q4 became valid in Story 1.2 (earnings calls happen for all four quarters);
    # assert rejection of a genuinely-unknown period instead.
    with pytest.raises(ValidationError):
        _normalized(fiscal_period="Q5")
