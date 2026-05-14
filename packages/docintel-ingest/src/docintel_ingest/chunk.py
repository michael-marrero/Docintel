"""BGE-aware paragraph-greedy chunker — Wave 4 of Phase 3.

Cross-references:

* D-10 — token counts come from the real BGE tokenizer
  (``BAAI/bge-small-en-v1.5``, revision-pinned per Pitfall 3). Lives in
  ``docintel_ingest.tokenizer`` (Wave 4 sibling module). Phase 5's
  silent-truncation canary depends on this — using anything else here
  (tiktoken, a wordpiece approximation, etc.) makes the canary a bet
  against tokenizer drift instead of a real retrieval test.
* D-11 — chunk dimensions: ``TARGET_TOKENS=450`` (greedy split point),
  ``OVERLAP_TOKENS=50`` (~11% overlap between adjacent chunks within an
  Item), ``HARD_CAP_TOKENS=500`` (build-fail-if-exceeded — leaves a
  12-token margin under BGE's 512 cap for ``[CLS]``/``[SEP]`` + any
  tokenizer surprise).
* D-12 — chunks NEVER cross Item boundaries. Overlap exists only within
  one Item; the last chunk of each Item may be short. ``item_code`` on
  every chunk is unambiguous (``test_no_chunk_crosses_item`` enforces
  this corpus-wide).
* D-13 — paragraph-greedy splitter. Walk paragraphs (``\\n\\n``-split)
  in order; accumulate until the next paragraph would push us past
  ``TARGET_TOKENS``; then close the chunk, retain a ~50-token overlap
  (the LAST paragraph(s) of the just-closed chunk), and continue.
  Outliers (>``HARD_CAP_TOKENS``) split via sentence regex first
  (CD-06), then hard-token-slice as a last resort.
* D-14 — ``chunk_id`` format ``{ticker}-FY{year}-Item-N[X]-{ordinal:03d}``.
  Ordinal is per-Item (resets at each Item boundary). Example:
  ``AAPL-FY2024-Item-1A-007``.
* D-16 — ``char_span_in_section: tuple[int, int]`` indexes into
  ``NormalizedFiling.sections[item_code]``. Phase 7's hoverable-citation
  UI uses this for the "expand in context" affordance.
* CD-02 — ``sha256_of_text`` is 16-char-truncated hex of UTF-8 bytes of
  the chunk text. Used by MANIFEST.json for fast chunk-identity hashing
  (Wave 5) and by ablation comparison.
* CD-06 — sentence-split regex ``(?<=[.!?])\\s+(?=[A-Z])`` is sufficient
  for 10-K prose (RESEARCH.md line 442). ``pysbd`` is the upgrade path
  if a specific 10-K introduces a sentence-detection failure mode.
* Pitfall 10 — the HARD_CAP loud-fail assertion. If any chunker output
  > 500 BGE tokens, raise ``ValueError``. This is the structural gate
  that makes Phase 5's silent-truncation canary a real test of
  retrieval quality (rather than a chunker-correctness test in
  disguise — RESEARCH.md lines 378-383 + line 583).

Wave 3 outcome note (item-coverage skew): 6 of 15 tickers (AMZN, GOOGL,
LLY, META, WMT, XOM) have empty ``sections`` because their HTML uses
styled-span Item headings the D-07 regex can't match. The chunker
handles that gracefully — ``chunk_filing()`` returns ``[]`` for empty
sections, ``chunk_all()`` continues without raising, and the resulting
empty (zero-byte) JSONL file is still committed so downstream
MANIFEST.json hashing stays consistent.

No network calls — pure CPU. NO ``@retry`` decorator (the same
structural exemption as ``embedder_bge.py`` / ``normalize.py``;
``check_ingest_wraps.sh``'s SDK_PATTERNS match the sec-edgar-downloader
surface only, which does not appear here).

Idempotency: ``chunk_all()`` writes JSONL via
``chunk.model_dump_json()`` (one line per chunk). Pydantic v2 produces
deterministic JSON output (field order matches model definition). Re-
running on byte-identical normalized JSON yields byte-identical JSONL —
that property is what Wave 5's ING-04 idempotency gate
(``tests/test_chunk_idempotency.py``) re-asserts after MANIFEST.json
lands.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path

import structlog
from docintel_core.config import Settings
from docintel_core.types import Chunk, NormalizedFiling

from docintel_ingest.tokenizer import count_tokens, get_bge_tokenizer

# Two-logger pattern (SP-3) — symmetry with embedder_bge.py / fetch.py /
# normalize.py / tokenizer.py. chunk.py has no tenacity-wrapped retry call
# sites (pure CPU, no network), so ``_retry_log`` is unused at module level;
# keep the binding for grep-symmetry with peers.
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)


# D-11 chunk-size discipline. These three constants ARE the chunker
# config that lands in MANIFEST.json's ``chunker`` block in Wave 5.
TARGET_TOKENS = 450
OVERLAP_TOKENS = 50
HARD_CAP_TOKENS = 500  # leaves 12-token margin under BGE's 512

# CD-06 sentence-split regex. Splits on sentence-ending punctuation
# followed by whitespace and an uppercase letter — sufficient for 10-K
# prose per RESEARCH.md line 442. Compiled once at module load (no
# per-call cost).
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


# Canonical 10-K Item titles. Used as a fallback when the section text's
# heading line doesn't expose a parseable title (e.g. the heading
# regex's group(2) doesn't survive whitespace collapse). Per
# RESEARCH.md §10-K Item structure. Items not in this table fall back
# to the bare item_code if no title can be derived.
_CANONICAL_ITEM_TITLES: dict[str, str] = {
    "Item 1": "Business",
    "Item 1A": "Risk Factors",
    "Item 1B": "Unresolved Staff Comments",
    "Item 1C": "Cybersecurity",
    "Item 2": "Properties",
    "Item 3": "Legal Proceedings",
    "Item 4": "Mine Safety Disclosures",
    "Item 5": "Market for Registrant's Common Equity, Related Stockholder Matters and Issuer Purchases of Equity Securities",
    "Item 6": "[Reserved]",
    "Item 7": "Management's Discussion and Analysis of Financial Condition and Results of Operations",
    "Item 7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "Item 8": "Financial Statements and Supplementary Data",
    "Item 9": "Changes in and Disagreements with Accountants on Accounting and Financial Disclosure",
    "Item 9A": "Controls and Procedures",
    "Item 9B": "Other Information",
    "Item 9C": "Disclosure Regarding Foreign Jurisdictions That Prevent Inspections",
    "Item 10": "Directors, Executive Officers and Corporate Governance",
    "Item 11": "Executive Compensation",
    "Item 12": "Security Ownership of Certain Beneficial Owners and Management and Related Stockholder Matters",
    "Item 13": "Certain Relationships and Related Transactions, and Director Independence",
    "Item 14": "Principal Accountant Fees and Services",
    "Item 15": "Exhibits and Financial Statement Schedules",
    "Item 16": "Form 10-K Summary",
}


def _sha256_short(text: str) -> str:
    """16-char truncated sha256 hex of UTF-8 bytes (CD-02).

    Used as the chunk-identity digest in MANIFEST.json (fast hashing)
    and in ablation comparison (does chunker config X produce a
    different chunk set than config Y at the same chunk_id position?).
    NOT a security primitive — this is a content-addressed-storage
    digest over public-record SEC text.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _item_code_to_filename(item_code: str) -> str:
    """``Item 1A`` -> ``Item-1A`` (hyphenated for chunk_id / filename safety per D-14)."""
    return item_code.replace(" ", "-")


