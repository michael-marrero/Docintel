"""Story 1.4 — new-filing detection (offline core; live SEC query is @real)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from docintel_core.config import Settings
from docintel_ingest.detect import corpus_accessions, detect_new, fetch_latest_accessions


def _seed(tmp_path: Path, normalized: dict[str, list[tuple[str, dict]]]) -> Settings:
    corpus = tmp_path / "corpus"
    corpus.mkdir(parents=True)
    corpus.joinpath("companies.snapshot.csv").write_text(
        "ticker,name,sector,market_cap_usd,fiscal_years,snapshot_date\n"
        + "".join(f'{t},{t},Tech,3000000000000,"[2024]",2026-07-01\n' for t in normalized),
        encoding="utf-8",
    )
    for ticker, files in normalized.items():
        tdir = corpus / "normalized" / ticker
        tdir.mkdir(parents=True)
        for stem, obj in files:
            (tdir / f"{stem}.json").write_text(json.dumps(obj), encoding="utf-8")
    return Settings(data_dir=str(tmp_path))


def test_corpus_accessions_groups_by_ticker_and_form(tmp_path: Path) -> None:
    cfg = _seed(
        tmp_path,
        {
            "AAPL": [
                ("FY2024", {"accession": "acc-10k-24", "filing_type": "10-K"}),
                ("Q1FY2024", {"accession": "acc-10q-24", "filing_type": "10-Q"}),
            ]
        },
    )
    assert corpus_accessions(cfg) == {
        "AAPL:10-K": {"acc-10k-24"},
        "AAPL:10-Q": {"acc-10q-24"},
    }


def test_detect_new_returns_only_the_delta(tmp_path: Path) -> None:
    cfg = _seed(tmp_path, {"AAPL": [("FY2024", {"accession": "old", "filing_type": "10-K"})]})
    result = detect_new(cfg, {"AAPL:10-K": {"old", "new1", "new2"}})
    assert not result.is_up_to_date
    assert result.new == {"AAPL:10-K": {"new1", "new2"}}
    assert result.count == 2
    assert "2 new filing(s)" in result.summary()


def test_detect_new_up_to_date_is_a_noop(tmp_path: Path) -> None:
    # AC-2: no new filings → reports "up to date".
    cfg = _seed(tmp_path, {"AAPL": [("FY2024", {"accession": "a", "filing_type": "10-K"})]})
    result = detect_new(cfg, {"AAPL:10-K": {"a"}})
    assert result.is_up_to_date
    assert result.summary() == "Corpus is up to date."


def test_detection_is_idempotent_once_ingested(tmp_path: Path) -> None:
    # AC-1: a filing that was "new" and got ingested is no longer detected.
    cfg = _seed(
        tmp_path,
        {
            "AAPL": [
                ("FY2024", {"accession": "a", "filing_type": "10-K"}),
                ("FY2025", {"accession": "b", "filing_type": "10-K"}),  # once-new, now in corpus
            ]
        },
    )
    assert detect_new(cfg, {"AAPL:10-K": {"a", "b"}}).is_up_to_date


def test_empty_corpus_all_latest_are_new(tmp_path: Path) -> None:
    cfg = _seed(tmp_path, {"AAPL": []})  # ticker in snapshot, nothing normalized yet
    result = detect_new(cfg, {"AAPL:10-K": {"x", "y"}})
    assert result.new == {"AAPL:10-K": {"x", "y"}}


def test_out_of_scope_form_is_not_reported_new(tmp_path: Path) -> None:
    # Review fix (HIGH): a 10-Q for a 10-K-only ticker is out of scope → never
    # ingested → must NOT be reported "new", else AC-2 ("up to date") never holds.
    cfg = _seed(tmp_path, {"AAPL": [("FY2024", {"accession": "a", "filing_type": "10-K"})]})
    # snapshot has no forms column → AAPL forms defaults to ["10-K"].
    latest = {"AAPL:10-K": {"a"}, "AAPL:10-Q": {"q1", "q2"}}
    result = detect_new(cfg, latest)
    assert result.is_up_to_date  # 10-K current; the out-of-scope 10-Q is ignored


@pytest.mark.real
def test_fetch_latest_accessions_live(tmp_path: Path) -> None:
    # @real: hits data.sec.gov. Skipped in offline CI (-m "not real").
    cfg = _seed(tmp_path, {"AAPL": []})
    latest = fetch_latest_accessions(cfg)
    assert any(k.startswith("AAPL:") for k in latest)
