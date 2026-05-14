"""Selectolax-based HTML → ``NormalizedFiling`` JSON normalizer.

Wave 3 of Phase 3: consume the body-only-trimmed raw HTML produced by
`docintel_ingest.fetch.trim_to_body()` and slice it into per-Item sections
that the Wave 4 chunker can read.

Cross-references:
* D-06 — HTML parser is ``selectolax`` (Lexbor backend); CSS-selector API is
  sufficient for the limited extraction the normalizer needs (drop ``<table>``,
  walk the visible text).
* D-07 — Item-boundary detection is regex-on-visible-text + ordering
  validation. The validator records missing items in the per-filing manifest
  but DOES NOT raise — pre-2024 filings legitimately lack Item 1C (Pitfall 5,
  SEC Final Rule 33-11216 made Item 1C mandatory only for FYs ending
  >= 2023-12-15).
* D-08 — Tables dropped entirely for v1. ``fetch.py``'s ``trim_to_body()``
  already pre-strips ``<table>`` blocks at fetch time; the normalizer repeats
  the decompose as defense in depth for hand-authored fixtures or alternate
  input sources that bypass ``trim_to_body``.
* D-09 — Per-filing output JSON schema is ``NormalizedFiling`` from
  ``docintel_core.types``. Keys in ``sections`` use the canonical
  ``"Item N[X]"`` form (space + capital ``I`` + digit + optional A/B/C).
* Pitfall 4 — Unicode whitespace drift. Apply ``unicodedata.normalize("NFC",
  text)``, replace ``\\xa0`` (non-breaking space) with ``' '``, and collapse
  runs of spaces/tabs to a single space BUT preserve ``\\n\\n`` paragraph
  breaks (the chunker's split unit in Wave 4).
* Pitfall 5 — Item 1C absence in pre-2024 filings is NOT an error. The
  ordering validator records the missing item and continues; the per-filing
  ``manifest.items_missing`` surfaces it for human review.

CRITICAL: Pitfall §424 — ``<ix:nonNumeric>`` inner prose MUST survive
normalization. ``fetch.py`` unwraps ix wrappers at fetch time; the
fixture-only path (``tests/fixtures/sample_10k/aapl_FY2024_trimmed.html``)
leaves them as unknown HTML tags, which Lexbor parses as inline elements —
their inner text is preserved naturally by ``body.text(deep=True)``. No
explicit unwrap call is required here; the canary in
``tests/test_normalize.py::test_ix_nonNumeric_prose_preserved`` verifies it.

No network calls — pure CPU. NO ``@retry`` decorator (parallels
``embedder_bge.py``'s structural exemption from ``check_adapter_wraps.sh``;
``check_ingest_wraps.sh`` looks only for the SEC-downloader SDK call-site
patterns (import / constructor / ``.get`` invocation), which do not appear
here — and the wording above intentionally avoids the literal grep targets
so this docstring stays a true negative).

Idempotency: ``normalize_all()`` writes JSON via ``json.dumps(...,
indent=2, sort_keys=True)`` so the on-disk bytes are stable across Python
dict-ordering differences and Pydantic v2 ``model_dump()`` iteration order.
Re-running ``docintel-ingest normalize`` produces byte-identical output for
every filing whose raw HTML is unchanged (modulo the ``fetched_at``
metadata field, which is sidecar-only and is NEVER included in any
byte-identity hash per RESEARCH.md anti-pattern line 428).

DEVIATION (Rule 1 — bug fix) from the literal D-07 regex spec
``^\\s*ITEM\\s+(\\d+[A-C]?)\\s*[.—\\-:]?\\s*(.+?)\\s*$``: that pattern uses
``\\s`` (which matches newlines even in MULTILINE) for the inter-token gaps
between the digit, optional separator, and the title. On the real fetched
MSFT FY2024 filing it produces 100 matches — many sub-headings inside Item
1 are matched as separate Items because ``\\s*[.—\\-:]?\\s*(.+?)\\s*$`` greedily
spans newlines and pairs the bare label ``Item 1`` with the next non-empty
line's text. The fix: restrict the inter-token gaps to ``[ \\t]`` only, and
require an explicit separator (``[.—\\-:]`` OR a single space/tab) between
the code and the title — so a bare ``Item 1`` label at the top of a page
is NOT treated as a heading. After the fix the same MSFT FY2024 filing
detects the expected 23 unique Item codes. Documented in the Plan 03-05
SUMMARY under "Deviations from Plan".
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

import structlog
from docintel_core.config import Settings
from docintel_core.types import NormalizedFiling, NormalizedFilingManifest
from selectolax.lexbor import LexborHTMLParser

from docintel_ingest.snapshot import load_snapshot

# Two-logger pattern (SP-3) — consistency with fetch.py + the broader codebase.
# normalize.py has no tenacity calls (pure CPU, no network) so ``_retry_log``
# is unused at module level; we keep the binding for grep-symmetry with
# fetch.py / embedder_bge.py reviewers may rely on.
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)


# D-07 + RESEARCH.md §Pattern 3 — Item-boundary regex.
#
# Permissive: case-insensitive; tolerates non-breaking space (after NFC
# normalization upstream replaces ``\xa0`` with ``' '``), em-dash, colon,
# period. Anchored to start-of-line in multiline mode so it does NOT match
# in-prose mentions like "as discussed in Item 1A above".
#
# Inter-token gaps use ``[ \t]`` (NOT ``\s``) to prevent the regex from
# spanning newlines. A literal separator OR at least one tab/space is
# REQUIRED between the digit-code and the title — this rejects bare
# "Item 1" labels that appear at page tops in some filings (e.g. MSFT
# FY2024) and would otherwise pair with the next non-empty line.
ITEM_RE = re.compile(
    r"^[ \t]*ITEM[ \t]+(\d+[A-C]?)(?:[.—\-:]|[ \t])[ \t]*(.+?)[ \t]*$",
    flags=re.IGNORECASE | re.MULTILINE,
)


# 10-K canonical Item sequence (post-2023 cybersecurity rule, Item 1C
# mandatory for FYs ending >= 2023-12-15 — SEC Final Rule 33-11216).
# Item 6 became [Reserved] in 2021 (SEC Final Rule 33-10890); many filers
# omit it entirely or include a single "Item 6. [Reserved]" line. Item 1C
# absence pre-2024 is OK (Pitfall 5). Item 9C is included because some
# filers add it (Disclosure Regarding Foreign Jurisdictions That Prevent
# Inspections). Item 16 is "Form 10-K Summary" — optional, many filers
# omit it entirely.
CANONICAL_ITEMS: list[str] = [
    "1",
    "1A",
    "1B",
    "1C",
    "2",
    "3",
    "4",  # PART I
    "5",
    "6",
    "7",
    "7A",
    "8",
    "9",
    "9A",
    "9B",
    "9C",  # PART II
    "10",
    "11",
    "12",
    "13",
    "14",  # PART III
    "15",
    "16",  # PART IV
]


def find_item_boundaries(text: str) -> list[tuple[str, int, int]]:
    """Slice the visible text into ``(item_code, char_start, char_end)`` tuples.

    Returns the list of detected Item-heading boundaries in document order.
    ``char_end`` is the start of the next heading's match (or ``len(text)``
    for the last item). The returned ``item_code`` is normalized to the
    canonical ``"Item N[X]"`` form: ``1a`` -> ``Item 1A``.

    The caller is responsible for any further filtering (e.g. discarding
    table-of-contents matches that share an item code with a later match).
    This function does NOT deduplicate — duplicate matches surface in the
    output and are the upstream caller's concern. ``normalize_html()`` below
    keeps the LAST match per item code (because tables-of-contents are
    typically EARLIER in the document than the actual heading; sections are
    therefore keyed by the deeper match, which has the full body text after
    it).

    Args:
        text: Visible HTML text after NFC + nbsp normalization. The regex
            uses ``[ \\t]`` for inter-token gaps so newlines do NOT bridge
            matches.

    Returns:
        ``list[tuple[item_code, char_start, char_end]]`` in document order.
        Empty list if no headings are detected.
    """
    matches = list(ITEM_RE.finditer(text))
    boundaries: list[tuple[str, int, int]] = []
    for i, m in enumerate(matches):
        code = m.group(1).upper()  # normalize 1a -> 1A
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        boundaries.append((f"Item {code}", m.start(), next_start))
    return boundaries


def _validate_ordering(found_codes: list[str]) -> bool:
    """Verify ``found_codes`` is a SUBSEQUENCE of the canonical Item order.

    Subsequence (NOT strict equality): a filing that detects Items
    ``[Item 1, Item 1A, Item 7]`` is valid because that's a subsequence of
    the canonical 23-item list — even though it skips many items in
    between. This is intentional per D-07 + Pitfall 5: missing items are
    tolerated; out-of-order items are not.

    Two-pointer walk: advance the canonical pointer until it matches each
    found code, in order. If we run out of canonical items before consuming
    all found codes, the ordering is INVALID (out-of-order or duplicate).

    Args:
        found_codes: List of ``"Item N[X]"`` strings in the order detected.

    Returns:
        True iff ``found_codes`` is a subsequence of the canonical sequence.
    """
    canonical = [f"Item {c}" for c in CANONICAL_ITEMS]
    i = 0  # canonical pointer
    for code in found_codes:
        while i < len(canonical) and canonical[i] != code:
            i += 1
        if i >= len(canonical):
            # Ran out of canonical items before consuming all found codes —
            # the found list is NOT a subsequence (out-of-order or duplicate).
            return False
        i += 1  # consume the matched canonical position
    return True


def _normalize_whitespace(text: str) -> str:
    """Apply NFC + nbsp -> space + paragraph-preserving whitespace collapse.

    Pitfall 4 recipe (RESEARCH.md lines 504-508):

      1. ``unicodedata.normalize("NFC", text)`` — canonical form so cross-
         platform byte-identity holds for character pairs that have multiple
         valid encodings (precomposed é vs. e + combining acute, etc.).
      2. Replace ``\\xa0`` (non-breaking space) with regular ``' '``. The
         ``ITEM_RE`` uses ``[ \\t]`` for inter-token gaps; nbsp would NOT
         match a literal tab/space without this step.
      3. Collapse runs of ``[ \\t]+`` to a single space BUT preserve
         ``\\n\\n`` paragraph breaks (the chunker's Wave 4 split unit).
         Implementation: split on ``\\n\\n``, collapse spaces inside each
         paragraph, rejoin with ``\\n\\n``.
      4. Strip leading/trailing whitespace on each paragraph.

    Args:
        text: Raw visible text from ``parser.body.text(deep=True,
            separator='\\n')``.

    Returns:
        Whitespace-normalized text. Paragraph boundaries (``\\n\\n``) are
        preserved; within-paragraph whitespace is collapsed to single spaces.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\xa0", " ")

    # Split on paragraph boundaries (\n\n), collapse intra-paragraph
    # whitespace, rejoin. ``re.sub(r"[ \t]+", " ", p)`` is the inner collapse;
    # we keep single ``\n`` characters inside a paragraph as soft line breaks
    # because the heading-detection regex treats them as record separators.
    paragraphs = text.split("\n\n")
    collapsed = [re.sub(r"[ \t]+", " ", p).strip(" \t") for p in paragraphs]
    return "\n\n".join(collapsed)


def _extract_visible_text(html: str) -> str:
    """Parse HTML with selectolax, drop ``<table>`` elements, return text.

    Per RESEARCH.md "Don't Hand-Roll" line 440: use
    ``parser.body.text(deep=True, separator='\\n')`` for HTML-to-text
    extraction. Regex stripping (``re.sub(r"<[^>]+>", "", html)``) destroys
    block-level structure and produces unreadable text; selectolax preserves
    block boundaries when given a separator.

    The ``<table>`` decompose is defense in depth — ``fetch.py``'s
    ``trim_to_body()`` already pre-strips table blocks at fetch time, but
    a hand-edited raw file (e.g. the sample_10k fixture) might re-introduce
    them. Decomposing again is cheap and idempotent.

    Args:
        html: Raw or trimmed HTML string. For real filings this is the
            output of ``fetch.py``'s ``trim_to_body()`` already on disk
            under ``data/corpus/raw/``. For the sample fixture it is
            hand-authored HTML containing the canary structures.

    Returns:
        Visible body text. Empty string if the HTML has no ``<body>``.
        Whitespace normalization is NOT applied here; the caller invokes
        ``_normalize_whitespace()`` separately so the table-count step
        (which needs the raw text length / byte-identity properties) is
        unaffected by collapse rules.
    """
    parser = LexborHTMLParser(html)

    # Defense in depth — fetch.py drops tables at fetch time, but the
    # sample_10k fixture and any hand-edited raw file may contain them.
    for node in parser.css("table"):
        node.decompose()

    body = parser.body
    if body is None:
        return ""
    return body.text(deep=True, separator="\n")


def _count_tables(html: str) -> int:
    """Count ``<table>`` elements on a fresh parse of the raw HTML.

    The manifest reports this so reviewers can sanity-check that
    ``fetch.py``'s trim happened upstream (count == 0) or, for the
    fixture, that defense-in-depth fires (count >= 1). Counting on a
    fresh parser instance avoids mutating the parser used by
    ``_extract_visible_text``.

    Args:
        html: Raw or trimmed HTML string (same as ``_extract_visible_text``).

    Returns:
        Number of ``<table>`` elements selectolax detects. Zero for
        already-trimmed real filings; positive for the sample fixture.
    """
    return len(LexborHTMLParser(html).css("table"))


def _accession_from_cache(cfg: Settings, ticker: str, fiscal_year: int) -> str:
    """Find the SEC accession number by walking the sec-edgar-downloader cache.

    sec-edgar-downloader stores filings at
    ``{cfg.data_dir}/corpus/.cache/sec-edgar-filings/{ticker}/10-K/{accession}/``.
    Each ``{accession}`` directory contains ``full-submission.txt`` whose
    SEC-HEADER block carries ``CONFORMED PERIOD OF REPORT: YYYYMMDD`` —
    the fiscal-year-end date. We match the period year against the snapshot
    ``fiscal_year`` label.

    The convention (verified across all 15 tickers in the snapshot): the
    snapshot FY label equals the calendar year of the FY-end date. AAPL
    FY2024 ended Sep 28 2024 (label 2024 matches period 20240928); NVDA
    FY2024 ended Jan 28 2024 (label 2024 matches period 20240128); MSFT
    FY2024 ended Jun 30 2024 (label 2024 matches period 20240630). Edge
    case verified: JNJ FY2024 (52-week year) ended Dec 29 2024 — period
    year still 2024.

    Fresh-clone hazard (RESEARCH.md Pitfall + plan-checker Warning #5):
    on a machine that has not run ``docintel-ingest fetch`` (the ``.cache/``
    is gitignored), this function raises ``FileNotFoundError`` with an
    actionable message. Plan 03-07 is the future home for an accession
    sidecar (``data/corpus/.accession/{ticker}/FY{year}.txt``) that would
    eliminate this dependency on the cache.

    Args:
        cfg: ``Settings`` instance. ``cfg.data_dir`` resolves the cache root.
        ticker: Validated stock ticker (e.g. ``"AAPL"``).
        fiscal_year: Snapshot FY label (e.g. ``2024``).

    Returns:
        The accession number string (e.g. ``"0000320193-24-000123"``).

    Raises:
        FileNotFoundError: If the cache directory does not exist OR if no
            cached accession has a ``CONFORMED PERIOD OF REPORT`` year
            matching ``fiscal_year``. The error message names the path
            and suggests ``docintel-ingest fetch`` as the remediation.
    """
    cache_root = Path(cfg.data_dir) / "corpus" / ".cache" / "sec-edgar-filings" / ticker / "10-K"
    if not cache_root.is_dir():
        raise FileNotFoundError(
            f"accession-from-cache lookup failed for {ticker} FY{fiscal_year}: "
            f"no cache directory at {cache_root}. Run `docintel-ingest fetch` "
            f"on a machine with sec.gov access to populate the cache, or commit "
            f"a sidecar at data/corpus/.accession/{ticker}/FY{fiscal_year}.txt "
            f"(future work — Plan 03-07)."
        )

    target_year = str(fiscal_year)
    for accession_dir in sorted(cache_root.iterdir()):
        if not accession_dir.is_dir():
            continue
        submission = accession_dir / "full-submission.txt"
        if not submission.is_file():
            continue
        # full-submission.txt is large (many MB); we only need the header
        # block which appears in the first ~2 KB. Read just enough to find
        # the CONFORMED PERIOD OF REPORT line.
        with submission.open(encoding="utf-8", errors="replace") as fh:
            header = fh.read(4096)
        for line in header.splitlines():
            if "CONFORMED PERIOD OF REPORT" in line:
                # Format: "CONFORMED PERIOD OF REPORT:\t20240928"
                period = line.rsplit(maxsplit=1)[-1].strip()
                if period.startswith(target_year):
                    return accession_dir.name
                break  # found the header line for this accession; not a match

    raise FileNotFoundError(
        f"accession-from-cache lookup failed for {ticker} FY{fiscal_year}: "
        f"no cached accession under {cache_root} has a CONFORMED PERIOD OF "
        f"REPORT year matching {fiscal_year}. Re-run `docintel-ingest fetch` "
        f"or commit a sidecar at data/corpus/.accession/{ticker}/FY{fiscal_year}.txt."
    )


def normalize_html(
    html: str,
    ticker: str,
    fiscal_year: int,
    accession: str,
) -> NormalizedFiling:
    """Normalize one HTML filing into a ``NormalizedFiling``. Pure function.

    Pipeline:

      1. Count ``<table>`` elements on a fresh parse (manifest only).
      2. Extract visible text via selectolax body.text(deep=True), dropping
         ``<table>`` elements as defense-in-depth (D-08).
      3. NFC + nbsp -> space + paragraph-preserving whitespace collapse
         (Pitfall 4).
      4. Slice into ``(item_code, char_start, char_end)`` via
         ``find_item_boundaries()`` (D-07).
      5. For each boundary, write ``sections[item_code]`` = section text
         starting AT the heading line. If the same item code appears multiple
         times (e.g. table-of-contents PLUS actual heading), keep the LAST
         occurrence — that's the one with the full body text after it.
      6. Compute ``items_missing`` against ``CANONICAL_ITEMS`` (Pitfall 5).
      7. Validate ordering against the canonical subsequence (D-07 lenient
         policy — log if invalid, do NOT raise).
      8. Assemble the ``NormalizedFilingManifest`` + ``NormalizedFiling``.

    Args:
        html: Raw or trimmed HTML string (e.g. content of
            ``data/corpus/raw/{ticker}/FY{year}.html``).
        ticker: Stock ticker (uppercase, validated upstream against
            ``^[A-Z.]{1,5}$`` per ``CompanyEntry`` Pydantic validator).
        fiscal_year: Snapshot FY label (e.g. 2024).
        accession: SEC accession number (e.g. ``"0000320193-24-000123"``).
            Caller obtains this via ``_accession_from_cache()`` or a sidecar.

    Returns:
        ``NormalizedFiling`` ready for ``json.dumps(model_dump(),
        sort_keys=True)`` serialization. ``fetched_at`` is stamped to the
        current UTC time; callers that need a stable byte-identity output
        (golden fixtures) must overwrite ``fetched_at`` post-hoc to a known
        value such as ``"1970-01-01T00:00:00+00:00"``.
    """
    tables_dropped = _count_tables(html)
    raw_text = _extract_visible_text(html)
    text = _normalize_whitespace(raw_text)

    boundaries = find_item_boundaries(text)

    # If the same item code appears multiple times (e.g. table-of-contents
    # PLUS actual heading), keep the LAST occurrence — that's the one with
    # the full body text in its span. The boundaries list preserves document
    # order, so a simple last-wins dict assignment captures this.
    sections: dict[str, str] = {}
    for code, start, end in boundaries:
        sections[code] = text[start:end].strip()

    # Re-order sections by canonical Item sequence so the on-disk JSON is
    # human-scannable (Item 1 -> Item 16). Items detected outside the
    # canonical list (extremely rare) are appended in document order.
    canonical_codes = [f"Item {c}" for c in CANONICAL_ITEMS]
    items_found: list[str] = [c for c in canonical_codes if c in sections]
    extras = [c for c in sections if c not in canonical_codes]
    items_found.extend(extras)

    # Items in the canonical sequence that are NOT detected. Pitfall 5
    # legitimizes pre-2024 missing Item 1C; the validator records and
    # surfaces, but does not flag as fatal.
    items_missing = [c for c in canonical_codes if c not in sections]

    # Order validation runs over the document-order codes (not the
    # re-sorted items_found) so a real ordering violation surfaces. We
    # log on invalid ordering but never raise (D-07 lenient policy).
    ordering_codes_in_doc_order = [code for code, _, _ in boundaries]
    # Deduplicate (last-wins) while preserving final document position,
    # mirroring the sections dict assignment above.
    seen: dict[str, int] = {}
    for idx, code in enumerate(ordering_codes_in_doc_order):
        seen[code] = idx
    deduped_ordering = sorted(seen.keys(), key=lambda c: seen[c])
    ordering_valid = _validate_ordering(deduped_ordering)
    if not ordering_valid:
        log.warning(
            "filing_ordering_invalid",
            ticker=ticker,
            fiscal_year=fiscal_year,
            doc_order=deduped_ordering,
            note=(
                "found-codes are not a subsequence of CANONICAL_ITEMS — "
                "investigate filing structure; missing items are tolerated"
            ),
        )

    manifest = NormalizedFilingManifest(
        items_found=items_found,
        items_missing=items_missing,
        ordering_valid=ordering_valid,
        tables_dropped=tables_dropped,
    )

    # ``fetched_at`` is sidecar metadata — RESEARCH.md anti-pattern line 428
    # explicitly forbids including it in any byte-identity hash. We stamp it
    # for traceability but downstream chunker / MANIFEST.json hashing ignores
    # it (Wave 5).
    fetched_at = datetime.now(UTC).isoformat()

    # ``raw_path`` is a relative-to-repo-root string by convention so the
    # committed JSON files are portable across machines (no absolute paths).
    raw_path = f"data/corpus/raw/{ticker}/FY{fiscal_year}.html"

    return NormalizedFiling(
        ticker=ticker,
        fiscal_year=fiscal_year,
        accession=accession,
        fetched_at=fetched_at,
        raw_path=raw_path,
        sections=sections,
        manifest=manifest,
    )


def normalize_all(cfg: Settings, raw_root: Path | None = None) -> int:
    """Normalize every committed raw filing into ``data/corpus/normalized/``.

    Orchestrator invoked by ``docintel-ingest normalize``. Iterates the
    committed snapshot (``data/corpus/companies.snapshot.csv``) and, for
    each (ticker, fiscal_year) pair:

      1. Resolve ``data/corpus/raw/{ticker}/FY{year}.html``. Skip with a
         structured log if the raw file is missing (e.g. fetch.py couldn't
         find that filing on sec.gov for that year — partial-failure
         tolerance per fetch.py).
      2. Read the raw HTML; resolve the SEC accession from the cache
         (``_accession_from_cache``).
      3. Call ``normalize_html()``; serialize via
         ``json.dumps(model_dump(), indent=2, sort_keys=True)`` for
         byte-identity.
      4. Write to ``data/corpus/normalized/{ticker}/FY{year}.json``.

    Args:
        cfg: ``Settings`` instance (passed in from the CLI's single
            ``Settings()`` construction — FND-11 single-env-reader rule).
        raw_root: Optional override for the raw-HTML root. Tests / Wave 4
            chunker tests may pass an explicit fixture root; production
            callers leave it ``None`` (defaults to
            ``{cfg.data_dir}/corpus/raw``).

    Returns:
        Shell exit code:
            * 0 — all filings either normalized successfully or were
              missing-from-fetch (logged but not fatal).
            * 1 — at least one filing produced an unrecoverable error
              (e.g. accession-from-cache lookup failed on a fresh clone).
    """
    if raw_root is None:
        raw_root = Path(cfg.data_dir) / "corpus" / "raw"
    out_root = Path(cfg.data_dir) / "corpus" / "normalized"

    companies = load_snapshot(cfg)
    total = sum(len(c.fiscal_years) for c in companies)

    log.info(
        "normalize_started",
        n_companies=len(companies),
        total_filings=total,
        raw_root=str(raw_root),
        out_root=str(out_root),
    )

    n_succeeded = 0
    n_skipped_raw_missing = 0
    n_failed = 0

    for entry in companies:
        for year in entry.fiscal_years:
            raw_path = raw_root / entry.ticker / f"FY{year}.html"
            if not raw_path.exists():
                n_skipped_raw_missing += 1
                log.warning(
                    "filing_normalize_skip",
                    ticker=entry.ticker,
                    fiscal_year=year,
                    raw_path=str(raw_path),
                    reason="raw_missing",
                )
                continue

            try:
                accession = _accession_from_cache(cfg, entry.ticker, year)
                html = raw_path.read_text(encoding="utf-8")
                nf = normalize_html(html, entry.ticker, year, accession)
            except Exception as exc:
                n_failed += 1
                log.error(
                    "filing_normalize_failed",
                    ticker=entry.ticker,
                    fiscal_year=year,
                    raw_path=str(raw_path),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                continue

            out_path = out_root / entry.ticker / f"FY{year}.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            # ``sort_keys=True`` is the byte-identity guarantor across Python
            # dict-ordering differences and Pydantic v2's model_dump iteration
            # order (PATTERNS.md line 461; mirrors the MANIFEST.json convention).
            out_path.write_text(
                json.dumps(nf.model_dump(), indent=2, sort_keys=True),
                encoding="utf-8",
            )

            n_succeeded += 1
            section_chars_total = sum(len(s) for s in nf.sections.values())
            log.info(
                "filing_normalized",
                ticker=entry.ticker,
                fiscal_year=year,
                accession=accession,
                items_found_count=len(nf.manifest.items_found),
                items_missing_count=len(nf.manifest.items_missing),
                tables_dropped=nf.manifest.tables_dropped,
                ordering_valid=nf.manifest.ordering_valid,
                section_chars_total=section_chars_total,
                out_path=str(out_path),
            )

    log.info(
        "normalize_complete",
        n_succeeded=n_succeeded,
        n_skipped_raw_missing=n_skipped_raw_missing,
        n_failed=n_failed,
        total_filings=total,
    )

    return 0 if n_failed == 0 else 1
