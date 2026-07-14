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
``^\\s*ITEM\\s+(\\d+[A-C]?)\\s*[.—\\-:]?\\s*(.+?)\\s*$`` — two corrections:

  1. ``\\s`` matches newlines even in MULTILINE mode, so the literal pattern
     spans newlines in the inter-token gaps. On real MSFT FY2024 it
     produces 100 matches — sub-headings inside Item 1 get paired with the
     bare label ``Item 1`` from a prior line because the inner
     ``\\s*[.—\\-:]?\\s*(.+?)\\s*$`` greedily walks across newlines. Fix:
     restrict inter-token gaps to ``[ \\t]`` only, and require an
     EXPLICIT separator (``[.—\\-:]`` OR a single tab/space) between the
     digit-code and the title — so a bare ``Item 1`` label at the top of
     a rendered page is NOT a heading.
  2. The literal ``\\d+`` allows arbitrary digit counts; this falsely
     matches "Item 103 of SEC Regulation S-K" (a real Walmart 10-K prose
     reference). Fix: bound to ``\\d{1,2}`` — the canonical 10-K Item
     sequence tops out at Item 16 (Form 10-K Summary).

After both fixes:
  * MSFT FY2024: 23 unique Item codes (was 100 matches / 23 unique).
  * AAPL / HD / JNJ / NVDA / TSLA / PG FY2024+ / V FY2024+: 23/23 perfect.
  * MSFT FY2023 / PG FY2023: 22/23 (missing Item 1C — Pitfall 5
    pre-mandate; legitimate).
  * JPM all FYs: 22/23 (missing optional Item 16).
  * Filers using bold-span-only headings (AMZN, GOOGL, LLY, META, WMT,
    XOM — collectively 6/15 tickers) return 0-4 matches. The D-07 regex
    cannot detect their headings because the literal "ITEM N." prefix
    is not in their visible text (headings are styled spans). This is
    consistent with the plan's lenient policy (RESEARCH.md A2): "missing
    items don't fail the build"; downstream Phase 8 ground-truth eval
    avoids questions targeting those filings. A future hybrid TOC-anchor
    + style-aware fallback (RESEARCH.md deferred ideas) is the V2 path.

