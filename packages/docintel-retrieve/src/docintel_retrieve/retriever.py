"""Query-time orchestrator. Composes the AdapterBundle + IndexStoreBundle into one .search() seam.

Phase 5 D-02: a single ``Retriever.search(query, k) -> list[RetrievedChunk]``
callable that runs the full pipeline end-to-end. The pipeline order is
non-negotiable (Step A..G — RESEARCH.md Pattern 2 lines 433-516):

  A. query normalization — tokenize + truncate at 64 BGE tokens (D-11),
     emit ``retriever_query_truncated`` warn if truncated, then
     ``q_vec = embedder.embed([truncated_query])[0]``.
  B. parallel candidate retrieval — ``bm25.query(truncated_query, 100)`` +
     ``dense.query(q_vec, 100)`` (D-05 top-N=100 each); timed per stage.
  C. RRF fusion — ``_rrf_fuse(bm25, dense)`` from Plan 05-03 (pure function,
     k=60). Zero-candidate guard (CD-07): if fused is ``[]``, emit
     ``retriever_search_zero_candidates`` warn and return ``[]``.
  D. top-M lookup + n_tokens assertion — take top-20 chunk_ids (D-06
     TOP_M_RERANK), look up Chunk in ``self._chunk_map``, assert
     ``chunk.n_tokens <= 500`` per chunk with the verbatim CLAUDE.md quote
     in the AssertionError message (D-10 + Pitfall 6). Defense-in-depth
     soft warning ``chunk_reranker_token_overflow`` only when
     ``bundle.reranker.name == "bge-reranker-base"`` (RESEARCH §3 + Pitfall 1).
  E. rerank — ``reranker.rerank(truncated_query, [chunk.text for chunk
     in top_m_chunks])`` (D-09 raw chunk.text verbatim; no prefix).
  F. top-K post-processing — take ``reranked[:k]``; build a
     ``RetrievedChunk`` with the seven D-03 fields per result
     (score = ``reranked_doc.score``).
  G. telemetry — emit ``retriever_search_completed`` INFO structlog with
     the twelve D-12 fields verbatim.

Ablation seams use null adapters (D-08), NOT behavior toggles — Phase 11's
no-rerank ablation swaps in ``NullReranker``; dense-only swaps in
``NullBM25Store``. ``Retriever.search`` has ZERO conditional branches for
ablation — the hot path is identical across all bundle compositions.

CD-04: this module composes already-wrapped adapter calls and adds NO new
tenacity wraps. The CI grep gates (``scripts/check_adapter_wraps.sh``,
``scripts/check_index_wraps.sh``, ``scripts/check_ingest_wraps.sh``) are
unchanged by Phase 5 — there are no new SDK call sites in
``docintel-retrieve``.

CD-01: ``Retriever.__init__`` eager-loads the ``chunk_id → Chunk`` map
from ``data/corpus/chunks/**/*.jsonl`` AND verifies cardinality against
``data/indices/MANIFEST.json`` ``chunk_count`` (Pitfall 7). Warm-up calls
to ``stores.dense.query`` + ``stores.bm25.query`` fire each store's
``_lazy_load_from_disk()`` path during construction (RESEARCH §5).

FND-11: ``cfg: Settings`` passed in by the factory; this module does not
read environment variables.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Final

import numpy as np
import structlog
from docintel_core.adapters.types import AdapterBundle, IndexStoreBundle, RerankedDoc
from docintel_core.config import Settings
from docintel_core.types import Chunk, RetrievedChunk

from docintel_retrieve.fuse import _rrf_fuse

# Single structlog logger — no tenacity in this module (CD-04), so the
# SP-3 two-logger pattern (``_retry_log`` + ``log``) is intentionally NOT
# applied; the dead ``_retry_log`` placeholder would be misleading here.
log = structlog.stdlib.get_logger(__name__)


TOP_N_PER_RETRIEVER: Final[int] = 100
"""D-05 — BM25 returns top-100, Dense returns top-100. RRF then fuses up to
200 ranked entries; the unique-chunk set is typically 120-180 with 10-K
boilerplate overlap. Recall payoff at 100 vs 50 is meaningful on near-
duplicate prose; 200 was rejected as diminishing returns at 6k chunks.
"""

TOP_M_RERANK: Final[int] = 20
"""D-06 — top-20 RRF-fused candidates go into ``Reranker.rerank``. bge-
reranker-base on CPU ≈ 20 ms per (query, chunk) pair → 20 pairs ≈ 0.4 s;
predictable and OK for both stub-mode CI and real-mode eval runs.
"""

TOP_K_FINAL: Final[int] = 5
"""D-06 — top-5 reranked chunks returned to the caller. Enough headroom
over RET-03's "top-3 hit" criterion; gives generation a 5-chunk context
block without diluting the prompt past the demo question's needs.
"""

QUERY_TOKEN_HARD_CAP: Final[int] = 64
"""D-11 — defensive cap on query length. Real user queries are sub-50
tokens typically; a long query (accidentally pasted prose, abuse) would
consume the reranker's 512-token budget, forcing the chunk side into
truncation that LOOKS like a Phase 3 bug. Truncation is LOUD (structlog
warning ``retriever_query_truncated``), not silent — the canary stays
sensitive to Phase 3 regressions specifically, not to query-length abuse.
"""


_CLAUDE_MD_HARD_GATE: Final[str] = (
    'Per CLAUDE.md: "If that gate fails, look at BGE 512-token truncation '
    "FIRST before suspecting hybrid retrieval, RRF, or chunk size. This is "
    "the most common subtle failure mode and the canary exists specifically "
    'to catch it."'
)
"""Pitfall 6 — verbatim CLAUDE.md text reused in BOTH the D-10 chunk-loop
AssertionError message AND (later) Plan 05-06's canary failure message.

