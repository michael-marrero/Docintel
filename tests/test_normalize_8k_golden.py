"""Story 1.6 — committed 8-K golden fixture regression.

Mirrors ``test_normalize_10q_golden.py`` for the 8-K path: the synthetic
``sample_8k`` trimmed HTML normalizes to the committed golden JSON and chunks
byte-identically to the committed golden JSONL. Locks event segmentation +
accession-keyed chunk_id + dotted-item titles against regression.
"""

from __future__ import annotations

import json
from pathlib import Path

from docintel_ingest.chunk import chunk_filing
from docintel_ingest.normalize import normalize_html

_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_8k"
_ACC = "0000320193-24-000075"


def test_normalize_8k_golden_matches() -> None:
    """Fixture HTML → NormalizedFiling matches the golden JSON (sans fetched_at, raw_path)."""
    html = (_DIR / f"aapl_{_ACC}_trimmed.html").read_text("utf-8")
    expected = json.loads((_DIR / f"aapl_{_ACC}_normalized.json").read_text("utf-8"))
    expected.pop("fetched_at", None)
    expected.pop("raw_path", None)

    actual = normalize_html(html, "AAPL", 2024, _ACC, form="8-K", fiscal_period="FY")
    assert actual.model_dump(exclude={"fetched_at", "raw_path"}) == expected


def test_8k_golden_is_event_segmented() -> None:
    """The golden proves flat dotted-item segmentation; no PART, no missing/ordering noise."""
    nf = json.loads((_DIR / f"aapl_{_ACC}_normalized.json").read_text("utf-8"))
    assert nf["filing_type"] == "8-K"
    assert nf["fiscal_period"] == "FY"
    assert nf["manifest"]["items_missing"] == []  # event-driven — no "missing"
    assert nf["manifest"]["ordering_valid"] is True
    assert "Item 2.02" in nf["sections"]
    assert "Item 5.02" in nf["sections"]
    assert "Results of Operations" in nf["sections"]["Item 2.02"]


def test_8k_golden_chunks_byte_identical() -> None:
    """Re-chunking the golden normalized JSON reproduces the committed JSONL byte-for-byte."""
    committed = (_DIR / f"aapl_{_ACC}_chunks.jsonl").read_bytes()
    chunks = chunk_filing(_DIR / f"aapl_{_ACC}_normalized.json")
    payload = ("\n".join(c.model_dump_json() for c in chunks) + "\n") if chunks else ""
    assert payload.encode("utf-8") == committed
    # Accession-keyed, dotted ids.
    assert all(c.chunk_id.startswith("AAPL-8K-000032019324000075-") for c in chunks)
    assert all(c.filing_type == "8-K" and c.fiscal_period == "FY" for c in chunks)
    # dotted-item title resolved via the merged 8-K taxonomy (not the raw code)
    assert chunks[0].item_title == "Results of Operations and Financial Condition"