def _chunk_id(ticker: str, fiscal_year: int, item_code: str, ordinal: int) -> str:
    """Format ``{ticker}-FY{year}-{item_code_hyphenated}-{ordinal:03d}`` per D-14.

    Example: ``AAPL-FY2024-Item-1A-007``. The format is byte-stable as
    long as Item detection is stable (D-12 + D-13 keep the same paragraph-
    greedy split behaviour for the same input section text). ING-04
    idempotency depends on this stability.
    """
    return f"{ticker}-FY{fiscal_year}-{_item_code_to_filename(item_code)}-{ordinal:03d}"


def _derive_item_title(section_text: str, item_code: str) -> str:
    """Extract the item heading title from section_text, or fall back to the canonical map.

    The normalizer's ``sections[item_code]`` value starts with the heading
    line (``ITEM 1A. Risk Factors``) followed by the body. We attempt a
    one-line match against the same heading regex the normalizer used;
    if that fails (e.g. heading text was lost to whitespace collapse),
    fall back to the canonical 10-K item-title table.
    """
    # Try the first non-empty line as a heading. The normalize.py regex
    # is ``^[ \t]*ITEM[ \t]+(\d{1,2}[A-C]?)(?:[.—\-:]|[ \t])[ \t]*(.+?)[ \t]*$``;
    # we re-run a relaxed variant against the first line only.
    heading_re = re.compile(
        r"^[ \t]*ITEM[ \t]+(\d{1,2}[A-C]?)(?:[.—\-:]|[ \t])[ \t]*(.+?)[ \t]*$",
        flags=re.IGNORECASE,
    )
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = heading_re.match(line)
        if m is not None:
            title = m.group(2).strip()
            if title:
                return title
        break  # only inspect the first non-empty line

    # Fallback: canonical 10-K item-title table.
    return _CANONICAL_ITEM_TITLES.get(item_code, item_code)


