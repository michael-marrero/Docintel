"""Story 1.1 code-review P8 — offline coverage for the FORM-AWARE orchestrators.

`test_normalize_10q_golden` exercises `normalize_html`/`chunk_filing` directly;
this drives the `_all` orchestrators (`normalize_all` form loop + `write_manifest`
Q-keyed discovery) end-to-end over a `forms=["10-Q"]` fixture snapshot — the exact
paths the code review flagged as untested. Fully offline: the accession sidecar
resolves without a live SEC fetch.
"""

from __future__ import annotations

import json
from pathlib import Path

from docintel_core.config import Settings
from docintel_ingest.chunk import chunk_all
from docintel_ingest.manifest import write_manifest
from docintel_ingest.normalize import normalize_all

_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "sample_10q" / "msft_Q3FY2024_trimmed.html"
)
_ACCESSION = "0000789019-24-000090"


def _seed_corpus(tmp_path: Path) -> Settings:
    corpus = tmp_path / "corpus"
    (corpus / "raw" / "MSFT").mkdir(parents=True)
    (corpus / "raw" / "MSFT" / "Q3FY2024.html").write_text(
        _FIXTURE.read_text("utf-8"), encoding="utf-8"
    )
    (corpus / "companies.snapshot.csv").write_text(
        "ticker,name,sector,market_cap_usd,fiscal_years,snapshot_date,forms\n"
        'MSFT,Microsoft,Technology,3000000000000,[2024],2026-07-01,["10-Q"]\n',
        encoding="utf-8",
    )
    (corpus / ".accession-map.json").write_text(
        json.dumps({"MSFT": {"Q3FY2024": _ACCESSION}}), encoding="utf-8"
    )
    return Settings(data_dir=str(tmp_path))


def test_normalize_and_manifest_are_form_aware(tmp_path: Path) -> None:
    cfg = _seed_corpus(tmp_path)
    corpus = tmp_path / "corpus"

    assert normalize_all(cfg) == 0
    nf_path = corpus / "normalized" / "MSFT" / "Q3FY2024.json"
    assert nf_path.is_file(), "normalize_all did not discover the Q-keyed 10-Q raw file"
    nf = json.loads(nf_path.read_text("utf-8"))
    assert nf["filing_type"] == "10-Q" and nf["fiscal_period"] == "Q3"
    assert "Part I Item 2" in nf["sections"] and "Part II Item 2" in nf["sections"]

    assert chunk_all(cfg) == 0
    assert (corpus / "chunks" / "MSFT" / "Q3FY2024.jsonl").is_file()

    write_manifest(cfg)
    manifest = json.loads((corpus / "MANIFEST.json").read_text("utf-8"))
    q_entries = [f for f in manifest["filings"] if f["filing_type"] == "10-Q"]
    assert len(q_entries) == 1, "10-Q filing missing from MANIFEST.json"
    entry = q_entries[0]
    assert entry["fiscal_period"] == "Q3"
    assert entry["accession"] == _ACCESSION
    assert entry["chunks_path"].endswith("MSFT/Q3FY2024.jsonl")


# --- Story 1.6: 8-K orchestrators (accession-keyed, not year-keyed) ---

_FIXTURE_8K_ACC = "0000320193-24-000075"
_FIXTURE_8K = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "sample_8k"
    / f"aapl_{_FIXTURE_8K_ACC}_trimmed.html"
)


def _seed_8k_corpus(tmp_path: Path) -> Settings:
    corpus = tmp_path / "corpus"
    (corpus / "raw" / "AAPL").mkdir(parents=True)
    (corpus / "raw" / "AAPL" / f"8K-{_FIXTURE_8K_ACC}.html").write_text(
        _FIXTURE_8K.read_text("utf-8"), encoding="utf-8"
    )
    (corpus / "companies.snapshot.csv").write_text(
        "ticker,name,sector,market_cap_usd,fiscal_years,snapshot_date,forms\n"
        'AAPL,Apple,Technology,3000000000000,[2024],2026-07-01,["8-K"]\n',
        encoding="utf-8",
    )
    # No accession sidecar needed — 8-K parses its accession from the filename.
    return Settings(data_dir=str(tmp_path))


def test_8k_normalize_and_manifest_are_form_aware(tmp_path: Path) -> None:
    cfg = _seed_8k_corpus(tmp_path)
    corpus = tmp_path / "corpus"

    assert normalize_all(cfg) == 0
    nf_path = corpus / "normalized" / "AAPL" / f"8K-{_FIXTURE_8K_ACC}.json"
    assert nf_path.is_file(), "normalize_all did not discover the accession-keyed 8-K raw file"
    nf = json.loads(nf_path.read_text("utf-8"))
    assert nf["filing_type"] == "8-K" and nf["fiscal_period"] == "FY"
    assert nf["accession"] == _FIXTURE_8K_ACC
    assert nf["fiscal_year"] == 2024  # derived from accession {cik}-24-{seq}
    assert "Item 2.02" in nf["sections"] and "Item 5.02" in nf["sections"]

    assert chunk_all(cfg) == 0
    assert (corpus / "chunks" / "AAPL" / f"8K-{_FIXTURE_8K_ACC}.jsonl").is_file()

    write_manifest(cfg)
    manifest = json.loads((corpus / "MANIFEST.json").read_text("utf-8"))
    k_entries = [f for f in manifest["filings"] if f["filing_type"] == "8-K"]
    assert len(k_entries) == 1, "8-K filing missing from MANIFEST.json"
    entry = k_entries[0]
    assert entry["accession"] == _FIXTURE_8K_ACC
    assert entry["chunks_path"].endswith(f"AAPL/8K-{_FIXTURE_8K_ACC}.jsonl")


def test_8k_malformed_filename_is_skipped_not_fatal(tmp_path: Path) -> None:
    """A malformed 8-K stem must skip that one file, not crash the whole run (review P1)."""
    cfg = _seed_8k_corpus(tmp_path)
    corpus = tmp_path / "corpus"
    # An accession that has no numeric year segment — an unguarded int() parse
    # would have raised and aborted normalization of every ticker/form.
    (corpus / "raw" / "AAPL" / "8K-garbage.html").write_text("<html></html>", encoding="utf-8")

    rc = normalize_all(cfg)
    assert rc == 1  # the bad file is counted as a failure
    # ...but the good 8-K still normalized — the run did not crash.
    assert (corpus / "normalized" / "AAPL" / f"8K-{_FIXTURE_8K_ACC}.json").is_file()
    assert not (corpus / "normalized" / "AAPL" / "8K-garbage.json").exists()
