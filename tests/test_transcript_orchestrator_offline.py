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


def _write_transcript(cfg: Settings, ticker_dir: str, name: str, payload: dict) -> None:
    tdir = Path(cfg.data_dir) / "corpus" / "transcripts" / ticker_dir
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / name).write_text(json.dumps(payload), encoding="utf-8")


def test_ticker_mismatch_is_skipped_not_written(tmp_path: Path) -> None:
    # Review fix: a JSON whose ticker disagrees with its dir would produce a
    # broken raw_path — skip loudly instead of crashing the manifest later.
    cfg = _seed(tmp_path, with_transcript=False)
    _write_transcript(
        cfg,
        "AAPL",
        "wrong.json",
        {
            "ticker": "MSFT",
            "fiscal_year": 2024,
            "fiscal_period": "Q1",
            "turns": [{"speaker": "A", "text": "hi"}],
        },
    )
    assert normalize_transcripts_all(cfg) == 1  # counted as a failure
    assert not (tmp_path / "corpus" / "normalized" / "AAPL" / "CALL-Q1FY2024.json").exists()


def test_duplicate_period_collision_is_skipped(tmp_path: Path) -> None:
    # Review fix: two files mapping to the same CALL-{period}FY{year} must not
    # silently clobber — the second is skipped (n_failed>0), the first survives.
    cfg = _seed(tmp_path, with_transcript=False)
    base = {"ticker": "AAPL", "fiscal_year": 2024, "fiscal_period": "Q1"}
    _write_transcript(
        cfg, "AAPL", "a_first.json", {**base, "turns": [{"speaker": "A", "text": "first"}]}
    )
    _write_transcript(
        cfg, "AAPL", "b_second.json", {**base, "turns": [{"speaker": "B", "text": "second"}]}
    )
    assert normalize_transcripts_all(cfg) == 1  # collision counted as failure
    nf = json.loads(
        (Path(cfg.data_dir) / "corpus" / "normalized" / "AAPL" / "CALL-Q1FY2024.json").read_text()
    )
    # sorted glob → "a_first.json" wins; "b_second.json" skipped, not clobbering.
    assert "first" in json.dumps(nf["sections"])


def test_manifest_tolerates_missing_transcript_raw(tmp_path: Path) -> None:
    # Review fix: if the source transcript JSON is gone but normalized+chunks
    # remain, write_manifest skips that entry rather than crashing.
    cfg = _seed(tmp_path, with_transcript=True)
    corpus = tmp_path / "corpus"
    assert normalize_transcripts_all(cfg) == 0
    assert chunk_all(cfg) == 0
    # delete the raw source AFTER the pipeline ran
    (corpus / "transcripts" / "AAPL" / "aapl_Q1FY2024.json").unlink()
    write_manifest(cfg)  # must not raise
    manifest = json.loads((corpus / "MANIFEST.json").read_text("utf-8"))
    assert [f for f in manifest["filings"] if f["filing_type"] == "transcript"] == []
