"""Story 1.4 — detect newly-published filings for covered companies.

Detection compares the accessions ALREADY in the corpus (read from the committed
normalized JSONs) against the LATEST accessions at SEC. The comparison + no-op
report is a PURE, offline-testable function; the live EDGAR query is `@real`
(network), injected so tests never hit the network. Ingesting the new filings
reuses the already-idempotent fetch/normalize/chunk pipeline (existing chunks
stay byte-identical — no re-baseline).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import structlog
from docintel_core.config import Settings
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from docintel_ingest.snapshot import load_snapshot

log = structlog.stdlib.get_logger(__name__)
_retry_log = logging.getLogger(__name__)


def _key(ticker: str, filing_type: str) -> str:
    return f"{ticker}:{filing_type}"


def corpus_accessions(cfg: Settings) -> dict[str, set[str]]:
    """Accessions currently in the corpus, keyed ``{ticker}:{filing_type}``.

    Reads every ``data/corpus/normalized/{ticker}/*.json`` for snapshot tickers
    and collects its ``accession`` under ``{ticker}:{filing_type}``. Deterministic
    and offline — this is the corpus side of the detection delta.
    """
    norm_root = Path(cfg.data_dir) / "corpus" / "normalized"
    known: dict[str, set[str]] = {}
    for entry in load_snapshot(cfg):
        tdir = norm_root / entry.ticker
        if not tdir.is_dir():
            continue
        for path in sorted(tdir.glob("*.json")):
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
                key = _key(entry.ticker, obj["filing_type"])
                known.setdefault(key, set()).add(obj["accession"])
            except (json.JSONDecodeError, KeyError, OSError) as exc:
                log.warning(
                    "detect_skip_unreadable_normalized", path=str(path), reason=type(exc).__name__
                )
    return known


@dataclass(frozen=True)
class DetectionResult:
    """New accessions per ``{ticker}:{form}``, or up-to-date."""

    new: dict[str, set[str]]  # only non-empty deltas

    @property
    def is_up_to_date(self) -> bool:
        return not self.new

    @property
    def count(self) -> int:
        return sum(len(v) for v in self.new.values())

    def summary(self) -> str:
        if self.is_up_to_date:
            return "Corpus is up to date."
        parts = [f"{key} ({len(accs)})" for key, accs in sorted(self.new.items())]
        return f"{self.count} new filing(s): " + ", ".join(parts)


def detect_new(cfg: Settings, latest: dict[str, set[str]]) -> DetectionResult:
    """Compute the new-filings delta ``latest - corpus`` per ``{ticker}:{form}``.

    Pure + offline: ``latest`` (accessions available at SEC, keyed
    ``{ticker}:{filing_type}``) is injected so this is fully testable without the
    network. Returns only non-empty deltas; all empty → ``is_up_to_date`` (AC-2).
    """
    known = corpus_accessions(cfg)
    new: dict[str, set[str]] = {}
    for key, accs in latest.items():
        delta = set(accs) - known.get(key, set())
        if delta:
            new[key] = delta
    return DetectionResult(new=new)


# --- Live SEC adapter (network; @real only) --------------------------------

_SUPPORTED_FORMS = ("10-K", "10-Q", "8-K")


@retry(
    retry=retry_if_exception_type((OSError, TimeoutError, ConnectionError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(_retry_log, logging.WARNING),
    reraise=True,
)
def _http_get_json(url: str, user_agent: str) -> object:
    """GET a JSON document from an SEC endpoint (tenacity-wrapped; retries only
    network transients, never a 4xx). `@real` — network."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ticker_cik_map(user_agent: str) -> dict[str, str]:
    """Ticker → zero-padded 10-digit CIK from EDGAR's company_tickers.json (`@real`)."""
    data = _http_get_json("https://www.sec.gov/files/company_tickers.json", user_agent)
    out: dict[str, str] = {}
    for row in data.values():  # {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...}
        out[str(row["ticker"]).upper()] = f"{int(row['cik_str']):010d}"
    return out


def fetch_latest_accessions(
    cfg: Settings, forms: tuple[str, ...] = _SUPPORTED_FORMS
) -> dict[str, set[str]]:
    """LIVE EDGAR query — latest accessions per ``{ticker}:{form}`` (`@real`, network).

    Uses the EDGAR submissions API (``data.sec.gov/submissions/CIK{cik}.json``),
    which lists recent filings (accession + form) WITHOUT downloading them. Scoped
    to the snapshot's tickers and the supported forms. Injected into ``detect_new``
    in production; offline tests use a stub ``latest`` dict instead.

    NOTE: validated live (per the Story 1.1 precedent for `@real` fetch paths);
    offline tests never call this.
    """
    ua = cfg.edgar_user_agent
    cik_map = _ticker_cik_map(ua)
    latest: dict[str, set[str]] = {}
    for entry in load_snapshot(cfg):
        cik = cik_map.get(entry.ticker.upper())
        if cik is None:
            log.warning("detect_ticker_no_cik", ticker=entry.ticker)
            continue
        subs = _http_get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", ua)
        recent = subs["filings"]["recent"]  # parallel arrays
        for accession, form in zip(recent["accessionNumber"], recent["form"], strict=False):
            if form in forms:
                latest.setdefault(_key(entry.ticker, form), set()).add(accession)
    return latest
