"""Shared Pydantic data-transfer models for docintel.

CD-01 decision: Chunk + NormalizedFiling + NormalizedFilingManifest +
CompanyEntry live HERE (not in docintel_ingest.types) so Phase 4 / 5 / 7 can
import them without depending on the ingest package. The schema is a contract,
not an ingest implementation detail. Adapter DTOs (TokenUsage, CompletionResponse,
JudgeVerdict, RerankedDoc, AdapterBundle) live separately in
``docintel_core/adapters/types.py`` per CD-05.

D-15: Chunk fields are chunk_id, ticker, fiscal_year, accession, item_code,
      item_title, text, char_span_in_section, n_tokens, prev_chunk_id,
      next_chunk_id (per CONTEXT.md). All four wave-shipped chunk attributes
      flow through this single class.
D-16: char_span_in_section indexes into NormalizedFiling.sections[item_code] —
      the citation anchor Phase 7's Citation will surface to the UI.
D-09: NormalizedFiling schema — sections is a dict[str, str] keyed by the
      normalized item_code ('Item 1A' form). manifest sub-model surfaces
      items_found, items_missing, ordering_valid, tables_dropped so the
      per-filing manifest is part of the typed contract (not a side file).
CD-02: Chunk.sha256_of_text is the 16-char truncated hex of sha256(text) so
      MANIFEST.json hashing stays fast AND chunks remain diffable in git.

Pitfall 1 (NVDA): CompanyEntry.fiscal_years is a list[int] PER ROW (not a
      global FY range). NVDA's FY2024 ended in late January 2024; AAPL's
      FY2024 ended in late September 2024. The per-ticker list IS the fix.
RESEARCH.md §Security Domain V5: CompanyEntry.ticker is validated against
      ``^[A-Z.]{1,5}$`` via a Pydantic field_validator — defense against
      ticker-as-path-traversal at fetch time (T-3-V5-01 in the threat model).
RESEARCH.md §Anti-pattern line 428: NormalizedFiling.fetched_at is ISO-8601
      UTC metadata only — it MUST NOT be included in any byte-identity hash
      of the normalized output. The docstring on the field repeats this rule.
"""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "Chunk",
    "CompanyEntry",
    "NormalizedFiling",
    "NormalizedFilingManifest",
]


# Defined first so NormalizedFiling can reference it without model_rebuild().
class NormalizedFilingManifest(BaseModel):
    """Per-filing manifest entry embedded in NormalizedFiling (D-09).

    Surfaces which Item N[X] sections were detected, which were missing
    (pre-2024 filings legitimately lack Item 1C per Pitfall 5), whether the
    detected items appeared in the canonical 10-K ordering, and how many
    ``<table>`` elements were dropped at normalization time (D-08).
    """

    model_config = ConfigDict(extra="forbid")

    items_found: list[str]
    items_missing: list[str]
    ordering_valid: bool
    tables_dropped: int


class NormalizedFiling(BaseModel):
    """One filing after HTML → JSON normalization. D-09 schema.

    Produced by Wave 3's ``docintel_ingest.normalize.normalize_html``. The
    resulting JSON lives at ``data/corpus/normalized/{ticker}/FY{year}.json``
    and is committed (D-04). The chunker reads this artifact in Wave 4.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str
    fiscal_year: int
    accession: str
    # ISO-8601 UTC timestamp captured at fetch time. RESEARCH.md anti-pattern
    # line 428: fetched_at is sidecar metadata only — it MUST NOT be included
    # in any byte-identity (sha256) hash of normalized output. Hashing the
    # fetch time would defeat ING-04 idempotency across re-runs.
    fetched_at: str = Field(
        description=(
            "ISO-8601 UTC fetch timestamp. NEVER included in byte-identity "
            "hashes of the normalized output — sidecar metadata only "
            "(RESEARCH.md anti-pattern line 428)."
        ),
    )
    # Relative path under the repo root, e.g. ``data/corpus/raw/AAPL/FY2024.html``.
    raw_path: str
    # Keyed by the normalized item_code (``Item 1``, ``Item 1A``, ...). A
    # missing Item shows up as an absent key here AND in manifest.items_missing.
    sections: dict[str, str]
    manifest: NormalizedFilingManifest


class Chunk(BaseModel):
    """A single retrievable chunk with citation-anchor metadata.

    D-15: carries chunk_id, ticker, fiscal_year, accession, item_code,
          item_title, text, char_span_in_section, n_tokens, prev_chunk_id,
          next_chunk_id.
    D-16: char_span_in_section indexes into NormalizedFiling.sections[item_code]
          — Phase 7's Citation will render the chunk text inline AND offer an
          "expand" affordance that highlights the span in the surrounding
          section text.
    D-12: chunks NEVER cross Item boundaries. ``item_code`` is unambiguous.
    D-11: n_tokens is the BGE-tokenizer count and MUST be < HARD_CAP_TOKENS
          (500). Wave 4's chunker enforces this with a build-fail-if-exceeded
          assertion (RESEARCH.md line 378-383 — the canary).
    CD-02: sha256_of_text is the 16-char truncated hex of sha256(text). Used
          by MANIFEST.json for fast chunk-identity hashing.
    D-14: chunk_id matches ``{ticker}-FY{year}-Item-N[X]-{ordinal:03d}``.
          Example: ``AAPL-FY2024-Item-1A-007``.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    ticker: str
    fiscal_year: int
    accession: str
    # Normalized item code, e.g. ``Item 1A``. Always ``Item `` + digit(s) +
    # optional A/B/C. Same form as ``NormalizedFiling.sections`` keys.
    item_code: str
    # Human-readable item title, e.g. ``Risk Factors``.
    item_title: str
    text: str
    # ``(start, end)`` indexing into ``NormalizedFiling.sections[item_code]``.
    # Pydantic v2 accepts ``tuple[int, int]`` natively (RESEARCH.md line 569).
    char_span_in_section: tuple[int, int]
    # BGE-tokenizer count. Wave 4 enforces < 500 (D-11 HARD_CAP_TOKENS).
    n_tokens: int
    prev_chunk_id: str | None
    next_chunk_id: str | None
    # CD-02: 16-char truncated hex of sha256(text).
    sha256_of_text: str


