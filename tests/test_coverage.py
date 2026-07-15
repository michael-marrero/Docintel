"""Story 1.3 — corpus coverage query facade (AC-1 boundary + AC-2 hashability)."""

from __future__ import annotations

import csv
from pathlib import Path

from docintel_core.config import Settings
from docintel_ingest.coverage import load_coverage

_HEADER = ["ticker", "name", "sector", "market_cap_usd", "fiscal_years", "snapshot_date", "forms"]


def _snapshot(tmp_path: Path, rows: list[dict]) -> Settings:
    corpus = tmp_path / "corpus"
    corpus.mkdir(parents=True)
    with (corpus / "companies.snapshot.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return Settings(data_dir=str(tmp_path))


def _row(ticker: str, fiscal_years: str, forms: str) -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "sector": "Tech",
        "market_cap_usd": "3000000000000",
        "fiscal_years": fiscal_years,
        "snapshot_date": "2026-07-01",
        "forms": forms,
    }


def test_in_and_out_of_scope(tmp_path: Path) -> None:
    cfg = _snapshot(tmp_path, [_row("AAPL", "[2023, 2024]", '["10-K", "10-Q"]')])
    cov = load_coverage(cfg)
    assert cov.tickers == ["AAPL"]
    assert cov.is_in_scope("AAPL")
    assert cov.is_in_scope("AAPL", 2024)
    assert cov.is_in_scope("AAPL", 2024, "10-Q")
    assert not cov.is_in_scope("AAPL", 2025)  # year out of scope
    assert not cov.is_in_scope("AAPL", 2024, "8-K")  # form out of scope
    assert not cov.is_in_scope("MSFT")  # unknown ticker → False, never raises
    assert cov.fiscal_years_for("AAPL") == [2023, 2024]
    assert cov.forms_for("AAPL") == ["10-K", "10-Q"]
    assert cov.fiscal_years_for("MSFT") == []
    assert cov.forms_for("MSFT") == []


def test_matrix_and_deterministic_sha(tmp_path: Path) -> None:
    cfg = _snapshot(tmp_path, [_row("AAPL", "[2024]", '["10-K"]')])
    cov = load_coverage(cfg)
    assert cov.as_matrix() == {"AAPL": {"fiscal_years": [2024], "forms": ["10-K"]}}
    # Deterministic (AC-2 reproducible/hashable) — same snapshot → same hash.
    assert cov.sha256() == load_coverage(cfg).sha256()


def test_sha_changes_when_scope_changes(tmp_path: Path) -> None:
    a = load_coverage(_snapshot(tmp_path / "a", [_row("AAPL", "[2024]", '["10-K"]')]))
    b = load_coverage(_snapshot(tmp_path / "b", [_row("AAPL", "[2024]", '["10-K", "8-K"]')]))
    assert a.sha256() != b.sha256()  # a form added to scope changes the hash