Both fixes are documented in the Plan 03-05 SUMMARY under
"Deviations from Plan".
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
#
# The digit count is bounded to ``\d{1,2}`` because the canonical 10-K
# Item sequence tops out at Item 16 (Form 10-K Summary). Without this
# bound, "Item 103 of SEC Regulation S-K" (a real Walmart 10-K prose
# reference) would be matched as a false Item-103 heading. The bound
# is a Rule 1 deviation from the literal D-07 regex and is documented
# in the module docstring's DEVIATION section.
ITEM_RE = re.compile(
    r"^[ \t]*ITEM[ \t]+(\d{1,2}[A-C]?)(?:[.—\-:]|[ \t])[ \t]*(.+?)[ \t]*$",
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


# ---------------------------------------------------------------------------
# 10-Q segmentation (Story 1.1). A 10-Q repeats item NUMBERS across PART I
# (financial) and PART II (other) — e.g. "Item 2" is MD&A in Part I and
# "Unregistered Sales" in Part II. The 10-K last-match dedup would MERGE
# them and drop MD&A, so 10-Q boundaries are keyed by the PART-prefixed code
# ("Part I Item 2"). Gated behind form so the 10-K path is byte-identical.
# ---------------------------------------------------------------------------

# ``PART I`` / ``PART II`` headers. Alternation ``I{1,2}`` + ``\b`` matches
# the longer roman ("II") before falling back to "I". Em-dash / hyphen / colon
# after the roman is optional (filers use "PART I—FINANCIAL INFORMATION",
# "PART I - ...", or a bare newline).
PART_RE = re.compile(
    r"^[ \t]*PART[ \t]+(I{1,2})\b",
    flags=re.IGNORECASE | re.MULTILINE,
)

# Canonical 10-Q item sequence, PART-prefixed. Titles are the SEC-standard
# item titles (Part I = financial/MD&A; Part II = legal/other). Item 1A
# (Risk Factors) lives only in Part II for 10-Q.
CANONICAL_ITEMS_10Q: list[str] = [
    "Part I Item 1",
    "Part I Item 2",
    "Part I Item 3",
    "Part I Item 4",
    "Part II Item 1",
    "Part II Item 1A",
    "Part II Item 2",
    "Part II Item 3",
    "Part II Item 4",
    "Part II Item 5",
    "Part II Item 6",
]

# Roman-numeral → "Part N" label. Only I and II occur in a 10-Q.
_ROMAN_TO_PART = {"I": "Part I", "II": "Part II"}


def find_item_boundaries_10q(text: str) -> list[tuple[str, int, int]]:
    """Slice 10-Q text into ``(part_item_code, char_start, char_end)`` tuples.

    Like :func:`find_item_boundaries` but PART-aware: every ``Item N`` heading
    is prefixed with the most recent ``PART I`` / ``PART II`` header so the
    Part I and Part II items sharing a number stay distinct. Item headings that
    appear BEFORE the first PART header (typically the table-of-contents block
    at the top of the filing) are dropped — they carry no part context and the
    real body headings under a PART header supersede them.

    Returns the boundaries in document order; ``char_end`` is the start of the
    next Item heading OR the next PART header (whichever comes first), or
    ``len(text)`` for the last item. The caller applies last-match dedup on the
    part-prefixed code to collapse any ToC-vs-body duplicate that sits under
    the same PART.

    Args:
        text: Visible filing text after NFC + nbsp + whitespace normalization
            (same input contract as :func:`find_item_boundaries`).

    Returns:
        ``list[tuple[part_item_code, char_start, char_end]]`` where
        ``part_item_code`` is e.g. ``"Part I Item 2"``. Empty list if no
        PART-scoped Item heading is detected.
    """
    # Merge PART and ITEM matches into one document-ordered stream.
    events: list[tuple[int, str, str]] = []  # (pos, kind, payload)
    for m in PART_RE.finditer(text):
        events.append((m.start(), "part", m.group(1).upper()))
    for m in ITEM_RE.finditer(text):
        events.append((m.start(), "item", m.group(1).upper()))
    events.sort(key=lambda e: e[0])

    # First pass: assign each item to its current part, recording heading start.
    current_part: str | None = None
    scoped: list[tuple[str, int]] = []  # (part_item_code, start)
    for pos, kind, payload in events:
        if kind == "part":
            current_part = _ROMAN_TO_PART.get(payload)
        elif current_part is not None:  # drop pre-PART (ToC) items
            scoped.append((f"{current_part} Item {payload}", pos))

    # Second pass: char_end is the start of the next heading of ANY kind
    # (Item OR Part). Using only the next *item* start would fold a trailing
    # PART header — and any prose between it and that Part's first Item — into
    # the previous Part's last item (e.g. Part I Item 4 swallowing
    # "PART II — OTHER INFORMATION").
    heading_starts = sorted(pos for pos, _, _ in events)
    boundaries: list[tuple[str, int, int]] = []
    for code, start in scoped:
        end = next((p for p in heading_starts if p > start), len(text))
        boundaries.append((code, start, end))
    return boundaries


# 8-K heading regex — dotted event codes (``Item 2.02``, ``Item 5.02``). The
# 10-K ``ITEM_RE`` captures ``\d{1,2}[A-C]?`` and does NOT match a dotted code,
# so 8-K needs its own pattern. Kept SEPARATE (not a loosened shared regex) so
# 10-K/10-Q detection is unaffected.
ITEM_RE_8K = re.compile(
    r"^[ \t]*ITEM[ \t]+(\d{1,2}\.\d{2})(?:[.—\-:]|[ \t])[ \t]*(.+?)[ \t]*$",
    flags=re.IGNORECASE | re.MULTILINE,
)


# Canonical 8-K event-item sequence (SEC Form 8-K General Instructions). Used
# for human-scannable section ordering only — 8-K items are event-driven, so a
# given filing reports just the one or two that occurred (items_missing is not
# meaningful and ordering is never a fixed subsequence; see normalize_html).
CANONICAL_ITEMS_8K: list[str] = [
    "Item 1.01",
    "Item 1.02",
    "Item 1.03",
    "Item 1.04",
    "Item 1.05",
    "Item 2.01",
    "Item 2.02",
    "Item 2.03",
    "Item 2.04",
    "Item 2.05",
    "Item 2.06",
    "Item 3.01",
    "Item 3.02",
    "Item 3.03",
    "Item 4.01",
    "Item 4.02",
    "Item 5.01",
    "Item 5.02",
    "Item 5.03",
    "Item 5.04",
    "Item 5.05",
    "Item 5.06",
    "Item 5.07",
    "Item 5.08",
    "Item 6.01",
    "Item 6.02",
    "Item 6.03",
    "Item 6.04",
    "Item 6.05",
    "Item 7.01",
    "Item 8.01",
    "Item 9.01",
]


def find_item_boundaries_8k(text: str) -> list[tuple[str, int, int]]:
    """Slice 8-K text into ``(item_code, char_start, char_end)`` tuples.

    8-K is a FLAT event-item list (no PART structure), with dotted item codes
    (``Item 2.02``). ``char_end`` is the start of the next Item heading (or
    ``len(text)`` for the last) — mirrors :func:`find_item_boundaries` but with
    the dotted :data:`ITEM_RE_8K`. Empty list if no 8-K Item heading is found.
    """
    matches = [(m.start(), f"Item {m.group(1)}") for m in ITEM_RE_8K.finditer(text)]
    boundaries: list[tuple[str, int, int]] = []
    for i, (start, code) in enumerate(matches):
        end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        boundaries.append((code, start, end))
    return boundaries


def _validate_ordering(found_codes: list[str], canonical: list[str] | None = None) -> bool:
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
        found_codes: List of item-code strings in the order detected
            (``"Item N[X]"`` for 10-K, ``"Part I Item N"`` for 10-Q).
        canonical: Canonical ordered code list to validate against. Defaults
            to the 10-K ``CANONICAL_ITEMS`` sequence; 10-Q passes
            ``CANONICAL_ITEMS_10Q`` (already full part-prefixed codes).

    Returns:
        True iff ``found_codes`` is a subsequence of the canonical sequence.
    """
    if canonical is None:
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


def _load_accession_map(cfg: Settings) -> dict[str, dict[str, str]]:
    """Load the committed accession-map sidecar (Rule 2 / Rule 3 deviation).

    The accession map at ``{cfg.data_dir}/corpus/.accession-map.json`` is the
    cross-machine-portable source of truth for ``(ticker, fiscal_year) ->
    accession`` lookups. It is built once on a developer machine (via the
    one-shot script invoked at Plan 03-05 execution time) and committed to
    the repo so CI / fresh clones / future plans (03-06 chunker, 03-07
    manifest) can resolve accessions without needing the gitignored
    ``data/corpus/.cache/`` SDK working directory.

    Why this exists (Rule 3 deviation rationale):

      * The original ``_accession_from_cache`` walked the SDK cache —
        which is gitignored per Pitfall 6 and therefore absent on every
        machine except the developer's after a ``docintel-ingest fetch``.
        Worktree-isolated executors (this very wave's runtime) have no
        access to the main repo's cache either; symlinking from the
        worktree breaks ``tests/test_corpus_layout.py::test_corpus_cache_gitignored``
        (``git check-ignore`` refuses to evaluate paths beyond a symbolic
        link). The sidecar approach resolves both problems at once.

      * Plan 03-05's plan-text explicitly named this as future work
        ("Plan 03-07 makes accession-recording explicit; this plan
        accepts the cache-walking fallback as the dev-machine
        convention"). The convention turned out to be impractical for
        the worktree-execution model, so the sidecar lands here instead.

    Schema (committed JSON):
        {"<TICKER>": {"<FY_YEAR>": "<accession-with-dashes>"}}

    Example::
        {"AAPL": {"2023": "0000320193-23-000106",
                   "2024": "0000320193-24-000123",
                   "2025": "0000320193-25-000079"}}

    Args:
        cfg: ``Settings`` instance. ``cfg.data_dir`` resolves the sidecar
            path (``{data_dir}/corpus/.accession-map.json``).

    Returns:
        The full mapping ``{ticker: {fy_str: accession}}``. Empty dict if
        the sidecar file is absent (callers fall back to direct lookup
        and surface an actionable error).
    """
    sidecar_path = Path(cfg.data_dir) / "corpus" / ".accession-map.json"
    if not sidecar_path.is_file():
        return {}
    with sidecar_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    # Pydantic-free schema validation: every value must be a dict[str, str].
    if not isinstance(data, dict):
        raise ValueError(f"accession-map sidecar at {sidecar_path} is not a JSON object")
    return data


# iXBRL cover-page tags for matching a cached 10-Q to its (quarter, FY).
_QUARTER_FOCUS_RE = re.compile(
    r'name="dei:DocumentFiscalPeriodFocus"[^>]*>\s*(Q[1-3]|FY)\s*<', flags=re.IGNORECASE
)
_FY_FOCUS_RE = re.compile(
    r'name="dei:DocumentFiscalYearFocus"[^>]*>\s*(\d{4})\s*<', flags=re.IGNORECASE
)


def _resolve_accession(
    cfg: Settings,
    ticker: str,
    fiscal_year: int,
    form: str = "10-K",
    fiscal_period: str = "FY",
) -> str:
    """Resolve the SEC accession number for one (ticker, fiscal_year).

    Two-tier lookup, sidecar first:

      1. Read the committed ``data/corpus/.accession-map.json`` (built by
         the Plan 03-05 execution step from the developer machine's SDK
         cache). This is the cross-machine path — works in CI, in
         executor worktrees, in fresh clones.
      2. Fall back to walking the SDK cache at
         ``{cfg.data_dir}/corpus/.cache/sec-edgar-filings/{ticker}/10-K/``
         and matching ``CONFORMED PERIOD OF REPORT`` from each
         ``full-submission.txt``. This path requires
         ``docintel-ingest fetch`` to have run on this machine and the
         cache to not be a symlink (Pitfall: ``git check-ignore`` fails
         on paths beyond symbolic links).
      3. If both fail, raise ``FileNotFoundError`` with a remediation message.

    The convention (verified across all 15 snapshot tickers): the snapshot
    FY label equals the calendar year of the SEC-recorded FY-end date.
    AAPL FY2024 -> Sep 28 2024 -> period 20240928 -> year 2024. JNJ
    FY2024 (52-week year, Dec 29 2024) -> period 20241229 -> year 2024.

    Args:
        cfg: ``Settings`` instance.
        ticker: Validated stock ticker (e.g. ``"AAPL"``).
        fiscal_year: Snapshot FY label (e.g. ``2024``).

    Returns:
        The accession number string (e.g. ``"0000320193-24-000123"``).

    Raises:
        FileNotFoundError: When neither the sidecar nor the SDK cache
            contains an entry for this (ticker, fiscal_year). The
            message names the sidecar path so the developer knows
            where to regenerate the map.
    """
    # Tier 1: sidecar
    mapping = _load_accession_map(cfg)
    # Tier 1: sidecar. 10-K keys by year; 10-Q keys by "{Qn}FY{year}" (the
    # regenerated sidecar carries per-quarter keys). 10-K format unchanged.
    sidecar_key = str(fiscal_year) if form == "10-K" else f"{fiscal_period}FY{fiscal_year}"
    if ticker in mapping and sidecar_key in mapping[ticker]:
        return mapping[ticker][sidecar_key]

    # Tier 2: SDK cache (developer-machine fallback), per-form subdirectory.
    cache_root = Path(cfg.data_dir) / "corpus" / ".cache" / "sec-edgar-filings" / ticker / form
    if cache_root.is_dir():
        for accession_dir in sorted(cache_root.iterdir()):
            if not accession_dir.is_dir():
                continue
            if form == "10-K":
                submission = accession_dir / "full-submission.txt"
                if not submission.is_file():
                    continue
                with submission.open(encoding="utf-8", errors="replace") as fh:
                    header = fh.read(4096)
                for line in header.splitlines():
                    if "CONFORMED PERIOD OF REPORT" in line:
                        period = line.rsplit(maxsplit=1)[-1].strip()
                        if period.startswith(str(fiscal_year)):
                            return accession_dir.name
                        break
            else:
                # 10-Q: match the cached filing's quarter + FY from its iXBRL
                # cover page (DocumentFiscalPeriodFocus / DocumentFiscalYearFocus).
                primary = next(iter(accession_dir.glob("primary-document.*")), None)
                if primary is None:
                    continue
                raw = primary.read_text(encoding="utf-8", errors="replace")
                q = _QUARTER_FOCUS_RE.search(raw)
                y = _FY_FOCUS_RE.search(raw)
                # Require BOTH quarter AND fiscal-year focus to match. Matching
                # on quarter alone (when the FY-focus tag is absent) can bind the
                # wrong accession when the cache holds the same quarter for two
                # fiscal years, mislabeling every chunk's provenance.
                if (
                    q
                    and y
                    and q.group(1).upper() == fiscal_period
                    and y.group(1) == str(fiscal_year)
                ):
                    return accession_dir.name

    raise FileNotFoundError(
        f"accession lookup failed for {ticker} {form} {fiscal_period}FY{fiscal_year}: "
        f"not in sidecar (data/corpus/.accession-map.json) and SDK cache either "
        f"absent or missing this entry. Run `docintel-ingest fetch` on a "
        f"machine with sec.gov access and regenerate the sidecar from the cache."
    )


def normalize_html(
    html: str,
    ticker: str,
    fiscal_year: int,
    accession: str,
    form: str = "10-K",
    fiscal_period: str = "FY",
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
            Caller obtains this via ``_resolve_accession()`` (sidecar-first,
            SDK-cache fallback).

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

    # Form-gated segmentation: 10-Q needs PART-awareness (Item numbers repeat
    # across Part I / Part II); 10-K uses the flat Item finder. Gating keeps
    # the 10-K path byte-identical.
    if form == "10-Q":
        boundaries = find_item_boundaries_10q(text)
    elif form == "8-K":
        boundaries = find_item_boundaries_8k(text)
    else:
        boundaries = find_item_boundaries(text)

    # If the same item code appears multiple times (e.g. table-of-contents
    # PLUS actual heading), keep the LAST occurrence — that's the one with
    # the full body text in its span. The boundaries list preserves document
    # order, so a simple last-wins dict assignment captures this. (For 10-Q,
    # codes are PART-prefixed so Part I Item 2 and Part II Item 2 don't merge.)
    sections: dict[str, str] = {}
    for code, start, end in boundaries:
        sections[code] = text[start:end].strip()

    # Re-order sections by canonical Item sequence so the on-disk JSON is
    # human-scannable. Items detected outside the canonical list (extremely
    # rare) are appended in document order.
    if form == "10-Q":
        canonical_codes = CANONICAL_ITEMS_10Q
    elif form == "8-K":
        canonical_codes = CANONICAL_ITEMS_8K
    else:
        canonical_codes = [f"Item {c}" for c in CANONICAL_ITEMS]
    items_found: list[str] = [c for c in canonical_codes if c in sections]
    extras = [c for c in sections if c not in canonical_codes]
    items_found.extend(extras)

    # Items in the canonical sequence that are NOT detected. Pitfall 5
    # legitimizes pre-2024 missing Item 1C; the validator records and
    # surfaces, but does not flag as fatal. 8-K is event-driven — a filing
    # reports only the events that occurred, so "missing" is not meaningful.
    items_missing = [] if form == "8-K" else [c for c in canonical_codes if c not in sections]

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
    # 8-K items are event-ordered, not a fixed subsequence — ordering is always
    # "valid" (there is nothing to violate). 10-K/10-Q use the subsequence check.
    ordering_valid = (
        True if form == "8-K" else _validate_ordering(deduped_ordering, canonical_codes)
    )
    if form != "8-K" and not ordering_valid:
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
    # 10-K keeps the bare ``FY{year}`` segment (byte-identical); 10-Q prefixes
    # the quarter (``Q3FY{year}``).
    if form == "8-K":
        # 8-K is accession-keyed (many per year); no fiscal period in the path.
        raw_path = f"data/corpus/raw/{ticker}/8K-{accession}.html"
    else:
        period = f"FY{fiscal_year}" if fiscal_period == "FY" else f"{fiscal_period}FY{fiscal_year}"
        raw_path = f"data/corpus/raw/{ticker}/{period}.html"

    return NormalizedFiling(
        ticker=ticker,
        fiscal_year=fiscal_year,
        accession=accession,
        fetched_at=fetched_at,
        raw_path=raw_path,
        sections=sections,
        manifest=manifest,
        filing_type=form,
        fiscal_period=fiscal_period,
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
         (``_resolve_accession`` — sidecar-first lookup).
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

    def _normalize_one(
        ticker: str,
        raw_path: Path,
        form: str,
        fiscal_period: str,
        year: int,
        stem: str,
        accession: str | None = None,
    ) -> None:
        nonlocal n_succeeded, n_skipped_raw_missing, n_failed
        if not raw_path.exists():
            n_skipped_raw_missing += 1
            log.warning(
                "filing_normalize_skip",
                ticker=ticker,
                fiscal_year=year,
                form=form,
                raw_path=str(raw_path),
                reason="raw_missing",
            )
            return
        try:
            # 8-K passes the accession explicitly (parsed from the stem);
            # 10-K/10-Q resolve it via the sidecar/cache.
            if accession is None:
                accession = _resolve_accession(cfg, ticker, year, form, fiscal_period)
            html = raw_path.read_text(encoding="utf-8")
            nf = normalize_html(
                html, ticker, year, accession, form=form, fiscal_period=fiscal_period
            )
        except Exception as exc:
            n_failed += 1
            log.error(
                "filing_normalize_failed",
                ticker=ticker,
                fiscal_year=year,
                form=form,
                raw_path=str(raw_path),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return

        out_path = out_root / ticker / f"{stem}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # ``sort_keys=True`` is the byte-identity guarantor (mirrors MANIFEST.json).
        out_path.write_text(json.dumps(nf.model_dump(), indent=2, sort_keys=True), encoding="utf-8")
        n_succeeded += 1
        log.info(
            "filing_normalized",
            ticker=ticker,
            fiscal_year=year,
            form=form,
            accession=accession,
            items_found_count=len(nf.manifest.items_found),
            out_path=str(out_path),
        )

    for entry in companies:
        for form in entry.forms:
            if form not in ("10-K", "10-Q", "8-K"):
                log.warning(
                    "filing_normalize_skip",
                    ticker=entry.ticker,
                    form=form,
                    reason="form_not_supported",
                )
                continue
            if form == "8-K":
                # 8-K raw files are accession-keyed (8K-{accession}.html), not
                # year-keyed. The accession parses straight from the stem; the
                # fiscal year is the filing year (accession middle segment of
                # {cik}-{yy}-{seq}).
                for raw_path in sorted((raw_root / entry.ticker).glob("8K-*.html")):
                    accession = raw_path.stem[len("8K-") :]
                    fy = 2000 + int(accession.split("-")[1])
                    _normalize_one(
                        entry.ticker, raw_path, "8-K", "FY", fy, raw_path.stem, accession=accession
                    )
                continue
            for year in entry.fiscal_years:
                if form == "10-K":
                    _normalize_one(
                        entry.ticker,
                        raw_root / entry.ticker / f"FY{year}.html",
                        "10-K",
                        "FY",
                        year,
                        f"FY{year}",
                    )
                else:
                    # 10-Q: discover the Q-keyed raw files fetch produced
                    # (Q1FY{year}.html … Q3FY{year}.html); derive the quarter
                    # from each stem. Missing quarters are simply absent.
                    for raw_path in sorted((raw_root / entry.ticker).glob(f"Q?FY{year}.html")):
                        stem = raw_path.stem  # e.g. "Q3FY2024"
                        _normalize_one(
                            entry.ticker, raw_path, "10-Q", stem.split("FY")[0], year, stem
                        )

    log.info(
        "normalize_complete",
        n_succeeded=n_succeeded,
        n_skipped_raw_missing=n_skipped_raw_missing,
        n_failed=n_failed,
        total_filings=total,
    )

    return 0 if n_failed == 0 else 1
