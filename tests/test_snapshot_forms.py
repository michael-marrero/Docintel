"""Story 1.1 Task 7 — snapshot ``forms`` scope column (schema + parse).

The per-ticker form scope lives in ``companies.snapshot.csv`` (snapshot-driven,
not env-driven — FND-11 / AD-5). Absent/blank column → the 10-K-only default so
pre-Story-1.1 snapshots parse byte-stable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from docintel_core.config import Settings
from docintel_core.types import CompanyEntry
from docintel_ingest.snapshot import load_snapshot

_HEADER = "ticker,name,sector,market_cap_usd,fiscal_years,snapshot_date,forms\n"
_HEADER_NO_FORMS = "ticker,name,sector,market_cap_usd,fiscal_years,snapshot_date\n"


def test_company_entry_defaults_to_10k_only() -> None:
    e = CompanyEntry(
        ticker="AAPL",
        name="Apple",
        sector="Tech",
        market_cap_usd=1.0,
        fiscal_years=[2024],
        snapshot_date="2026-01-01",
    )
    assert e.forms == ["10-K"]


def test_company_entry_accepts_multi_form() -> None:
    e = CompanyEntry(
        ticker="AAPL",
        name="Apple",
        sector="Tech",
        market_cap_usd=1.0,
        fiscal_years=[2024],
        snapshot_date="2026-01-01",
        forms=["10-K", "10-Q"],
    )
    assert e.forms == ["10-K", "10-Q"]


def test_company_entry_rejects_unknown_form() -> None:
    with pytest.raises(ValidationError):
        CompanyEntry(
            ticker="AAPL",
            name="Apple",
            sector="Tech",
            market_cap_usd=1.0,
            fiscal_years=[2024],
            snapshot_date="2026-01-01",
            forms=["10-K", "DEF 14A"],
        )


def test_load_snapshot_parses_forms_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "snap.csv"
    csv_path.write_text(
        _HEADER + 'AAPL,Apple,Tech,1.0,"[2024]",2026-01-01,"[""10-K"", ""10-Q""]"\n',
        encoding="utf-8",
    )
    rows = load_snapshot(Settings(), csv_path)
    assert rows[0].forms == ["10-K", "10-Q"]


def test_load_snapshot_absent_forms_defaults(tmp_path: Path) -> None:
    csv_path = tmp_path / "snap.csv"
    csv_path.write_text(
        _HEADER_NO_FORMS + 'AAPL,Apple,Tech,1.0,"[2024]",2026-01-01\n',
        encoding="utf-8",
    )
    rows = load_snapshot(Settings(), csv_path)
    assert rows[0].forms == ["10-K"]
