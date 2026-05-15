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
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "Chunk",
    "CompanyEntry",
    "IndexManifest",
    "IndexManifestBM25",
    "IndexManifestDense",
    "IndexManifestEmbedder",
    "NormalizedFiling",
    "NormalizedFilingManifest",
    "REFUSAL_TEXT_SENTINEL",
    "RetrievedChunk",
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


class RetrievedChunk(BaseModel):
    """A single retrieval result returned by ``Retriever.search`` (Phase 5).

    D-03: the public retrieval shape is exactly seven fields — ``chunk_id``,
          ``text``, ``score``, ``ticker``, ``fiscal_year``, ``item_code``,
          ``char_span_in_section``. Per-stage debug fields (``bm25_rank``,
          ``dense_rank``, ``rrf_score``, ``rerank_score``) are deliberately
          OMITTED from the public model — they are internal accounting that
          downstream callers (Phase 6 reader, Phase 7 generation, Phase 13
          UI) MUST NOT depend on. RESEARCH.md anti-pattern line 622 forbids
          leaking them onto the public shape; ``ConfigDict(extra="forbid")``
          is the bite point.
    D-16: ``char_span_in_section`` is the citation anchor — Phase 7's
          ``Citation`` will render the chunk text inline AND offer an
          "expand" affordance that highlights the span in the surrounding
          section text. Same semantics as ``Chunk.char_span_in_section``.
    CD-02: this model lives in ``docintel_core.types`` (not in
          ``docintel_retrieve.types``) so Phase 6 / 7 / 13 can import it
          without depending on the retrieve package. The schema is a
          contract; the retrieve package re-exports it as a convenience.
    Frozen=True: downstream callers MUST NOT mutate the result list —
          ``rc.score = X`` raises ``pydantic.ValidationError`` after
          construction. This is defense-in-depth against a Phase 7
          reranker-output-shape mistake that would otherwise silently
          corrupt RRF scores in shared result lists.

    The ``score`` field is the final score a caller should compare against —
    after the reranker stage in the default pipeline, or the RRF score in
    the no-rerank ablation (Phase 11). Callers should not need to know
    which stage produced it; the orchestrator owns the policy.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    text: str
    # final reranker score (or RRF score in no-rerank ablation)
    score: float
    ticker: str
    fiscal_year: int
    # e.g., "Item 1A" — matches Phase 3 Chunk.item_code
    item_code: str
    # citation anchor — Phase 3 D-16
    char_span_in_section: tuple[int, int]


REFUSAL_TEXT_SENTINEL: Final[str] = (
    "I cannot answer this question from the retrieved 10-K excerpts."
)
"""Canonical refusal sentinel for Phase 6 (D-11) — single source of truth across
stub LLM, generator (docintel-generate), and Phase 7 Citation parser.

Pitfall 9 (RESEARCH Open Question 1) resolution: this constant lives HERE in
docintel_core.types — not in docintel_generate.prompts — so the upward-stack
import direction is preserved. docintel-generate imports from docintel-core;
never the reverse. The stub adapter
(packages/docintel-core/src/docintel_core/adapters/stub/llm.py) imports this
name in Plan 06-05; docintel_generate.prompts.REFUSAL_PROMPT also equals this
string body (Plan 06-03 imports it as the canonical body for hash computation).

The string is exactly 63 characters; no trailing whitespace; no surrounding
punctuation beyond the terminal period. Phase 9 MET-03 faithfulness tests
assert byte-exact ``text.startswith(REFUSAL_TEXT_SENTINEL)`` — any drift in
this constant breaks Phase 9 / 10 / 13.
"""


class IndexManifestEmbedder(BaseModel):
    """Embedder block of the Phase 4 index MANIFEST (D-13).

    Sourced from ``bundle.embedder.name`` + ``Settings.embedder_model_id``
    + the BGE-small-en-v1.5 dim (Phase 2 D-01 = 384). Phase 10's eval manifest
    header consumes these three fields verbatim (EVAL-02).
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    model_id: str
    dim: int


