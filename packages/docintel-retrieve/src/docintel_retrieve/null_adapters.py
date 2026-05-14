"""Null adapter seams for Phase 11 ablation (Phase 5 D-08).

Two classes that satisfy the ``Reranker`` and ``BM25Store`` protocols but
degenerate the corresponding stage. Phase 11's no-rerank ablation constructs::

    AdapterBundle(embedder=..., reranker=NullReranker(), llm=..., judge=...)

and Phase 11's dense-only ablation constructs::

    IndexStoreBundle(dense=..., bm25=NullBM25Store())

Phase 5's ``Retriever.search`` has **zero conditional branches** for ablation —
it always runs the same control flow (embed query → BM25.query + Dense.query →
RRF fuse → Reranker.rerank → top-K). The null adapters degenerate the
corresponding stage in place:

* ``NullReranker.rerank`` preserves input order (score is the negated input
  rank so descending sort by score retains the RRF ordering). Phase 11's
  no-rerank ablation therefore returns top-K = top-M of the fused list.
* ``NullBM25Store.query`` always returns ``[]``. Phase 11's dense-only ablation
  therefore runs RRF over a single ranker (dense) — RRF of a single ranker
  reduces to that ranker's ordering, which is the desired ablation semantics.

This is the **"adapter swap is the artifact"** framing (Phase 2 D-03 used the
same pattern for Anthropic ↔ OpenAI generators). By NOT putting ``no_rerank``
or ``dense_only`` booleans into ``Retriever.search``, the hot path stays
branch-free and the Phase 5 reranker-canary acceptance gate (RET-03) tests the
**same code path** that the production pipeline runs — the ablation does not
gate a different control flow.

Both protocols are declared ``@runtime_checkable`` in
``docintel_core.adapters.protocols``, so structural mismatches surface as
``isinstance(NullReranker(), Reranker) is False`` (caught by
``tests/test_null_adapters.py``). The classes here do **not** inherit from the
protocols — they satisfy them structurally, mirroring every existing stub
adapter (``StubReranker``, ``StubEmbedder``, ``Bm25sStore``).

Discipline:
    * No SDK imports (no ``bm25s``, ``qdrant_client``, ``sentence_transformers``,
      ``torch``, ``numpy``, ``structlog``, ``tenacity``). These classes are
      pure-Python stateless adapters.
    * No I/O, no env-var reads, no clock/RNG. Output is deterministic across
      calls and machines.
    * RESEARCH.md anti-pattern reminder — "Don't add tenacity wraps inside
      Retriever." No retry layer here either; null adapters never fail.
"""

from __future__ import annotations

from docintel_core.adapters.types import RerankedDoc
from docintel_core.types import Chunk


class NullReranker:
    """Preserve input order; satisfies the ``Reranker`` protocol structurally.

    Score is negated so descending sort by score preserves input order: the
    top of the input list (RRF rank 0) gets score ``0.0``, and the bottom
    (RRF rank ``M-1``) gets score ``-(M-1)``. Phase 5's ``Retriever._rerank``
    sorts the reranker output descending by score (matching ``BGEReranker``
    and ``StubReranker`` semantics); with ``NullReranker`` that sort yields
    the same input order.

    No inheritance from ``Reranker`` (Protocol is ``@runtime_checkable`` so
    structural satisfaction is sufficient; this mirrors every existing stub).
    """

    @property
    def name(self) -> str:
        """Adapter identifier surfaced into Phase 10 eval manifest headers."""
        return "null-reranker"

    def rerank(self, query: str, docs: list[str]) -> list[RerankedDoc]:
        """Return docs in input order with ``score = -float(rank)``.

        Args:
            query: Ignored (the null adapter does not score against the query).
            docs:  List of document strings in the order they should be
                preserved. Empty list returns ``[]``.

        Returns:
            ``list[RerankedDoc]`` where ``RerankedDoc.score = -float(i)`` for
            input position ``i``; downstream descending sort by score
            preserves the input ordering.
        """
        return [
            RerankedDoc(doc_id=str(i), text=doc, score=-float(i), original_rank=i)
            for i, doc in enumerate(docs)
        ]


class NullBM25Store:
    """Return zero candidates; satisfies the ``BM25Store`` protocol structurally.

    Phase 5's RRF then runs over dense-only — RRF of a single ranker reduces
    to that ranker's ordering, which is the desired Phase 11 dense-only
    ablation semantics.

    Must expose the FULL 6-method BM25Store protocol surface (``name``,
    ``add``, ``commit``, ``query``, ``verify``, ``last_vocab_size``) — the
    Protocol is ``@runtime_checkable`` so a missing method surfaces as
    ``isinstance(NullBM25Store(), BM25Store) is False``. No inheritance from
    the Protocol.

    No persisted state: ``add`` is a no-op, ``commit`` returns the 64-char
    zero sentinel (stable across runs so the Phase 4 ``IndexManifestBM25``
    schema's ``sha256`` field remains a hex string of the expected shape if
    a Phase 11 ablation run ever attempts to write a manifest containing the
    null store's identity), ``verify`` is trivially ``True``, and
    ``last_vocab_size`` is ``0``.
    """

    @property
    def name(self) -> str:
        """Adapter identifier surfaced into Phase 10 eval manifest headers."""
        return "null-bm25"

    def add(self, chunks: list[Chunk], text: list[str]) -> None:
        """No-op — null store has no state to accumulate."""

    def commit(self) -> str:
        """Return a stable sentinel digest for MANIFEST consistency.

        The 64-character zero string is a valid hex sha256 shape (matches the
        ``IndexManifestBM25.sha256`` field expectation) and is stable across
        calls and processes, so ablation runs that touch the manifest writer
        produce reproducible identities.
        """
        return "0" * 64

    def query(self, query_text: str, k: int) -> list[tuple[str, int, float]]:
        """Always return ``[]``.

        Phase 5's RRF then runs over dense-only; RRF of a single ranker
        reduces to that ranker's ordering.
        """
        return []

    def verify(self) -> bool:
        """Trivially true — null store has no persisted artefact to verify."""
        return True

    def last_vocab_size(self) -> int:
        """Vocab size is zero in the null store."""
        return 0
