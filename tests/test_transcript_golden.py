"""Story 1.2 — committed transcript golden fixture regression."""

from __future__ import annotations

import json
from pathlib import Path

from docintel_ingest.chunk import chunk_filing
from docintel_ingest.transcript import parse_transcript

_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_transcript"


def test_transcript_golden_normalize_matches() -> None:
    expected = json.loads((_DIR / "aapl_CALL-Q1FY2024_normalized.json").read_text("utf-8"))
    expected.pop("fetched_at", None)
    expected.pop("raw_path", None)
    actual = parse_transcript(_DIR / "aapl_Q1FY2024.json")
    assert actual.model_dump(exclude={"fetched_at", "raw_path"}) == expected


def test_transcript_golden_chunks_byte_identical() -> None:
    committed = (_DIR / "aapl_CALL-Q1FY2024_chunks.jsonl").read_bytes()
    chunks = chunk_filing(_DIR / "aapl_CALL-Q1FY2024_normalized.json")
    payload = ("\n".join(c.model_dump_json() for c in chunks) + "\n") if chunks else ""
    assert payload.encode("utf-8") == committed
    assert all(c.chunk_id.startswith("AAPL-CALL-Q1FY2024-Turn-") for c in chunks)
    assert all(c.filing_type == "transcript" and c.fiscal_period == "Q1" for c in chunks)
    # Speaker provenance: item_title is the speaker (FR-A6).
    assert chunks[1].item_title == "Tim Cook (Chief Executive Officer)"