# Compile once at module load — Pydantic re-runs field_validator per construction.
_TICKER_PATTERN = re.compile(r"^[A-Z.]{1,5}$")


class CompanyEntry(BaseModel):
    """One row of the committed ``companies.snapshot.csv``.

    D-01 + D-02: the snapshot pins the ``{ticker, name, sector,
    market_cap_usd, fiscal_years, snapshot_date}`` 6-tuple. Re-running
    ``make fetch-corpus`` reads THIS file rather than re-querying any
    market-cap source — that pinning is what makes ING-04 byte-identity
    survive across calendar years.

    Pitfall 1 (NVDA): ``fiscal_years`` is per-ROW, not a global FY range.
    NVDA's FY2024 ended Jan 28, 2024; AAPL's FY2024 ended Sep 28, 2024; MSFT's
    FY2024 ended Jun 30, 2024. The list of integers is the company-specific
    set of fiscal years the snapshot pins at generation time.

    RESEARCH.md §Security V5 + T-3-V5-01 (threat model): the ``ticker``
    validator enforces ``^[A-Z.]{1,5}$``. This blocks path-traversal at fetch
    time: a malicious snapshot row containing ``../../etc/passwd`` for the
    ticker is rejected by Pydantic BEFORE it can flow into
    ``data/corpus/raw/{ticker}/FY{year}.html`` path construction.

    Pitfall 7 (GOOGL vs GOOG): the snapshot includes exactly one ticker per
    issuer. GOOGL (Class A, voting) and GOOG (Class C) are two share classes
    of Alphabet Inc.; both map to the same 10-K accession. This model accepts
    either form syntactically — the de-duplication is a snapshot-curation
    concern, not a Pydantic validation concern.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str
    name: str
    sector: str
    market_cap_usd: float
    # Per-ticker pinned list per Pitfall 1. Non-empty; every year in
    # ``range(2000, 2030)`` — anything outside that sanity window is a CSV typo.
    fiscal_years: list[int]
    # ISO-8601 date (``YYYY-MM-DD``). Validated via ``date.fromisoformat``.
    snapshot_date: str

    @field_validator("ticker")
    @classmethod
    def _ticker_pattern(cls, v: str) -> str:
        if not _TICKER_PATTERN.match(v):
            raise ValueError(
                f"ticker {v!r} violates ^[A-Z.]{{1,5}}$ (RESEARCH.md §V5, "
                "T-3-V5-01) — uppercase letters and ``.`` only, length 1-5. "
                "This is the path-traversal defense for fetch.py's "
                "data/corpus/raw/{ticker}/ resolution."
            )
        return v

    @field_validator("market_cap_usd")
    @classmethod
    def _market_cap_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError(
                f"market_cap_usd {v!r} must be >= 0 (sort metadata, not "
                "load-bearing — but negative values are CSV typos)."
            )
        return v

    @field_validator("fiscal_years")
    @classmethod
    def _fiscal_years_sane(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError(
                "fiscal_years must be non-empty (Pitfall 1 — per-ticker FY "
                "pinning is the whole point of the snapshot)."
            )
        for year in v:
            if not (2000 <= year < 2030):
                raise ValueError(
                    f"fiscal_year {year!r} outside sanity range [2000, 2030) "
                    "— this is almost certainly a CSV typo. Widen the range "
                    "deliberately in docintel_core.types if SEC data goes "
                    "back further."
                )
        return v

    @field_validator("snapshot_date")
    @classmethod
    def _snapshot_date_iso(cls, v: str) -> str:
        try:
            date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(
                f"snapshot_date {v!r} is not ISO-8601 YYYY-MM-DD format: {exc}"
            ) from exc
        return v
