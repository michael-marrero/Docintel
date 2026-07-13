"""Story 1.1 Task 8 — committed 10-Q golden fixture regression.

Mirrors ``tests/test_normalize.py`` (10-K) for the 10-Q path: the synthetic
``sample_10q`` trimmed HTML normalizes to the committed golden JSON and chunks
byte-identically to the committed golden JSONL. Locks the PART-aware
segmentation + Q-keyed chunk_id contract against regression.
"""

from __future__ import annotations

import json
from pathlib import Path

from docintel_ingest.chunk import chunk_filing
from docintel_ingest.normalize import normalize_html

_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_10q"


def test_normalize_10q_golden_matches() -> None:
    """Fixture HTML → NormalizedFiling matches the golden JSON (sans fetched_at, raw_path)."""
    html = (_DIR / "msft_Q3FY2024_trimmed.html").read_text("utf-8")
    expected = json.loads((_DIR / "msft_Q3FY2024_normalized.json").read_text("utf-8"))
    expected.pop("fetched_at", None)
    expected.pop("raw_path", None)

    actual = normalize_html(
        html, "MSFT", 2024, "0000789019-24-000090", form="10-Q", fiscal_period="Q3"
    )
    assert actual.model_dump(exclude={"fetched_at", "raw_path"}) == expected


def test_10q_golden_is_part_aware() -> None:
    """The golden proves Part I Item 2 (MD&A) and Part II Item 2 are distinct sections."""
    nf = json.loads((_DIR / "msft_Q3FY2024_normalized.json").read_text("utf-8"))
    assert nf["filing_type"] == "10-Q"
    assert nf["fiscal_period"] == "Q3"
    assert "Part I Item 2" in nf["sections"]
    assert "Part II Item 2" in nf["sections"]
    assert "Net sales increased" in nf["sections"]["Part I Item 2"]  # MD&A body
    assert "repurchased" in nf["sections"]["Part II Item 2"]  # buybacks


def test_10q_golden_chunks_byte_identical() -> None:
    """Re-chunking the golden normalized JSON reproduces the committed JSONL byte-for-byte."""
    committed = (_DIR / "msft_Q3FY2024_chunks.jsonl").read_bytes()
    chunks = chunk_filing(_DIR / "msft_Q3FY2024_normalized.json")
    payload = ("\n".join(c.model_dump_json() for c in chunks) + "\n") if chunks else ""
    assert payload.encode("utf-8") == committed
    # Q-keyed, PART-prefixed ids.
    assert all(c.chunk_id.startswith("MSFT-Q3FY2024-Pt") for c in chunks)
    assert all(c.filing_type == "10-Q" and c.fiscal_period == "Q3" for c in chunks)
