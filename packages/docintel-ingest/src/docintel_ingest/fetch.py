"""Tenacity-wrapped SEC EDGAR fetcher + body-only Inline XBRL trimmer.

This is the only outbound-network call site in Phase 3. All other waves
(normalize, chunk, verify) operate on committed disk artifacts. CI never
exercises this module against live sec.gov — the developer runs `make
fetch-corpus` once on a local machine and commits the resulting
`data/corpus/raw/{ticker}/FY{year}.html` files (D-04).

Cross-references:
* D-03 — fetch source = `sec-edgar-downloader==5.1.0`, the single
  Downloader.get() call site wrapped in tenacity (D-18 / ADP-06 analog).
* D-04 — commit raw HTML under `data/corpus/raw/` (gitignore negation in
  Plan 03-02). The SDK's working `.cache/` stays gitignored.
* D-05 — raw HTML trimmed to body-only at fetch time: drop Inline XBRL
  metadata wrappers, drop tables, unwrap inline-text `<ix:nonNumeric>` /
  `<ix:nonFraction>` (preserve inner prose — see Pitfall §424 in
  RESEARCH.md). Target footprint ~90 MB for 15 cos x 3 FYs.
* D-19 — `Settings.edgar_user_agent` validated at fetch.py entry (Pitfall 8).
* Pitfall 1 — NVDA's late-January fiscal year. The snapshot stores
  `fiscal_years: list[int]` per ticker; `_year_window()` returns an 18-mo
  window covering both late-January and late-September fiscal-year filings.
* Pitfall 2 — `include_amends=False`. The original 10-K (not 10-K/A) is
  the canonical body of the annual report (D-03 + Pitfall 2 rationale).
* Pitfall 7 — single ticker per CIK. The snapshot row validator enforces
  this; we don't redo the check here (defense in depth, not duplication).
* Pitfall 8 — SEC blocks IP for missing/bad User-Agent.
  `_validate_user_agent()` runs before `Downloader(...)` construction,
  raising `ValueError` with an actionable message if the UA is invalid.
* SP-3 two-logger pattern — `_retry_log` (stdlib) for tenacity
  `before_sleep_log`; `log` (structlog bound) for all other lines.

ADP-06 / D-18 grep gate: this file contains `from tenacity import` AND
`from sec_edgar_downloader import Downloader` AND `dl.get(`. The CI gate at
`scripts/check_ingest_wraps.sh` exits zero only if both are present;
removing the tenacity wrap in a future refactor would flip the gate to red.

T-3-V5-01 (path traversal): `CompanyEntry.ticker` is Pydantic-validated
against `^[A-Z.]{1,5}$` at snapshot-load time (Plan 03-03 + docintel-core
`types.py`). Path traversal via ticker is structurally impossible after
validation; this module trusts the validation and constructs paths directly.

T-3-DOS-02 (SEC rate limit): sec-edgar-downloader 5.1.0 integrates
`pyrate-limiter` 4.x which enforces 10 req/sec at the library layer. We do
NOT add a second throttle here — the tenacity retries fire only on
network-layer transients (`OSError`, `TimeoutError`, `ConnectionError`),
NOT on HTTP-429 which the lib absorbs internally.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

# sec_edgar_downloader 5.1.0 has no py.typed marker and its __init__.py uses
# the bare `from ._Downloader import Downloader` form (no `as` re-export). mypy's
# strict implicit-reexport check rejects this; the workspace mypy override sets
# ignore_missing_imports=True for sec_edgar_downloader.* (see repo root
# pyproject.toml [[tool.mypy.overrides]]), but mypy still applies attr-defined
# on the (typed-as-Any) module. The targeted ignore on the `Downloader` import
# below is narrower than a blanket # type: ignore on the whole statement.
import structlog
from docintel_core.config import Settings
from sec_edgar_downloader import Downloader  # type: ignore[attr-defined]
from selectolax.lexbor import LexborHTMLParser
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from docintel_ingest.snapshot import load_snapshot

# Two-logger pattern (SP-3): stdlib logger for tenacity before_sleep_log;
# structlog bound logger for all other structured log lines.
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)


# CSS-escaped Inline XBRL tag selectors. selectolax's Lexbor CSS parser
# rejects raw `:` in tag names (`ix:nonnumeric` raises SelectolaxError);
# the canonical escape `ix\:nonnumeric` is required for both `parser.css()`
# AND `parser.unwrap_tags()` (the latter calls `self.css(tag)` per tag —
# see `selectolax/lexbor/node.pxi unwrap_tags`).
#
# `IX_WRAPPERS_TO_UNWRAP` — inline-text wrappers in narrative prose. The
# XBRL HTML-for-iXBRL working group note states: "Where an `ix:nonNumeric`
# tag uses the default `escape='false'` attribute, the resulting fact value
# is the concatenation of all text nodes that are descendants of the tag."
# In plain English: the human-readable 10-K text lives INSIDE these
# wrappers. They MUST be unwrapped (tag removed, children preserved), not
# decomposed (RESEARCH.md Pitfall §424).
IX_WRAPPERS_TO_UNWRAP: list[str] = [
    r"ix\:nonnumeric",  # narrative text — MUST unwrap, not decompose
    r"ix\:nonfraction",  # numeric facts inline in prose
    r"ix\:fraction",
    r"ix\:numerator",
    r"ix\:denominator",
    r"ix\:continuation",  # text fragments split across blocks
]

# `IX_METADATA_TO_DECOMPOSE` — non-visible XBRL plumbing. These tags carry
# references, resources, hidden facts, footnotes, and namespace metadata
# that the renderer normally hides from human readers. Decompose entirely —
# they are not body text.
IX_METADATA_TO_DECOMPOSE: list[str] = [
    r"ix\:header",  # <ix:header> wraps <ix:references>, <ix:resources>, <ix:hidden>
    r"ix\:references",
    r"ix\:resources",
    r"ix\:hidden",  # hidden facts — NOT visible prose; safe to drop
    r"ix\:tuple",
    r"ix\:exclude",
    r"ix\:relationship",
    r"ix\:footnote",  # numeric-fact footnotes — drop to keep body clean
]

# Regex pre-strip for `<table>...</table>` blocks (D-08). Non-greedy match
# so adjacent tables don't merge. Case-insensitive. DOTALL so newlines
# inside tables don't terminate the match.
#
# Why regex pre-strip instead of pure `parser.css('table').decompose()`:
# the HTML5 parsing algorithm hoists orphan text content out of `<table>`
# (e.g. `<table>x</table>` becomes `x<table></table>` in the parsed tree).
# Decomposing the empty table after parse leaves the hoisted text behind.
# Pre-stripping the raw `<table>...</table>` substring eliminates this
# corner case AND is faster on real 10-K HTML (no parse-time table tree).
# Defense in depth: we still run `parser.css('table').decompose()` after
# parse to clean any well-formed residual tables (e.g. tables nested in
# already-stripped-block leftovers).
_TABLE_BLOCK_RE = re.compile(
    r"<table\b[^>]*>.*?</table>",
    flags=re.IGNORECASE | re.DOTALL,
)


def _validate_user_agent(ua: str) -> None:
    """Sanity-check the SEC User-Agent before constructing a Downloader.

    SEC fair-access policy requires a descriptive User-Agent of the form
    `Name email@example.com`. Requests without one may be 403'd or, worse,
    silently rate-limit-blocked for hours at the IP layer (RESEARCH.md
    Pitfall 8 line 559). The validation is intentionally permissive:
    non-empty AND contains `@`. A more elaborate regex would chase false
    positives — the SEC's enforcement is at the human-review layer, not a
    parsed-format check.

    Args:
        ua: User-Agent string read from `Settings.edgar_user_agent`.

    Raises:
        ValueError: If `ua` is empty/whitespace OR does not contain `@`.
            The message names the env var so the developer knows where to fix.
    """
    if not ua or "@" not in ua:
        raise ValueError(
            "DOCINTEL_EDGAR_USER_AGENT must be set to 'Name email@example.com'. "
            "SEC blocks requests without a valid identifying User-Agent."
        )


def _parse_user_agent(ua: str) -> tuple[str, str]:
    """Split the validated User-Agent string into `(name, email)`.

    The Downloader constructor takes `company_name` and `email_address`
    separately and concatenates them as `f"{name} {email}"` (see
    `sec_edgar_downloader._Downloader:49`). The convention is
    `Firstname Lastname firstname@example.com` — name to the LEFT of the
    last whitespace-separated token, email is the last token. Use rsplit
    so multi-word names ("Jane Q Doe") still resolve correctly.

    Args:
        ua: Pre-validated User-Agent. Caller MUST have run
            `_validate_user_agent(ua)` first — this function trusts that
            `ua` is non-empty and contains `@`.

    Returns:
        Tuple `(name, email)`. Both strings are non-empty.

    Raises:
        ValueError: If the rsplit yields fewer than two parts (e.g. a
            single token with no whitespace before the `@`).
    """
    parts = ua.rsplit(None, 1)
    if len(parts) != 2 or "@" not in parts[1] or not parts[0].strip():
        raise ValueError(
            "DOCINTEL_EDGAR_USER_AGENT must be set to 'Name email@example.com'. "
            "SEC blocks requests without a valid identifying User-Agent."
        )
    return parts[0].strip(), parts[1].strip()


def _year_window(year: int) -> tuple[str, str]:
    """Compute the (after, before) ISO-date window for a fiscal year.

    Per Pitfall 1: NVDA's FY2024 ended Jan 28 2024 (filed late Feb 2024);
    AAPL's FY2024 ended Sep 28 2024 (filed early Nov 2024); MSFT's FY2024
    ended Jun 30 2024 (filed late Jul 2024). All three FY2024 10-Ks file
    between Jan 1 2024 and Jun 30 2025 — an 18-month window catches them
    all without ambiguity (RESEARCH.md line 478).

    Args:
        year: Fiscal year integer (e.g. 2024).

    Returns:
        Tuple `(after, before)` in `YYYY-MM-DD` form for use with
        `Downloader.get(after=..., before=...)`.
    """
    return f"{year}-01-01", f"{year + 1}-06-30"


def _resolve_paths(cfg: Settings) -> tuple[Path, Path]:
    """Resolve and create the raw-output and SDK-cache directories.

    `raw_root` is the committed-artifact root (`data/corpus/raw/`).
    `cache_root` is the gitignored SDK working area (`data/corpus/.cache/`).
    Both are created with `exist_ok=True` so re-runs are no-ops.

    Args:
        cfg: Validated `Settings` instance. `cfg.data_dir` is the base.

    Returns:
        Tuple `(raw_root, cache_root)`. Both directories exist on return.
    """
    raw_root = Path(cfg.data_dir) / "corpus" / "raw"
    cache_root = Path(cfg.data_dir) / "corpus" / ".cache"
    raw_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    return raw_root, cache_root


def trim_to_body(html: str) -> str:
    """Trim a raw 10-K HTML document to a body-only, table-free, ix-free form.

    Pure function — no network, no file I/O. The pipeline is:

      1. Pre-strip `<table>...</table>` blocks via regex (D-08). This
         handles both well-formed and malformed table fragments before
         selectolax parses the tree.
      2. Parse the residual HTML with `LexborHTMLParser`.
      3. Decompose `IX_METADATA_TO_DECOMPOSE` — hidden facts, references,
         resources, footnotes. These are non-visible XBRL plumbing.
      4. Defense-in-depth: decompose any well-formed residual `<table>`
         elements that survived the regex pre-strip (e.g. tables nested
         inside other already-stripped blocks).
      5. Unwrap `IX_WRAPPERS_TO_UNWRAP` — remove the tag but PRESERVE the
         inner text. `ix:nonNumeric` and its siblings carry the report's
         human-readable prose; decomposing them would erase the body
         (Pitfall §424 in RESEARCH.md).
      6. Merge adjacent text nodes left over from unwrap.
      7. Return `parser.html or ""` — `parser.html` returns `None` on
         empty input; coerce to empty string for type safety.

    Args:
        html: Raw HTML string downloaded from sec.gov via
            sec-edgar-downloader's `download_details=True` mode (the
            `primary-document.html` file).

    Returns:
        Body-only HTML string with no `<table>` elements, no
        `ix:metadata` tags, and `ix:nonNumeric`/`ix:nonFraction`/etc.
        wrappers unwrapped to expose their inner text.
    """
    # 1. Regex pre-strip of table blocks (D-08 — drop tables entirely for v1).
    stripped = _TABLE_BLOCK_RE.sub("", html)

    # 2. Parse with Lexbor backend.
    parser = LexborHTMLParser(stripped)

    # 3. Decompose IX metadata blocks (hidden facts, refs, etc.).
    for selector in IX_METADATA_TO_DECOMPOSE:
        for node in parser.css(selector):
            node.decompose()

    # 4. Decompose any well-formed `<table>` elements that survived the
    # regex pre-strip (defense in depth — e.g. inner tables of stripped
    # outer tables can leave residual closing tags that parse as new tables).
    for node in parser.css("table"):
        node.decompose()

    # 5. Unwrap iXBRL inline-text wrappers (REMOVE tag, KEEP children).
    # NOTE: ix:nonNumeric MUST be unwrapped, not decomposed — its inner
    # text is the visible report prose (Pitfall §424).
    parser.unwrap_tags(IX_WRAPPERS_TO_UNWRAP, delete_empty=False)

    # 6. Coalesce adjacent text nodes left over from unwrap.
    parser.merge_text_nodes()

    return parser.html or ""


@retry(
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(4),
    # Network-layer transients only. NOT urllib.HTTPError (4xx auth/permission
    # won't fix by retrying — same exclusion rationale as Phase 2's
    # AuthenticationError exclusion in llm_anthropic.py).
    retry=retry_if_exception_type((OSError, TimeoutError, ConnectionError)),
    before_sleep=before_sleep_log(_retry_log, logging.WARNING),
    reraise=True,
)
def _fetch_one(dl: Downloader, ticker: str, after: str, before: str) -> int:
    """Single SEC fetch via sec-edgar-downloader; retried on network transients only.

    The decorator parameters mirror CD-05 / D-03 (Plan 03-04 verification):
      * `wait_exponential(multiplier=2, min=2, max=30)` — HTTP-tuned backoff
        (Phase 2 used `multiplier=1, min=1, max=20`; HTTP I/O has longer
        natural latencies than local model inference, so the window widens).
      * `stop_after_attempt(4)` — 4 attempts total. Phase 2 uses 5 because
        LLM rate limits are tighter; SEC's pyrate-limiter absorbs the
        common transient class, so 4 is sufficient.
      * `retry_if_exception_type((OSError, TimeoutError, ConnectionError))`
        — network-layer only. HTTP 4xx (urllib.HTTPError) is auth /
        permission / bad-input; retrying makes it worse, not better.
      * `before_sleep=before_sleep_log(_retry_log, logging.WARNING)` —
        every retry logs attempt count + sleep duration. NO silent retries
        (CLAUDE.md operating rule).
      * `reraise=True` — final failure propagates to the caller so the
        partial-failure aggregator can record the failed (ticker, year).

    Args:
        dl: Configured `Downloader` instance. Caller passes the SAME
            `dl` for all tickers; sec-edgar-downloader keeps a
            ticker-to-CIK cache populated at constructor time.
        ticker: Validated stock ticker (e.g. `AAPL`).
        after: ISO date string `YYYY-MM-DD` (lower-inclusive bound).
        before: ISO date string `YYYY-MM-DD` (upper-inclusive bound).

    Returns:
        Number of filings downloaded (typically 0 or 1 for an 18-mo
        single-FY window).

    Raises:
        OSError / TimeoutError / ConnectionError: After 4 retry attempts.
    """
    return dl.get(
        "10-K",
        ticker,
        after=after,
        before=before,
        download_details=True,  # we want primary-document.html, the clean body
        include_amends=False,  # Pitfall 2 — only canonical 10-K, not 10-K/A
    )


def _idempotent_skip(target: Path) -> bool:
    """Return True if the target file is already on disk with non-zero size.

    Idempotency precondition for ING-04 (`make fetch-corpus` is a no-op on
    second run). Short-circuits the sec.gov call before any network I/O,
    so re-running the fetch costs zero outbound requests on already-fetched
    filings.

    Args:
        target: Path to the trimmed HTML output
            (`data/corpus/raw/{ticker}/FY{year}.html`).

    Returns:
        True iff `target` exists AND has size > 0. Zero-byte targets are
        treated as failures (probably an interrupted write).
    """
    return target.exists() and target.stat().st_size > 0


def _locate_primary_doc(cache_root: Path, ticker: str, fresh_dirs: set[Path]) -> Path | None:
    """Find the primary-document HTML produced by the most recent fetch.

    sec-edgar-downloader writes to:
      `{cache_root}/sec-edgar-filings/{TICKER}/10-K/{accession}/primary-document.html`
    (suffix `.html`, possibly `.htm` for older filings — the SDK normalizes
    `.htm` to `.html` in `_orchestrator.py:120`; we glob for any
    `primary-document.*` to handle the rare `.xml` case).

    The `fresh_dirs` argument is the set of accession directories that did
    NOT exist before this `_fetch_one()` call (caller diffs the directory
    listing pre/post-fetch). This guarantees we return the JUST-DOWNLOADED
    filing even when the cache has older accessions for the same ticker.

    Args:
        cache_root: SDK working dir (`{data_dir}/corpus/.cache/`).
        ticker: Stock ticker (uppercase).
        fresh_dirs: Set of accession-number subdirectories newly created
            by the just-completed fetch. Empty set means no new accession
            was downloaded (filing not found for that ticker/year).

    Returns:
        Path to the primary-document HTML, or None if no fresh accession
        produced a primary doc.
    """
    if not fresh_dirs:
        return None
    # If multiple fresh accessions, pick the lexicographically-largest
    # accession number — SEC accession numbers are monotone-increasing
    # within a single filer, so the largest is the most recent filing.
    chosen = max(fresh_dirs, key=lambda p: p.name)
    candidates = sorted(chosen.glob("primary-document.*"))
    if not candidates:
        return None
    # Prefer .html/.htm over .xml when both exist.
    for cand in candidates:
        if cand.suffix.lower() in {".html", ".htm"}:
            return cand
    return candidates[0]


def _ticker_accession_dirs(cache_root: Path, ticker: str) -> set[Path]:
    """List accession-number subdirectories under `{cache_root}/.../{ticker}/10-K/`.

    Used to capture before/after snapshots so `_locate_primary_doc()` can
    identify which accessions were freshly downloaded by `_fetch_one()`.

    Args:
        cache_root: SDK working dir.
        ticker: Stock ticker (uppercase).

    Returns:
        Set of `Path` objects pointing to per-accession directories. Empty
        set if the ticker has no prior cached filings.
    """
    ten_k_dir = cache_root / "sec-edgar-filings" / ticker / "10-K"
    if not ten_k_dir.is_dir():
        return set()
    return {p for p in ten_k_dir.iterdir() if p.is_dir()}


def fetch_all(cfg: Settings, snapshot_path: Path | None = None) -> int:
    """Fetch all (ticker, fiscal_year) filings named in `companies.snapshot.csv`.

    Entry point invoked by the `docintel-ingest fetch` CLI subcommand. Reads
    the committed snapshot, validates the User-Agent, instantiates a single
    `Downloader`, and iterates per-ticker x per-fiscal-year. Each filing is
    fetched via the tenacity-wrapped `_fetch_one()`, then trimmed to body-
    only via `trim_to_body()`, then written to
    `data/corpus/raw/{ticker}/FY{year}.html`.

    Idempotency: filings already present at the target path with non-zero
    size are skipped before the sec.gov call (D-22 precondition for ING-04).

    Partial failure: a single filing missing from SEC (`n_downloaded == 0`)
    or producing no primary doc is logged but does NOT abort the run —
    the function continues to the next filing and reports the failure
    count in the exit code.

    Args:
        cfg: Validated `Settings` instance. Must come from the CLI's single
            `Settings()` construction (FND-11 single-env-reader rule).
        snapshot_path: Optional override for the snapshot CSV path. Tests
            pass an explicit fixture; production callers leave it None.

    Returns:
        Shell exit code:
            * 0 — all filings either fetched successfully or already
              present on disk (idempotent skip).
            * 1 — at least one filing failed to fetch or produced no
              primary document.
    """
    _validate_user_agent(cfg.edgar_user_agent)
    name, email = _parse_user_agent(cfg.edgar_user_agent)

    raw_root, cache_root = _resolve_paths(cfg)
    companies = load_snapshot(cfg, snapshot_path)

    # Single Downloader instance reused across all (ticker, year) calls.
    # sec-edgar-downloader populates a ticker-to-CIK cache at construction
    # time; reusing the instance avoids one API call per ticker.
    dl = Downloader(name, email, download_folder=cache_root)

    total_filings = sum(len(c.fiscal_years) for c in companies)
    log.info(
        "fetch_started",
        n_companies=len(companies),
        total_filings=total_filings,
        raw_root=str(raw_root),
        cache_root=str(cache_root),
    )

    n_succeeded = 0
    n_skipped_idempotent = 0
    n_not_found = 0
    n_failed = 0

    for entry in companies:
        for year in entry.fiscal_years:
            target_path = raw_root / entry.ticker / f"FY{year}.html"

            if _idempotent_skip(target_path):
                n_skipped_idempotent += 1
                log.info(
                    "filing_skipped_idempotent",
                    ticker=entry.ticker,
                    fiscal_year=year,
                    target=str(target_path),
                )
                continue

            after, before = _year_window(year)
            dirs_before = _ticker_accession_dirs(cache_root, entry.ticker)

            try:
                n_downloaded = _fetch_one(dl, entry.ticker, after, before)
            except Exception as exc:  # partial-failure aggregator — re-raise via summary exit code
                n_failed += 1
                log.error(
                    "filing_fetch_failed",
                    ticker=entry.ticker,
                    fiscal_year=year,
                    after=after,
                    before=before,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                continue

            if n_downloaded == 0:
                n_not_found += 1
                log.warning(
                    "filing_not_found",
                    ticker=entry.ticker,
                    fiscal_year=year,
                    after=after,
                    before=before,
                )
                continue

            dirs_after = _ticker_accession_dirs(cache_root, entry.ticker)
            fresh = dirs_after - dirs_before
            primary_doc_path = _locate_primary_doc(cache_root, entry.ticker, fresh)

            if primary_doc_path is None:
                n_failed += 1
                log.error(
                    "primary_doc_missing",
                    ticker=entry.ticker,
                    fiscal_year=year,
                    fresh_accessions=[p.name for p in fresh],
                )
                continue

            raw_html = primary_doc_path.read_text(encoding="utf-8", errors="replace")
            trimmed_html = trim_to_body(raw_html)

            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(trimmed_html, encoding="utf-8")

            n_succeeded += 1
            raw_bytes = len(raw_html)
            trimmed_bytes = len(trimmed_html)
            log.info(
                "filing_fetched",
                ticker=entry.ticker,
                fiscal_year=year,
                accession=primary_doc_path.parent.name,
                raw_bytes=raw_bytes,
                trimmed_bytes=trimmed_bytes,
                trim_ratio=round(trimmed_bytes / max(raw_bytes, 1), 3),
                target=str(target_path),
            )

    log.info(
        "fetch_complete",
        n_succeeded=n_succeeded,
        n_skipped_idempotent=n_skipped_idempotent,
        n_not_found=n_not_found,
        n_failed=n_failed,
        total_filings=total_filings,
    )

    return 0 if n_failed == 0 else 1