def _split_outlier_paragraph(text: str) -> list[str]:
    """Sentence-split then hard-slice fallback for paragraphs > HARD_CAP tokens (D-13 + CD-06).

    Step 1: regex sentence-split (CD-06). For 10-K prose this is
    sufficient — RESEARCH.md "Don't Hand-Roll" line 442 documents
    ``pysbd`` as the upgrade path if a specific filing introduces a
    sentence-detection failure mode.

    Step 2: if any resulting sentence is STILL > HARD_CAP_TOKENS, hard-
    token-slice on token boundaries — encode the sentence with the BGE
    tokenizer, then decode token windows of size ``HARD_CAP_TOKENS``
    back to text. This is the D-13 last-resort fallback ("hard token
    slice"); the resulting chunks may have awkward sentence-mid breaks
    but they remain valid embedding inputs (BGE encodes mid-sentence
    text without complaint).

    Note on byte-stability: ``tok.decode(window, skip_special_tokens=True)``
    is deterministic for a given tokenizer revision, so this fallback
    preserves ING-04 byte-identity across re-runs on the same input.
    """
    parts = SENTENCE_SPLIT_RE.split(text)
    out: list[str] = []
    tok = get_bge_tokenizer()
    for part in parts:
        n = count_tokens(part)
        if n <= HARD_CAP_TOKENS:
            out.append(part)
            continue
        # Hard-token-slice: encode + decode in HARD_CAP_TOKENS-sized windows.
        encoded = tok.encode(part, add_special_tokens=False)
        for i in range(0, len(encoded), HARD_CAP_TOKENS):
            window = encoded[i : i + HARD_CAP_TOKENS]
            decoded = tok.decode(window, skip_special_tokens=True)
            # transformers `decode` is typed as ``str | list[str]`` in some
            # stub versions; in practice a single token-id window always
            # returns ``str``. Cast defensively rather than asserting.
            if isinstance(decoded, list):  # pragma: no cover — defensive
                decoded = " ".join(decoded)
            out.append(decoded)
    return out


