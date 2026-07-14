"""Story 1.2 — transcript parse + speaker-turn segmentation (mechanism)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from docintel_ingest.transcript import parse_transcript

_SRC = Path(__file__).resolve().parent / "fixtures" / "sample_transcript" / "aapl_Q1FY2024.json"


def test_parse_segments_by_speaker_turn() -> None:
    nf = parse_transcript(_SRC)
    assert nf.filing_type == "transcript"
    assert nf.fiscal_period == "Q1"
    assert nf.accession == "CALL-2024-02-01"
    assert list(nf.sections.keys()) == ["Turn 000", "Turn 001", "Turn 002", "Turn 003"]
    # Speaker heading is the section's first line (drives item_title + embedded attribution).
    assert nf.sections["Turn 001"].startswith("Tim Cook (Chief Executive Officer)")
    assert nf.sections["Turn 000"].startswith("Operator")  # empty role → no parens


def test_missing_required_key_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text('{"ticker": "AAPL", "turns": []}', encoding="utf-8")
    with pytest.raises(ValueError):
        parse_transcript(p)


def test_empty_turns_list_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text(
        '{"ticker":"AAPL","fiscal_year":2024,"fiscal_period":"Q1","turns":[]}', encoding="utf-8"
    )
    with pytest.raises(ValueError):
        parse_transcript(p)


def test_empty_text_turns_dropped_index_preserved(tmp_path: Path) -> None:
    p = tmp_path / "t.json"
    p.write_text(
        json.dumps(
            {
                "ticker": "AAPL",
                "fiscal_year": 2024,
                "fiscal_period": "Q1",
                "turns": [{"speaker": "A", "text": "   "}, {"speaker": "B", "text": "hello"}],
            }
        ),
        encoding="utf-8",
    )
    nf = parse_transcript(p)
    # Turn 0 (blank) dropped; enumerate index preserved so the kept turn is Turn 001.
    assert list(nf.sections.keys()) == ["Turn 001"]
