"""Story 1.3 — ingest respects scope (AC-1) + manifest captures it hashably (AC-2)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from docintel_core.config import Settings
from docintel_ingest.manifest import write_manifest
from docintel_ingest.normalize import normalize_all

_HTML = (
    "<html><body><h1>ITEM 1. Business</h1>"
    "<p>We make things and sell them widely across many regions.</p></body></html>"
)


def _seed(tmp_path: Path) -> Settings:
    corpus = tmp_path / "corpus"
    (corpus / "raw" / "AAPL").mkdir(parents=True)
    (corpus / "raw" / "AAPL" / "FY2024.html").write_text(_HTML, encoding="utf-8")
    # An out-of-scope raw file sitting on disk — must be ignored by ingest.
    (corpus / "raw" / "AAPL" / "FY2099.html").write_text(_HTML, encoding="utf-8")
    (corpus / "companies.snapshot.csv").write_text(
        "ticker,name,sector,market_cap_usd,fiscal_years,snapshot_date\n"
        'AAPL,Apple,Tech,3000000000000,"[2024]",2026-07-01\n',
        encoding="utf-8",
    )
    (corpus / ".accession-map.json").write_text(
        json.dumps({"AAPL": {"2024": "0000320193-24-000001"}}), encoding="utf-8"
    )
    return Settings(data_dir=str(tmp_path))


def test_normalize_all_only_processes_in_scope_years(tmp_path: Path) -> None:
    cfg = _seed(tmp_path)
    assert normalize_all(cfg) == 0
    corpus = tmp_path / "corpus"
    assert (corpus / "normalized" / "AAPL" / "FY2024.json").is_file()  # in scope
    # FY2099 is on disk but NOT in the snapshot's fiscal_years → never touched.
    assert not (corpus / "normalized" / "AAPL" / "FY2099.json").exists()


def test_manifest_snapshot_block_captures_scope_hash(tmp_path: Path) -> None:
    cfg = _seed(tmp_path)
    write_manifest(cfg)
    manifest = json.loads((tmp_path / "corpus" / "MANIFEST.json").read_text("utf-8"))
    csv_bytes = (tmp_path / "corpus" / "companies.snapshot.csv").read_bytes()
    # AC-2: the scope is captured in the manifest, reproducible + hashable.
    assert manifest["snapshot"]["sha256"] == hashlib.sha256(csv_bytes).hexdigest()
    assert manifest["snapshot"]["tickers"] == ["AAPL"]