def _emit_chunk(
    text: str,
    *,
    ticker: str = "UNKNOWN",
    fiscal_year: int = 0,
    accession: str = "",
    item_code: str = "Item 1",
    item_title: str = "",
    char_start: int = 0,
    char_end: int | None = None,
    ordinal: int = 0,
) -> Chunk:
    """Build a ``Chunk`` from ``text`` + metadata; enforces HARD_CAP loud-fail (Pitfall 10).

    The hard-cap check fires FIRST so this function is also the
    standalone canary used by
    ``tests/test_chunk.py::test_hard_cap_assertion_raises_on_oversize``
    (which calls ``_emit_chunk(oversize_text)`` with no keyword args).
    The keyword-only defaults exist precisely so the canary call
    succeeds at the validation step — the test only checks that
    ``ValueError`` is raised with a "exceeds" substring.

    Real callers in ``_chunk_section()`` always pass every keyword
    argument; the defaults are scaffolding for the unit test of the
    canary itself.

    Args:
        text: The full chunk text (``\\n\\n``-joined paragraphs).
        ticker: e.g. ``"AAPL"``; populates ``Chunk.ticker``.
        fiscal_year: e.g. ``2024``; populates ``Chunk.fiscal_year``.
        accession: SEC accession number; populates ``Chunk.accession``.
        item_code: Canonical item code (``"Item 1A"``).
        item_title: Human-readable item title (``"Risk Factors"``).
        char_start: Start offset into ``NormalizedFiling.sections[item_code]``
            (D-16 citation anchor). When overlap is applied, this is the
            start char of the FIRST overlap paragraph (so the citation
            anchor points at the prose the chunk actually contains, not
            at the post-overlap content).
        char_end: End offset into the section. Defaults to
            ``char_start + len(text)`` when omitted; pass an explicit
            value when the section_text and the chunk text diverge
            (e.g. an outlier fragment whose decoded bytes don't match
            the original section bytes).
        ordinal: Per-Item ordinal starting at 0. The chunk_id is
            zero-padded to 3 digits.

    Returns:
        A fully-populated ``Chunk`` instance with ``prev_chunk_id`` and
        ``next_chunk_id`` set to ``None`` (the second-pass
        ``_wire_neighbors`` populates the linked-list pointers across
        the whole filing).

    Raises:
        ValueError: If ``count_tokens(text) > HARD_CAP_TOKENS`` (Pitfall
        10 loud-fail discipline — Phase 5's silent-truncation canary
        depends on this gate firing rather than a >500-token chunk
        slipping through to the embedder).
    """
    n_tokens = count_tokens(text)
    chunk_id = _chunk_id(ticker, fiscal_year, item_code, ordinal)
    if n_tokens > HARD_CAP_TOKENS:
        # The literal message contains "exceeds" — the canary test
        # matches ``pytest.raises(ValueError, match=r"exceeds")``.
        raise ValueError(f"chunk {chunk_id} exceeds {HARD_CAP_TOKENS} tokens: {n_tokens}")

    end = char_end if char_end is not None else char_start + len(text)
    return Chunk(
        chunk_id=chunk_id,
        ticker=ticker,
        fiscal_year=fiscal_year,
        accession=accession,
        item_code=item_code,
        item_title=item_title or _CANONICAL_ITEM_TITLES.get(item_code, item_code),
        text=text,
        char_span_in_section=(char_start, end),
        n_tokens=n_tokens,
        prev_chunk_id=None,
        next_chunk_id=None,
        sha256_of_text=_sha256_short(text),
    )


# Upper bound on overlap token-count. The plan calls for ~50 tokens of
# overlap; we cap at 2x that (100) to keep the overlap meaningfully small
# even when the trailing paragraph is large. Without this cap a single
# 480-token trailing paragraph would be carried over wholesale and,
# combined with the next ~200-token paragraph, push the next chunk past
# HARD_CAP_TOKENS (the empirical failure mode observed on JNJ/JPM/MSFT/
# NVDA/PG/V FY 2023-2025 with the literal paragraph-aligned overlap).
# This is a Rule 1 (auto-fix bug) deviation from the plan's strict
# paragraph-aligned overlap rule — see the Plan 03-06 SUMMARY for the
# rationale. The plan text explicitly anticipates "sentence-aligned if
# possible, hard-token-aligned otherwise" overlap; this cap is what
# triggers the sentence-aligned fallback.
_OVERLAP_HARD_CAP = 2 * OVERLAP_TOKENS  # 100 tokens


def _truncate_overlap_text(text: str, max_tokens: int) -> str:
    """Trim ``text`` from the LEFT so the trailing ``max_tokens`` survive.

    The function picks the longest tail that fits under ``max_tokens``.
    Prefers a sentence-boundary cut (CD-06 regex) over a hard-token-slice
    cut so the overlap reads as a coherent sentence-prefix rather than a
    mid-sentence stub. Falls back to hard-token-slice if no sentence
    boundary is found within the budget.

    Used by ``_take_overlap`` when a single trailing paragraph exceeds
    ``_OVERLAP_HARD_CAP`` — taking the whole paragraph would carry too
    many tokens into the next chunk and risk HARD_CAP at the next emit.
    """
    if count_tokens(text) <= max_tokens:
        return text

    # Try sentence-aligned: take the trailing sentences whose cumulative
    # token count fits under max_tokens.
    sentences = SENTENCE_SPLIT_RE.split(text)
    accumulated: list[str] = []
    tok_total = 0
    for s in reversed(sentences):
        s_tok = count_tokens(s)
        if tok_total + s_tok > max_tokens:
            break
        accumulated.insert(0, s)
        tok_total += s_tok
    if accumulated:
        return " ".join(accumulated)

    # Hard-token-slice fallback: take the last max_tokens worth of tokens.
    tok = get_bge_tokenizer()
    encoded = tok.encode(text, add_special_tokens=False)
    tail = encoded[-max_tokens:]
    decoded = tok.decode(tail, skip_special_tokens=True)
    if isinstance(decoded, list):  # pragma: no cover — defensive
        decoded = " ".join(decoded)
    return decoded


