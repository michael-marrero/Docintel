"""Read ``data/corpus/companies.snapshot.csv`` into ``list[CompanyEntry]``.

D-01: the snapshot CSV is the locked source of truth for which companies the
corpus reasons over. Re-running ``make fetch-corpus`` reads THIS file rather
than re-querying any market-cap source — that pinning is what makes ING-04
byte-identity survive across calendar years.

D-02: each row's ``fiscal_years`` column pins the fiscal years to fetch FOR
THAT TICKER. AAPL's FY2024 ended Sep 28 2024; NVDA's FY2024 ended Jan 28
2024; MSFT's FY2024 ended Jun 30 2024 — the fiscal-year LABEL is the same but
the calendar periods are not (Pitfall 1).

The CSV value for ``fiscal_years`` is a JSON-encoded list of integers (e.g.
``"[2023,2024,2025]"``). This module decodes it via ``json.loads`` per
``csv.DictReader`` row and constructs a ``CompanyEntry``. Pydantic v2's
``field_validator`` chain on ``CompanyEntry`` then enforces:

* ticker matches ``^[A-Z.]{1,5}$`` (RESEARCH.md §V5 + T-3-V5-01 —
  path-traversal defense for fetch.py path construction);
* market_cap_usd >= 0;
* fiscal_years non-empty AND every year in [2000, 2030);
* snapshot_date is ISO-8601 ``YYYY-MM-DD``.

Validation errors bubble up — the developer fixes the snapshot row. There is
no silent salvage of malformed rows: the snapshot is small (15 rows), hand
curated, and the failure mode "row 7 of companies.snapshot.csv has an
invalid ticker" is exactly the message we want.

FND-11: this module accepts ``cfg: Settings`` as an argument; it MUST NOT
construct its own ``Settings()`` or read environment variables. The CLI
constructs ``Settings()`` once and passes it in. The grep gate at
``tests/test_no_env_outside_config.py`` enforces this.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import structlog
from docintel_core.config import Settings
from docintel_core.types import CompanyEntry

log = structlog.stdlib.get_logger(__name__)


def load_snapshot(cfg: Settings, path: Path | None = None) -> list[CompanyEntry]:
    """Parse the committed snapshot CSV into a list of ``CompanyEntry``.

    Args:
      cfg: Settings instance. ``cfg.data_dir`` is the base for the default
        snapshot path (``{data_dir}/corpus/companies.snapshot.csv``).
      path: explicit override for the snapshot path. Tests / Wave 2 fetchers
        can point this at a fixture; production callers leave it None to use
        the canonical committed location.

    Returns:
      list[CompanyEntry] in the order the CSV file lists them.

    Raises:
      FileNotFoundError: the snapshot CSV does not exist at the resolved path.
      pydantic.ValidationError: any row fails CompanyEntry validation.
      json.JSONDecodeError: the ``fiscal_years`` cell is not valid JSON.
    """
    if path is None:
        path = Path(cfg.data_dir) / "corpus" / "companies.snapshot.csv"

    rows: list[CompanyEntry] = []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            fiscal_years = json.loads(row["fiscal_years"])
            entry = CompanyEntry(
                ticker=row["ticker"],
                name=row["name"],
                sector=row["sector"],
                market_cap_usd=float(row["market_cap_usd"]),
                fiscal_years=fiscal_years,
                snapshot_date=row["snapshot_date"],
            )
            rows.append(entry)

    log.info(
        "snapshot_loaded",
        path=str(path),
        n_companies=len(rows),
        total_filings=sum(len(r.fiscal_years) for r in rows),
    )
    return rows