class IndexManifestDense(BaseModel):
    """Dense block of the Phase 4 index MANIFEST (D-13).

    Polymorphic by ``backend``: ``"numpy"`` carries ``sha256`` of
    ``embeddings.npy`` (D-04); ``"qdrant"`` carries the collection identity +
    geometry (D-06). A cross-field validator enforces that the OTHER backend's
    fields are ``None`` — this catches MANIFEST writers that conflate the two
    polymorphs at write time (the contract is structural, not free-form).

    CD-06: When ``backend == "qdrant"``, ``collection`` is the human-readable
    name (default ``"docintel-dense-v1"``); ``vector_size`` MUST be 384
    (BGE-small-en-v1.5 dim) and ``distance`` MUST be ``"Cosine"`` per D-06.
    """

    model_config = ConfigDict(extra="forbid")

    backend: Literal["numpy", "qdrant"]
    sha256: str | None = None  # numpy only
    collection: str | None = None  # qdrant only
    collection_uuid: str | None = None  # qdrant only (stable identifier per CD-06)
    points_count: int | None = None  # qdrant only
    vector_size: int | None = None  # qdrant only
    distance: str | None = None  # qdrant only ("Cosine" per D-06)

    @model_validator(mode="after")
    def _backend_field_consistency(self) -> IndexManifestDense:
        """Enforce polymorphic shape per D-13 schema.

        numpy → sha256 required + all qdrant fields None.
        qdrant → collection + points_count + vector_size + distance required
                 + sha256 None. ``collection_uuid`` is OPTIONAL on the qdrant
                 side because not every qdrant-client version exposes a stable
                 UUID; the human-readable ``collection`` name is the floor.
        """
        if self.backend == "numpy":
            if self.sha256 is None:
                raise ValueError(
                    "IndexManifestDense backend='numpy' requires sha256 "
                    "(hex digest of embeddings.npy per D-04). Got sha256=None."
                )
            qdrant_only = {
                "collection": self.collection,
                "collection_uuid": self.collection_uuid,
                "points_count": self.points_count,
                "vector_size": self.vector_size,
                "distance": self.distance,
            }
            populated = {k: v for k, v in qdrant_only.items() if v is not None}
            if populated:
                raise ValueError(
                    "IndexManifestDense backend='numpy' must have all qdrant-only "
                    f"fields unset, got populated: {sorted(populated.keys())!r}. "
                    "Use backend='qdrant' if you intended the production-shaped store (D-06)."
                )
        elif self.backend == "qdrant":
            missing = [
                name
                for name, value in (
                    ("collection", self.collection),
                    ("points_count", self.points_count),
                    ("vector_size", self.vector_size),
                    ("distance", self.distance),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    f"IndexManifestDense backend='qdrant' missing required fields: {missing!r}. "
                    "All four (collection, points_count, vector_size, distance) are required for "
                    "D-13 schema + D-14 verify."
                )
            if self.sha256 is not None:
                raise ValueError(
                    "IndexManifestDense backend='qdrant' must NOT carry sha256 — "
                    "the qdrant backend records collection identity instead "
                    "(D-06: collection drop-and-recreate, no on-disk npy)."
                )
        return self


class IndexManifestBM25(BaseModel):
    """BM25 block of the Phase 4 index MANIFEST (D-13).

    Same shape across stub and real modes (D-07: one BM25 implementation —
    ``bm25s``). ``library_version`` is sourced from
    ``importlib.metadata.version("bm25s")`` (Pitfall 6 — guard against
    file-layout drift on dep bump).

    Tokenizer pipeline (D-08): lowercase → English stopwords → Porter stem.
    The ``tokenizer`` dict surfaces the pipeline so reviewers can confirm
    what was applied without reading the build code.

    Hyperparameters (D-09): ``k1=1.5``, ``b=0.75`` (Lucene defaults).
    """

    model_config = ConfigDict(extra="forbid")

    library: str
    library_version: str
    k1: float
    b: float
    tokenizer: dict[str, Any]
    vocab_size: int
    sha256: str


class IndexManifest(BaseModel):
    """Phase 4 index MANIFEST schema (D-13). Home: ``docintel_core.types`` per CD-02.

    Single file at ``data/indices/MANIFEST.json``; same top-level shape across
    both dense backends (numpy / qdrant); the ``dense`` block is polymorphic per
    ``IndexManifestDense``. Phase 4's ``docintel-index verify`` (D-14) loads
    this model via ``IndexManifest.model_validate(json.loads(MANIFEST.json))``.

    ``extra="forbid"`` is structural defence-in-depth (T-4-V5-01 — tampered
    JSON with an unexpected key fails validation immediately rather than
    silently flowing into downstream logic).

    Phase 10's eval-report manifest header (EVAL-02) imports this model so
    ``embedder.name``, ``dense.backend``, and ``bm25.tokenizer`` are sourced
    via a single typed contract.

    ``corpus_manifest_sha256`` is the hash of ``data/corpus/MANIFEST.json``
    (Phase 3's per-filing manifest bytes) — keys the D-12 skip path
    (``index_build_skipped_unchanged_corpus``).
    """

    model_config = ConfigDict(extra="forbid")

    embedder: IndexManifestEmbedder
    dense: IndexManifestDense
    bm25: IndexManifestBM25
    corpus_manifest_sha256: str
    chunk_count: int
    built_at: str  # ISO-8601 UTC
    git_sha: str
    format_version: int


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
