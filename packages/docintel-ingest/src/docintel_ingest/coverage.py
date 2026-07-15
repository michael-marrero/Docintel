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

    def _entries(self, ticker: str) -> list[CompanyEntry]:
        # ALL matching rows — the snapshot may carry duplicate ticker rows
        # (curation concern, not Pydantic-validated), and ingest processes every
        # row, so the facade must UNION them or it would refuse a period the
        # corpus actually contains (the facade is the authority for 2.6 refusal).
        return [c for c in self.companies if c.ticker == ticker]

    def fiscal_years_for(self, ticker: str) -> list[int]:
        return sorted({y for e in self._entries(ticker) for y in e.fiscal_years})

    def forms_for(self, ticker: str) -> list[str]:
        # Sorted (like fiscal_years_for) so as_matrix()/sha256() are a canonical
        # scope identity independent of the CSV's forms ordering.
        return sorted({f for e in self._entries(ticker) for f in e.forms})

    def is_in_scope(
        self, ticker: str, fiscal_year: int | None = None, form: str | None = None
    ) -> bool:
        """True iff ``ticker`` is covered (and, when given, the fiscal_year/form too).

        An unknown ticker returns False (never raises). This is the boundary the
        coverage view (1.5) renders and honest refusal (2.6) checks. Duplicate
        ticker rows are unioned so the facade agrees with what ingest indexes.
        """
        entries = self._entries(ticker)
        if not entries:
            return False
        if fiscal_year is not None and fiscal_year not in {
            y for e in entries for y in e.fiscal_years
        }:
            return False
        if form is not None and form not in {f for e in entries for f in e.forms}:
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


# Period recency ordering (annual is "latest" within a fiscal year).
_PERIOD_ORDER = {"FY": 5, "Q4": 4, "Q3": 3, "Q2": 2, "Q1": 1}


def _fmt_latest_period(periods: list[tuple[int, str]]) -> str | None:
    """Format the most-recent (fiscal_year, period) as e.g. ``FY2024`` / ``FY2024 · Q3``."""
    if not periods:
        return None
    year = max(y for y, _ in periods)
    within = [p for y, p in periods if y == year]
    best = max(within, key=lambda p: _PERIOD_ORDER.get(p, 0))
    return f"FY{year}" if best == "FY" else f"FY{year} · {best}"


def build_coverage_view(cfg: Settings) -> dict:
    """Assemble the browsable coverage view (Story 1.5): declared scope + indexed counts.

    Scope (name/sector/forms/fiscal_years) comes from the coverage facade; per-company
    filing counts, transcript count, and latest indexed period come from the corpus
    ``MANIFEST.json`` (the published corpus artifact). JSON-ready and deterministic;
    an absent/unreadable manifest yields zero indexed counts (scope still renders).
    """
    companies = load_snapshot(cfg)

    # Merge duplicate ticker rows (the snapshot may carry them — 1.3 review): first
    # row wins name/sector, forms/fiscal_years union. One rendered row per ticker,
    # so len(rows) == company_count (no "Showing 19 of 18").
    merged: dict[str, dict] = {}
    order: list[str] = []
    for c in companies:
        if c.ticker not in merged:
            merged[c.ticker] = {
                "name": c.name,
                "sector": c.sector,
                "forms": set(c.forms),
                "fiscal_years": set(c.fiscal_years),
            }
            order.append(c.ticker)
        else:
            merged[c.ticker]["forms"].update(c.forms)
            merged[c.ticker]["fiscal_years"].update(c.fiscal_years)

    # Index the published manifest's filings by ticker (best-effort; absent/
    # unreadable → empty; a filing missing "ticker" is skipped, not fatal to the rest).
    by_ticker: dict[str, list[dict]] = {}
    manifest_path = Path(cfg.data_dir) / "corpus" / "MANIFEST.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {"filings": []}
        for filing in manifest.get("filings", []):
            ticker = filing.get("ticker")
            if ticker:
                by_ticker.setdefault(ticker, []).append(filing)

    rows: list[dict] = []
    for ticker in order:
        info = merged[ticker]
        filings = by_ticker.get(ticker, [])
        counts: dict[str, int] = {}
        transcript_count = 0
        periods: list[tuple[int, str]] = []
        for f in filings:
            ftype = f.get("filing_type", "10-K")
            counts[ftype] = counts.get(ftype, 0) + 1
            if ftype == "transcript":
                transcript_count += 1
            else:
                # A malformed fiscal_year (null / non-numeric) must not 500 the
                # endpoint — the module's contract is graceful degradation.
                try:
                    fy = int(f.get("fiscal_year", 0))
                except (TypeError, ValueError):
                    continue
                periods.append((fy, str(f.get("fiscal_period", "FY"))))
        rows.append(
            {
                "ticker": ticker,
                "name": info["name"],
                "sector": info["sector"],
                "forms": sorted(info["forms"]),
                "fiscal_years": sorted(info["fiscal_years"]),
                "filing_counts": dict(sorted(counts.items())),
                "transcript_count": transcript_count,
                "latest_period": _fmt_latest_period(periods),
                "in_corpus": bool(filings),
            }
        )

    all_years = sorted({y for c in companies for y in c.fiscal_years})
    corpus = {
        "company_count": len(order),
        "forms": sorted({f for c in companies for f in c.forms}),
        "fy_min": all_years[0] if all_years else None,
        "fy_max": all_years[-1] if all_years else None,
        "has_transcripts": any(r["transcript_count"] > 0 for r in rows),
        "snapshot_date": companies[0].snapshot_date if companies else "",
    }
    return {"corpus": corpus, "companies": rows}