def _take_overlap(paragraphs: list[str]) -> list[str]:
    """Return the trailing paragraphs of the just-closed chunk as seed for the next chunk.

    Paragraph-aligned overlap when the trailing paragraph fits under
    ``_OVERLAP_HARD_CAP``; otherwise sentence-aligned (or hard-token-
    sliced as last resort) — see ``_truncate_overlap_text``. This is
    the plan's "sentence-aligned if possible, hard-token-aligned
    otherwise" rule made concrete.

    Walks backwards accumulating paragraphs until token sum reaches
    ``OVERLAP_TOKENS`` (or all paragraphs are consumed for a short
    chunk).

    Returns:
        A NEW list (does not mutate ``paragraphs``) containing the
        overlap-seed paragraphs for the next chunk. If the LAST
        paragraph exceeds ``_OVERLAP_HARD_CAP``, the returned list has
        exactly one entry — the right-trimmed tail of that paragraph
        (text bytes only; the next chunk's char_span_in_section anchor
        falls back to 0 in that case).
    """
    if not paragraphs:
        return []

    # Special case: if the LAST paragraph alone exceeds _OVERLAP_HARD_CAP,
    # don't carry the whole thing — take a sentence/token-aligned tail
    # so the next chunk has a coherent overlap of ~OVERLAP_TOKENS
    # tokens rather than the entire trailing paragraph.
    last = paragraphs[-1]
    if count_tokens(last) > _OVERLAP_HARD_CAP:
        return [_truncate_overlap_text(last, OVERLAP_TOKENS)]

    accumulated: list[str] = []
    tok_total = 0
    for para in reversed(paragraphs):
        # If this paragraph would push the overlap past the hard cap,
        # stop accumulating — keep the overlap meaningful but bounded.
        para_tok = count_tokens(para)
        if accumulated and tok_total + para_tok > _OVERLAP_HARD_CAP:
            break
        accumulated.insert(0, para)
        tok_total += para_tok
        if tok_total >= OVERLAP_TOKENS:
            break
    return accumulated


