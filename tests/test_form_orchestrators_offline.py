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

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_10q" / "msft_Q3FY2024_trimmed.html"
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
