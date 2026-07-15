"""Story 1.5 — build_coverage_view: declared scope + indexed manifest counts."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from docintel_core.config import Settings
from docintel_ingest.coverage import build_coverage_view

_HDR = ["ticker", "name", "sector", "market_cap_usd", "fiscal_years", "snapshot_date", "forms"]


def _row(ticker: str, name: str, sector: str, fiscal_years: str, forms: str) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "sector": sector,
        "market_cap_usd": "3000000000000",
        "fiscal_years": fiscal_years,
        "snapshot_date": "2026-07-01",
        "forms": forms,
    }


def _seed(tmp_path: Path, rows: list[dict], manifest_filings: list[dict] | None = None) -> Settings:
    corpus = tmp_path / "corpus"
    corpus.mkdir(parents=True)
    with (corpus / "companies.snapshot.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_HDR)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    if manifest_filings is not None:
        (corpus / "MANIFEST.json").write_text(
            json.dumps({"filings": manifest_filings}), encoding="utf-8"
        )
    return Settings(data_dir=str(tmp_path))


def test_build_coverage_view_with_manifest(tmp_path: Path) -> None:
    cfg = _seed(
        tmp_path,
        [
            _row("AAPL", "Apple Inc.", "Technology", "[2023, 2024]", '["10-K", "10-Q"]'),
            _row("XOM", "Exxon", "Energy", "[2024]", '["10-K"]'),
        ],
        manifest_filings=[
            {"ticker": "AAPL", "filing_type": "10-K", "fiscal_period": "FY", "fiscal_year": 2023},
            {"ticker": "AAPL", "filing_type": "10-K", "fiscal_period": "FY", "fiscal_year": 2024},
            {
                "ticker": "AAPL",
                "filing_type": "transcript",
                "fiscal_period": "Q1",
                "fiscal_year": 2024,
            },
        ],
    )
    view = build_coverage_view(cfg)

    corpus = view["corpus"]
    assert corpus["company_count"] == 2
    assert corpus["forms"] == ["10-K", "10-Q"]
    assert corpus["fy_min"] == 2023 and corpus["fy_max"] == 2024
    assert corpus["has_transcripts"] is True
    assert corpus["snapshot_date"] == "2026-07-01"

    aapl = next(c for c in view["companies"] if c["ticker"] == "AAPL")
    assert aapl["name"] == "Apple Inc." and aapl["sector"] == "Technology"
    assert aapl["filing_counts"] == {"10-K": 2, "transcript": 1}
    assert aapl["transcript_count"] == 1
    assert aapl["latest_period"] == "FY2024"
    assert aapl["in_corpus"] is True

    xom = next(c for c in view["companies"] if c["ticker"] == "XOM")
    assert xom["filing_counts"] == {} and xom["in_corpus"] is False
    assert xom["latest_period"] is None


def test_build_coverage_view_no_manifest_still_renders_scope(tmp_path: Path) -> None:
    cfg = _seed(tmp_path, [_row("AAPL", "Apple", "Tech", "[2024]", '["10-K"]')])
    view = build_coverage_view(cfg)
    assert view["corpus"]["company_count"] == 1
    assert view["corpus"]["has_transcripts"] is False
    assert view["companies"][0]["in_corpus"] is False
    assert view["companies"][0]["filing_counts"] == {}
    assert view["companies"][0]["latest_period"] is None
