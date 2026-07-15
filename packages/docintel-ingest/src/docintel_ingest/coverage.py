"""Story 1.3 — corpus coverage scope: a read-only query facade over the snapshot.

The committed ``companies.snapshot.csv`` IS the coverage definition (per-ticker
``fiscal_years`` + ``forms``). This module exposes the "is X in scope?" boundary
the system needs to know what it can answer — the foundation for the coverage
view (Story 1.5) and honest refusal (Story 2.6). It adds a QUERY surface, not a
second source of truth: it reads via ``load_snapshot(cfg)`` (Settings, AD-5),
never the environment.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from docintel_core.config import Settings
from docintel_core.types import CompanyEntry

from docintel_ingest.snapshot import load_snapshot


@dataclass(frozen=True)
class Coverage:
    """Read-only view of the corpus coverage scope (companies x fiscal_years x forms)."""

    companies: tuple[CompanyEntry, ...]

    @property
    def tickers(self) -> list[str]:
        return sorted({c.ticker for c in self.companies})

    def _entry(self, ticker: str) -> CompanyEntry | None:
        for c in self.companies:
            if c.ticker == ticker:
                return c
        return None

    def fiscal_years_for(self, ticker: str) -> list[int]:
        entry = self._entry(ticker)
        return sorted(entry.fiscal_years) if entry else []

    def forms_for(self, ticker: str) -> list[str]:
        entry = self._entry(ticker)
        return list(entry.forms) if entry else []

    def is_in_scope(
        self, ticker: str, fiscal_year: int | None = None, form: str | None = None
    ) -> bool:
        """True iff ``ticker`` is covered (and, when given, the fiscal_year/form too).

        An unknown ticker returns False (never raises). This is the boundary the
        coverage view (1.5) renders and honest refusal (2.6) checks.
        """
        entry = self._entry(ticker)
        if entry is None:
            return False
        if fiscal_year is not None and fiscal_year not in entry.fiscal_years:
            return False
        if form is not None and form not in entry.forms:
            return False
        return True

    def as_matrix(self) -> dict[str, dict[str, list]]:
        """Coverage matrix ``{ticker: {"fiscal_years": [...], "forms": [...]}}``, sorted."""
        return {
            t: {"fiscal_years": self.fiscal_years_for(t), "forms": self.forms_for(t)}
            for t in self.tickers
        }

    def sha256(self) -> str:
        """Deterministic hash of the coverage matrix — a reproducible scope identity."""
        canonical = json.dumps(self.as_matrix(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


def load_coverage(cfg: Settings, snapshot_path: Path | None = None) -> Coverage:
    """Load the corpus coverage from the committed snapshot (single source, AD-5)."""
    return Coverage(companies=tuple(load_snapshot(cfg, snapshot_path)))