MUST contain the substrings:
  * "BGE 512-token truncation FIRST"
  * "before suspecting hybrid retrieval, RRF, or chunk size"
  * "the canary exists specifically to catch it"

A "make error messages clearer" cleanup PR that paraphrases the text would
break the Phase 5 canary's self-documenting failure mode. The three
substrings are also referenced by ``tests/test_reranker_canary.py``
``_CLAUDE_MD_QUOTE`` constant (Plan 05-06) so any drift in the source of
truth here surfaces immediately in CI.
"""


class Retriever:
    """End-to-end query pipeline: BM25 + dense → RRF → rerank → top-K.

    D-02 single seam. Phase 6 calls ``.search()``; Phase 10 wraps it;
    Phase 13 awaits it (sync-wrapped per Phase 2 D-08); Phase 11 swaps
    the Retriever instance for ablations (D-08 null-adapter pattern).

    CD-03: holds ``AdapterBundle`` + ``IndexStoreBundle`` as instance
    attributes; the bundles themselves carry the lazy-loading discipline.

    CD-01: ``__init__`` eager-loads the ``chunk_id → Chunk`` map AND fires
    warm-up calls against both stores to trigger their ``_lazy_load_from_disk``
    paths (RESEARCH §5 — first-query latency property).
    """

    def __init__(
        self,
        bundle: AdapterBundle,
        stores: IndexStoreBundle,
        cfg: Settings,
    ) -> None:
        """Construct the Retriever and eager-load the chunk_id → Chunk map.

        Args:
            bundle:  AdapterBundle from ``make_adapters(cfg)`` — carries
                ``embedder``, ``reranker``, ``llm``, ``judge``.
            stores:  IndexStoreBundle from ``make_index_stores(cfg)`` —
                carries ``dense`` + ``bm25``.
            cfg:     Settings instance with ``data_dir`` + ``index_dir`` set.
                Only the two paths are consulted; no other Settings field.

        Notes:
            * Eager load is ~600 ms in stub mode on the 6,053-chunk corpus
              (RESEARCH §6). Real-mode Phase 13 will lru-cache the Retriever
              at the FastAPI dependency level.
            * Warm-up calls are wrapped in ``try/except Exception`` so an
              empty / absent index does not prevent construction — that
              would block test seams that construct a Retriever against
              ``tmp_path`` Settings (e.g. ``test_zero_candidates``).
        """
        self._bundle = bundle
        self._stores = stores
        self._cfg = cfg
        # CD-01 — eager chunk-map load + MANIFEST cardinality check (Pitfall 7).
        self._chunk_map: dict[str, Chunk] = self._load_chunk_map()
        # RESEARCH §5 — fire each store's lazy-load path during construction.
        # Wrapped in try/except because empty / absent indices (test seams,
        # cold-start before docintel-index build) should not prevent
        # construction. The bundles' .query implementations themselves
        # handle the empty-store case (NumpyDenseStore returns [];
        # Bm25sStore returns []).
        try:
            self._stores.dense.query(np.zeros(384, dtype=np.float32), k=1)
        except Exception:
            pass
        try:
            self._stores.bm25.query("warmup", k=1)
        except Exception:
            pass

    def search(self, query: str, k: int = TOP_K_FINAL) -> list[RetrievedChunk]:
        """One callable, end-to-end. See module docstring for the pipeline.

        Args:
            query: Raw user query — will be truncated at 64 BGE tokens
                BEFORE embedder.embed (D-11 + Pitfall — the cap is the
                load-bearing defense; long queries are surfaced loudly
                via a structlog warning, never silently truncated).
            k:     Number of final results to return. Defaults to
                ``TOP_K_FINAL`` = 5 (D-06). Callers may request a smaller
                k for the canary (top-3 hit-rate gate) without changing
                the rerank top-M.

        Returns:
            ``list[RetrievedChunk]`` of length ``min(k, len(reranked))``.
            Each ``RetrievedChunk`` carries the seven D-03 fields:
            ``chunk_id``, ``text``, ``score``, ``ticker``, ``fiscal_year``,
            ``item_code``, ``char_span_in_section``. The ``score`` is the
            reranker output (or RRF score in the no-rerank ablation, where
            ``NullReranker`` preserves input order with score = -original_rank).

        Raises:
            AssertionError: When any chunk in the top-20 RRF set has
                ``n_tokens > 500`` (D-10 + Pitfall 6). The error message
                embeds ``_CLAUDE_MD_HARD_GATE`` verbatim so the failure
                mode self-documents at the seam.
        """
        t0 = time.perf_counter()

        # Step A — query normalization (D-11)
        truncated_query, q_tokens = self._truncate_query(query)
        if q_tokens > QUERY_TOKEN_HARD_CAP:
            log.warning(
                "retriever_query_truncated",
                original_tokens=q_tokens,
                truncated_to=QUERY_TOKEN_HARD_CAP,
                query_prefix=query[:100],
            )
        q_vec = self._bundle.embedder.embed([truncated_query])[0]

        # Step B — parallel candidate retrieval (D-05 — top-100 each).
        # Store-query failures (e.g. absent on-disk artifacts when the
        # Retriever is constructed against an empty tmp_path corpus) are
        # treated as zero-candidate from that store rather than crashing
        # the entire search — the CD-07 zero-candidate guard below picks
        # up the empty-fused case and emits ``retriever_search_zero_candidates``.
        bm25_t0 = time.perf_counter()
        try:
            bm25_results = self._stores.bm25.query(truncated_query, TOP_N_PER_RETRIEVER)
        except Exception as exc:
            log.warning(
                "retriever_bm25_query_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            bm25_results = []
        bm25_ms = (time.perf_counter() - bm25_t0) * 1000

        dense_t0 = time.perf_counter()
        try:
            dense_results = self._stores.dense.query(q_vec, TOP_N_PER_RETRIEVER)
        except Exception as exc:
            log.warning(
                "retriever_dense_query_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            dense_results = []
        dense_ms = (time.perf_counter() - dense_t0) * 1000

        # Step C — RRF fusion (D-07 — RRF_K = 60)
        fuse_t0 = time.perf_counter()
        fused = _rrf_fuse(bm25_results, dense_results)
        fuse_ms = (time.perf_counter() - fuse_t0) * 1000

        # CD-07 — zero-candidate path. Phase 6 GEN-04 refusal path will take
        # over from here; the structlog warning is the observability hook
        # Phase 9 MET-05 can count.
        if not fused:
            log.warning(
                "retriever_search_zero_candidates",
                query=truncated_query[:100],
            )
            return []

        # Step D — top-M lookup + n_tokens assertion (D-10 + Pitfall 6/7)
        top_m_ids = [cid for cid, _ in fused[:TOP_M_RERANK]]
        # Pitfall 7: KeyError on a missing cid is intentional — __init__
        # already verified cardinality against MANIFEST; if a cid is somehow
        # missing now, that's a genuine drift bug we want to surface.
        top_m_chunks: list[Chunk] = [self._chunk_map[cid] for cid in top_m_ids]
        for chunk in top_m_chunks:
            assert chunk.n_tokens <= 500, (
                f"Chunk {chunk.chunk_id!r} has n_tokens={chunk.n_tokens} > 500. "
                + _CLAUDE_MD_HARD_GATE
            )

        # Step D defense-in-depth — RESEARCH §3 + Pitfall 1 soft warning.
        # No-op in stub mode (reranker.name != "bge-reranker-base").
        self._check_reranker_token_overflow(top_m_chunks)

        # Step E — rerank (D-09 — raw chunk.text verbatim; no prefix)
        rerank_t0 = time.perf_counter()
        reranked: list[RerankedDoc] = self._bundle.reranker.rerank(
            truncated_query, [chunk.text for chunk in top_m_chunks]
        )
        rerank_ms = (time.perf_counter() - rerank_t0) * 1000

        # Step F — top-K post-processing. RerankedDoc.doc_id is the index
        # into top_m_chunks (the contract every Reranker adapter honours).
        results: list[RetrievedChunk] = []
        for reranked_doc in reranked[:k]:
            idx = int(reranked_doc.doc_id)
            chunk = top_m_chunks[idx]
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    score=reranked_doc.score,
                    ticker=chunk.ticker,
                    fiscal_year=chunk.fiscal_year,
                    item_code=chunk.item_code,
                    char_span_in_section=chunk.char_span_in_section,
                )
            )

        # Step G — telemetry (D-12). Twelve fields verbatim; Phase 9 MET-05
        # + Phase 11 ablation reports source from this single log line.
        total_ms = (time.perf_counter() - t0) * 1000
        log.info(
            "retriever_search_completed",
            query_tokens=q_tokens,
            query_truncated=q_tokens > QUERY_TOKEN_HARD_CAP,
            bm25_candidates=len(bm25_results),
            dense_candidates=len(dense_results),
            rrf_unique=len(fused),
            rerank_input=len(top_m_chunks),
            results_returned=len(results),
            bm25_ms=round(bm25_ms, 2),
            dense_ms=round(dense_ms, 2),
            fuse_ms=round(fuse_ms, 2),
            rerank_ms=round(rerank_ms, 2),
            total_ms=round(total_ms, 2),
        )
        return results

    def _truncate_query(self, query: str) -> tuple[str, int]:
        """Count tokens via the embedder-side tokenizer; truncate at 64 (D-11).

        See RESEARCH §3 for the rationale on which tokenizer counts: the
        embedder side (BGE-small BERT WordPiece) is what feeds dense + BM25
        consistently. The reranker-side count is checked downstream by the
        D-10 chunk.n_tokens assertion + the RESEARCH §3 soft warning.

        Stub embedder (``name == "stub-embedder"``) uses whitespace.split() —
        within 1-2x of BERT WordPiece on English prose; fine for a defensive
        cap. Real embedder (``name == "bge-small-en-v1.5"``) lazily accesses
        ``embedder._model.tokenizer`` (the SentenceTransformer's HF tokenizer).

        Args:
            query: Raw user query.

        Returns:
            ``(maybe_truncated_text, original_token_count)``. Caller emits
            the structlog warning when ``original_token_count > 64``.
        """
        embedder_name = self._bundle.embedder.name
        if embedder_name == "stub-embedder":
            tokens = query.lower().split()
            n = len(tokens)
            if n > QUERY_TOKEN_HARD_CAP:
                truncated = " ".join(tokens[:QUERY_TOKEN_HARD_CAP])
                return (truncated, n)
            return (query, n)

        # Real-mode path — lazily access the HF tokenizer on the embedder's
        # underlying SentenceTransformer model. Future-proof against adapter
        # shape changes (``_model`` or ``.tokenizer`` could be absent) by
        # falling back to the whitespace approximation in those cases.
        model = getattr(self._bundle.embedder, "_model", None)
        tokenizer = getattr(model, "tokenizer", None) if model is not None else None
        if tokenizer is None:
            # Fall back to whitespace approximation — same as stub path.
            tokens = query.lower().split()
            n = len(tokens)
            if n > QUERY_TOKEN_HARD_CAP:
                truncated = " ".join(tokens[:QUERY_TOKEN_HARD_CAP])
                return (truncated, n)
            return (query, n)

        # Real tokenizer path — count tokens; if over the cap, decode the
        # truncated token slice back to text. ``add_special_tokens=False``
        # keeps the count comparable to the chunker side which also excludes
        # specials for n_tokens (Phase 3 D-11 chunker).
        encoded = tokenizer.encode(query, add_special_tokens=False)
        n = len(encoded)
        if n > QUERY_TOKEN_HARD_CAP:
            truncated_text = tokenizer.decode(
                encoded[:QUERY_TOKEN_HARD_CAP],
                skip_special_tokens=True,
            )
            return (truncated_text, n)
        return (query, n)

    def _load_chunk_map(self) -> dict[str, Chunk]:
        """Load every Chunk from data/corpus/chunks/**/*.jsonl into a dict.

        CD-01 eager load. Sub-second on the 6,053-chunk corpus (RESEARCH §6).
        The map is held as an instance attribute; subsequent ``.search()``
        calls do O(1) lookups.

        Pitfall 7 cardinality check: read ``data/indices/MANIFEST.json``
        ``chunk_count`` and assert it matches ``len(chunk_map)``. Mismatch
        indicates Phase 3 corpus drift vs Phase 4 indices; raises ``ValueError``
        pointing at the rebuild command. The check is SKIPPED when
        ``MANIFEST.json`` is absent (e.g. tests with ``tmp_path``, cold-start
        before ``docintel-index build``).

        Returns:
            ``dict[chunk_id, Chunk]`` keyed by the chunk_id sourced from the
            JSONL records. Sorted-filename traversal makes the iteration
            order deterministic across machines.

        Raises:
            ValueError: When ``MANIFEST.json`` exists and its ``chunk_count``
                does not match the on-disk chunk count.
        """
        chunks_root = Path(self._cfg.data_dir) / "corpus" / "chunks"
        chunk_map: dict[str, Chunk] = {}
        # Sorted-filename traversal — same pattern as
        # ``packages/docintel-index/src/docintel_index/build.py::_read_all_chunks``
        # so test_assertion_quotes_claude_md gets a deterministic
        # ``next(iter(r._chunk_map))`` across machines.
        if chunks_root.is_dir():
            for jsonl_path in sorted(chunks_root.rglob("*.jsonl")):
                text = jsonl_path.read_text(encoding="utf-8")
                for line in text.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    chunk = Chunk.model_validate_json(stripped)
                    chunk_map[chunk.chunk_id] = chunk

        # Pitfall 7 — MANIFEST cardinality check (skipped when absent).
        manifest_path = Path(self._cfg.index_dir) / "MANIFEST.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            expected = manifest.get("chunk_count", -1)
            if expected != len(chunk_map):
                raise ValueError(
                    f"chunk_map cardinality {len(chunk_map)} != "
                    f"MANIFEST.chunk_count {expected}. Phase 3 corpus has "
                    f"drifted vs Phase 4 indices. Run `uv run docintel-index "
                    f"build` to rebuild indices, OR `uv run docintel-ingest "
                    f"all` to rebuild chunks. Manifest path: {manifest_path}"
                )

        log.info(
            "retriever_chunk_map_loaded",
            n=len(chunk_map),
            corpus_root=str(chunks_root),
        )
        return chunk_map

    def _check_reranker_token_overflow(self, chunks: list[Chunk]) -> None:
        """Defense-in-depth — warn if reranker tokenizer disagrees with embedder.

        RESEARCH §3 + Pitfall 1. bge-reranker-base uses XLM-RoBERTa
        tokenizer; bge-small-en-v1.5 uses BERT tokenizer. ``chunk.n_tokens``
        was computed using BGE-small. If XLM-RoBERTa tokenizes any chunk to
        > 500 tokens, silent truncation will occur at reranker inference
        time — exactly the failure mode the Phase 5 canary exists to catch.

        Only fires in real mode (``reranker.name == "bge-reranker-base"``).
        Stub mode skips this entirely — the stub reranker doesn't tokenize.

        Guarded against future reranker adapter shape changes: if ``_model``
        or ``.tokenizer`` is absent on the reranker, the function returns
        silently rather than crashing the search.

        Args:
            chunks: The top-M chunks about to enter the reranker. The
                function only iterates; no mutation.
        """
        if self._bundle.reranker.name != "bge-reranker-base":
            return  # Stub or future adapter — no tokenizer to inspect.
        model = getattr(self._bundle.reranker, "_model", None)
        if model is None:
            return  # Future-proof: reranker adapter without ._model attribute.
        tokenizer = getattr(model, "tokenizer", None)
        if tokenizer is None:
            return  # Future-proof: model without .tokenizer attribute.

        for chunk in chunks:
            n_rerank = len(tokenizer.encode(chunk.text, truncation=False))
            if n_rerank > 500:  # Same threshold as the embedder budget.
                log.warning(
                    "chunk_reranker_token_overflow",
                    chunk_id=chunk.chunk_id,
                    embedder_n_tokens=chunk.n_tokens,
                    reranker_n_tokens=n_rerank,
                    note="reranker tokenizer disagrees with embedder; investigate canary",
                )