def _chunk_section(
    *,
    item_code: str,
    item_title: str,
    section_text: str,
    ticker: str,
    fiscal_year: int,
    accession: str,
) -> list[Chunk]:
    """Paragraph-greedy splitter for one Item's section text (D-13).

    Walks paragraphs (``\\n\\n``-split) in document order, greedily
    accumulating until the next paragraph would push the running token
    total past ``TARGET_TOKENS``; then closes the chunk via
    ``_emit_chunk()``, retains a ~50-token overlap (the trailing
    paragraphs of the just-closed chunk), and continues.

    Outlier paragraphs (> ``HARD_CAP_TOKENS``) are pre-split via
    ``_split_outlier_paragraph()`` — sentence regex first, then
    hard-token-slice as a last resort (D-13 + CD-06).

    Char-offset tracking:
        ``section_text.index(paragraph)`` gives the first occurrence of
        a paragraph string inside the section. Since 10-K prose
        paragraphs are typically unique within a section (no exact
        duplicates after whitespace normalization), this is safe. When
        the same paragraph DOES recur (e.g. boilerplate "[Reserved]"),
        ``.index`` returns the first match — char_start is then a
        lower-bound anchor rather than the exact occurrence position;
        the citation-anchor invariant (D-16) holds for the FIRST
        occurrence which is the conservative choice.

    Args:
        item_code: Canonical item code (``"Item 1A"``).
        item_title: Human-readable title (``"Risk Factors"``).
        section_text: Full ``NormalizedFiling.sections[item_code]`` text.
        ticker / fiscal_year / accession: Stamped on every emitted Chunk.

    Returns:
        List of ``Chunk`` instances in document order. ``prev_chunk_id``
        and ``next_chunk_id`` are ``None`` here; the caller
        (``chunk_filing``) wires them across Items in a second pass.
    """
    # Split paragraphs and drop blank entries. The normalizer applied
    # paragraph-preserving whitespace collapse, so ``\\n\\n`` splits
    # are reliable separators.
    paragraphs = [p for p in section_text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    # Pre-process outliers: any paragraph > HARD_CAP gets pre-split into
    # sentence-fragments / hard-slice fragments. The replacement
    # fragments slot into the paragraph stream in-place.
    expanded: list[str] = []
    for para in paragraphs:
        if count_tokens(para) > HARD_CAP_TOKENS:
            expanded.extend(_split_outlier_paragraph(para))
        else:
            expanded.append(para)

    chunks: list[Chunk] = []
    cur: list[str] = []
    cur_tokens = 0
    cur_start: int = 0  # char offset of the first paragraph of the current chunk

    for para in expanded:
        para_tok = count_tokens(para)

        # Defensive: outlier pre-processing should have eliminated all
        # > HARD_CAP fragments. If a fragment STILL exceeds the cap
        # (e.g. a single ~500-token "word" with no spaces — pathological),
        # the loud-fail discipline in _emit_chunk catches it below.
        # We don't pre-emptively raise here; the hard-cap check is the
        # one true gate, and we want it firing at emit time so the
        # diagnostic message includes the chunk_id.

        # Rule 1 (auto-fix bug) flush condition: TARGET_TOKENS gates the
        # USUAL split, but HARD_CAP_TOKENS gates EVERY split. Even when
        # we're under TARGET, if adding the next paragraph would push us
        # over HARD_CAP, we MUST flush first. Empirically this matters
        # because overlap can leave cur_tokens at ~OVERLAP_TOKENS (50)
        # but the next paragraph might be ~480 tokens — under TARGET we'd
        # combine to 530+ and violate HARD_CAP at emit time. The fix is
        # this explicit HARD_CAP guard.
        if cur and cur_tokens + para_tok > HARD_CAP_TOKENS:
            flush_now = True
        elif cur and cur_tokens + para_tok > TARGET_TOKENS:
            flush_now = True
        else:
            flush_now = False

        if flush_now:
            # Close current chunk.
            text = "\n\n".join(cur)
            chunk = _emit_chunk(
                text,
                ticker=ticker,
                fiscal_year=fiscal_year,
                accession=accession,
                item_code=item_code,
                item_title=item_title,
                char_start=cur_start,
                char_end=cur_start + len(text),
                ordinal=len(chunks),
            )
            chunks.append(chunk)

            # Seed next chunk with paragraph-aligned overlap. Find the
            # char_start of the FIRST overlap paragraph in section_text.
            overlap = _take_overlap(cur)
            overlap_tokens = sum(count_tokens(p) for p in overlap)
            # Rule 1 (auto-fix bug): overlap + the about-to-be-added
            # paragraph must STILL fit under HARD_CAP. If they don't
            # (e.g. overlap=60 tokens + para_tok=450 = 510 > 500),
            # DROP the overlap entirely — the next chunk starts fresh
            # with the incoming paragraph. Acceptable per the plan's
            # ``hard-token-aligned otherwise`` permission: when adding
            # overlap would break the hard cap, the overlap-mechanism
            # yields gracefully so the cap survives. The cost is one
            # adjacent-chunk pair without textual overlap; the demo's
            # retrieval still works because the paragraph WAS the
            # tail of the prior chunk, and Phase 5's reranker can
            # bridge the gap.
            if overlap and overlap_tokens + para_tok > HARD_CAP_TOKENS:
                overlap = []
                overlap_tokens = 0
            if overlap:
                # ``section_text.index`` from the beginning — paragraph
                # uniqueness within a section is the working assumption.
                cur_start = section_text.find(overlap[0])
                if cur_start < 0:
                    # Defensive fallback (overlap text was reshaped by
                    # outlier slicing and no longer matches a literal
                    # substring): anchor to 0. ING-04 byte-identity is
                    # still preserved because the chunk text + n_tokens
                    # + sha256 are deterministic functions of the
                    # paragraph contents.
                    cur_start = 0
                cur = list(overlap)
                cur_tokens = overlap_tokens
            else:
                cur = []
                cur_tokens = 0
                cur_start = 0

        # Append current paragraph. If cur was just reset (or this is
        # the first iteration), set the char_start anchor.
        if not cur:
            anchor = section_text.find(para)
            cur_start = anchor if anchor >= 0 else 0
        cur.append(para)
        cur_tokens += para_tok

    # Flush the final chunk if anything remains.
    if cur:
        text = "\n\n".join(cur)
        chunk = _emit_chunk(
            text,
            ticker=ticker,
            fiscal_year=fiscal_year,
            accession=accession,
            item_code=item_code,
            item_title=item_title,
            char_start=cur_start,
            char_end=cur_start + len(text),
            ordinal=len(chunks),
        )
        chunks.append(chunk)

    # Defensive: re-assert HARD_CAP on every emitted chunk. ``_emit_chunk``
    # raises during construction, but this second pass would catch any
    # future refactor that bypasses the emit path. Loud-fail discipline.
    for ch in chunks:
        if ch.n_tokens > HARD_CAP_TOKENS:
            raise ValueError(f"chunk {ch.chunk_id} exceeds {HARD_CAP_TOKENS} tokens: {ch.n_tokens}")

    return chunks


def _wire_neighbors(chunks: list[Chunk]) -> list[Chunk]:
    """Second pass: populate prev_chunk_id / next_chunk_id linked-list pointers.

    The linked-list spans across Item boundaries (the document-order
    flow through the filing) — Phase 7's Citation UI uses prev/next to
    render "previous / next chunk" navigation. D-12's "chunks never
    cross Item boundaries" applies to the chunk TEXT, not to the
    prev/next pointers.
    """
    if not chunks:
        return chunks
    return [
        chunk.model_copy(
            update={
                "prev_chunk_id": chunks[i - 1].chunk_id if i > 0 else None,
                "next_chunk_id": chunks[i + 1].chunk_id if i + 1 < len(chunks) else None,
            }
        )
        for i, chunk in enumerate(chunks)
    ]


def chunk_filing(normalized_path: Path) -> list[Chunk]:
    """Read one ``NormalizedFiling`` JSON; return its chunks in document order (D-12).

    Pipeline:
        1. Parse the JSON via ``NormalizedFiling.model_validate_json``.
        2. For each item_code in ``manifest.items_found`` (canonical-
           order subsequence — D-07), run ``_chunk_section()``. Items
           with empty ``sections`` (Wave 3 outcome — AMZN / META / XOM)
           produce no chunks and are skipped silently.
        3. Wire prev/next pointers across the whole filing.

    The empty-sections case yields ``[]`` for those filings — the
    caller (``chunk_all``) writes a zero-byte JSONL file to preserve
    the corpus's 45-file layout for MANIFEST.json hashing.

    Args:
        normalized_path: Absolute or repo-relative path to one
            ``data/corpus/normalized/{ticker}/FY{year}.json`` file.

    Returns:
        ``list[Chunk]`` in document order. Empty if the input has no
        ``sections`` (Wave 3 styled-span-headings filings).
    """
    nf = NormalizedFiling.model_validate_json(normalized_path.read_text(encoding="utf-8"))

    chunks: list[Chunk] = []
    for item_code in nf.manifest.items_found:
        section_text = nf.sections.get(item_code)
        if section_text is None or not section_text.strip():
            # items_found can list an item whose body text is empty
            # (defensive against future normalizer changes); skip.
            continue
        item_title = _derive_item_title(section_text, item_code)
        item_chunks = _chunk_section(
            item_code=item_code,
            item_title=item_title,
            section_text=section_text,
            ticker=nf.ticker,
            fiscal_year=nf.fiscal_year,
            accession=nf.accession,
        )
        chunks.extend(item_chunks)

    chunks = _wire_neighbors(chunks)

    log.info(
        "filing_chunked",
        ticker=nf.ticker,
        fiscal_year=nf.fiscal_year,
        chunk_count=len(chunks),
        items_chunked=len(nf.manifest.items_found),
        sections_present=len(nf.sections),
    )
    return chunks


def chunk_all(
    cfg: Settings,
    normalized_root: Path | None = None,
    out_root: Path | None = None,
) -> int:
    """Iterate every committed normalized JSON; write chunks JSONL under ``data/corpus/chunks``.

    Orchestrator invoked by ``docintel-ingest chunk`` (CLI Plan 03-03).
    Iterates every ``*.json`` under the normalized root (typically
    ``data/corpus/normalized/``), runs ``chunk_filing()``, and writes
    JSONL output to a mirrored path under the chunks root (typically
    ``data/corpus/chunks/``).

    JSONL format: one ``chunk.model_dump_json()`` per line. Pydantic v2
    produces deterministic JSON output (field order matches model
    definition), and ``json.dumps`` is byte-stable across Python
    versions for the same input — together this gives ING-04
    byte-identity.

    Empty filings (Wave 3 styled-span-headings case) get a zero-byte
    JSONL written so the corpus layout has exactly one ``.jsonl`` per
    ``.json``.

    Args:
        cfg: ``Settings`` instance passed by the CLI's single
            ``Settings()`` construction (FND-11). ``cfg.data_dir``
            resolves the default normalized/chunks roots.
        normalized_root: Override for the normalized JSON root. Tests
            point this at a fixture root; production callers leave it
            ``None``.
        out_root: Override for the chunks JSONL output root. Tests use
            this for idempotency comparison; production callers leave
            it ``None``.

    Returns:
        Shell exit code:
            * 0 — every normalized JSON either produced a chunks JSONL
              or was empty (zero-byte JSONL written).
            * 1 — at least one filing raised an unrecoverable error
              (e.g. HARD_CAP loud-fail — surfaces as ``ValueError``
              from ``_emit_chunk``).
    """
    if normalized_root is None:
        normalized_root = Path(cfg.data_dir) / "corpus" / "normalized"
    if out_root is None:
        out_root = Path(cfg.data_dir) / "corpus" / "chunks"

    log.info(
        "chunk_started",
        normalized_root=str(normalized_root),
        out_root=str(out_root),
    )

    t_start = time.perf_counter()
    n_filings = 0
    n_chunks_total = 0
    n_failed = 0
    max_chunk_tokens = 0
    sum_chunk_tokens = 0

    for normalized_path in sorted(normalized_root.rglob("*.json")):
        rel = normalized_path.relative_to(normalized_root)
        out_path = (out_root / rel).with_suffix(".jsonl")

        try:
            chunks = chunk_filing(normalized_path)
        except Exception as exc:
            n_failed += 1
            log.error(
                "filing_chunk_failed",
                normalized_path=str(normalized_path),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            continue

        out_path.parent.mkdir(parents=True, exist_ok=True)
        # JSONL: one line per chunk. Empty filings write a zero-byte
        # file (no newline) — preserves the corpus layout for
        # MANIFEST.json hashing.
        if chunks:
            payload = "\n".join(chunk.model_dump_json() for chunk in chunks) + "\n"
        else:
            payload = ""
        out_path.write_text(payload, encoding="utf-8")

        n_filings += 1
        n_chunks_total += len(chunks)
        for c in chunks:
            sum_chunk_tokens += c.n_tokens
            if c.n_tokens > max_chunk_tokens:
                max_chunk_tokens = c.n_tokens

    duration = time.perf_counter() - t_start
    mean_tokens = (sum_chunk_tokens / n_chunks_total) if n_chunks_total else 0.0
    log.info(
        "chunk_complete",
        n_filings=n_filings,
        n_chunks_total=n_chunks_total,
        n_failed=n_failed,
        mean_chunk_tokens=mean_tokens,
        max_chunk_tokens=max_chunk_tokens,
        duration_sec=duration,
    )

    return 0 if n_failed == 0 else 1


__all__ = [
    "HARD_CAP_TOKENS",
    "OVERLAP_TOKENS",
    "SENTENCE_SPLIT_RE",
    "TARGET_TOKENS",
    "chunk_all",
    "chunk_filing",
]
