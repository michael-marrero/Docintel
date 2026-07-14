"""Story 1.2 — offline transcript orchestrator + AC-2 optional no-op + manifest."""

from __future__ import annotations

import json
from pathlib import Path

from docintel_core.config import Settings
from docintel_ingest.chunk import chunk_all
from docintel_ingest.manifest import write_manifest
from docintel_ingest.transcript import normalize_transcripts_all

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_transcript" / "aapl_Q1FY2024.json"


def _seed(tmp_path: Path, *, with_transcript: bool) -> Settings:
    corpus = tmp_path / "corpus"
    corpus.mkdir(parents=True)
    corpus.joinpath("companies.snapshot.csv").write_text(
        "ticker,name,sector,market_cap_usd,fiscal_years,snapshot_date\n"
        "AAPL,Apple,Technology,3000000000000,[2024],2026-07-01\n",
        encoding="utf-8",
    )
    if with_transcript:
        tdir = corpus / "transcripts" / "AAPL"
        tdir.mkdir(parents=True)
        (tdir / "aapl_Q1FY2024.json").write_text(_FIXTURE.read_text("utf-8"), encoding="utf-8")
    return Settings(data_dir=str(tmp_path))


def test_transcript_orchestrator_end_to_end(tmp_path: Path) -> None:
    cfg = _seed(tmp_path, with_transcript=True)
    corpus = tmp_path / "corpus"

    assert normalize_transcripts_all(cfg) == 0
    nf_path = corpus / "normalized" / "AAPL" / "CALL-Q1FY2024.json"
    assert nf_path.is_file()
    assert json.loads(nf_path.read_text("utf-8"))["filing_type"] == "transcript"

    assert chunk_all(cfg) == 0
    assert (corpus / "chunks" / "AAPL" / "CALL-Q1FY2024.jsonl").is_file()

    write_manifest(cfg)
    manifest = json.loads((corpus / "MANIFEST.json").read_text("utf-8"))
    tx = [f for f in manifest["filings"] if f["filing_type"] == "transcript"]
    assert len(tx) == 1, "transcript missing from MANIFEST.json"
    entry = tx[0]
    assert entry["accession"] == "CALL-2024-02-01"
    assert entry["fiscal_period"] == "Q1"
    assert entry["chunks_path"].endswith("AAPL/CALL-Q1FY2024.jsonl")
    # raw points at the firm-supplied transcript JSON, and its sha256 is recorded.
    assert entry["raw_path"].endswith("transcripts/AAPL/aapl_Q1FY2024.json")
    assert entry["raw_sha256"]


def test_transcripts_absent_is_a_clean_noop(tmp_path: Path) -> None:
    # AC-2: a deployment with no transcripts still succeeds.
    cfg = _seed(tmp_path, with_transcript=False)
    assert normalize_transcripts_all(cfg) == 0
    assert not (tmp_path / "corpus" / "normalized").exists()
