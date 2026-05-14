"""Four typing.Protocol classes defining the adapter seam for docintel.

Every later phase (4-13) imports through these protocols -- never directly
against a provider SDK. This seam is the load-bearing artifact for swappable
LLM, embedding, reranking, and judge implementations.

numpy import note:
    Embedder.embed()'s return type annotation references np.ndarray, so numpy
    is an unconditional import at module evaluation time. This is acceptable:
    numpy is already in uv.lock (transitive via sentence-transformers, Wave 5
    promotes it to a direct dep of docintel-core via D-11). Stub-mode CI pays
    the numpy import cost only — no torch, no SDKs.

D-08: All methods are sync-only (no async def, no streaming) for v1.
D-13: Each Protocol carries a .name property for Phase 10 manifest header
      introspection (bundle.embedder.name, bundle.llm.name, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

import numpy as np

if TYPE_CHECKING:
    from docintel_core.adapters.types import (
        CompletionResponse,
        JudgeVerdict,
        RerankedDoc,
    )

# Phase 4 D-02: DenseStore + BM25Store consume Chunk at the .add() seam. Chunk
# lives in the SAME package (docintel_core.types) so there is no import cycle —
# types.py imports only from pydantic + stdlib; adapters/protocols.py is the
# downstream consumer. Runtime import (not TYPE_CHECKING) keeps the annotations
# usable for runtime_checkable Protocol introspection (D-13 .name source).
from docintel_core.types import Chunk


@runtime_checkable
class Embedder(Protocol):
    """Converts a batch of texts to fixed-dimension float32 embeddings.

    CD-02 decision: returns np.ndarray of shape (len(texts), embedding_dim).
    Real adapter (BGE-small-en-v1.5) returns shape (N, 384). Stub adapter
    returns the same shape so dimension mismatches surface in stub mode.
    """

    @property
    def name(self) -> str:
        """Adapter identifier used in eval manifest headers (Phase 10)."""
        ...

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return float32 array of shape (len(texts), embedding_dim)."""
        ...


@runtime_checkable
class Reranker(Protocol):
    """Scores (query, document) pairs for relevance and returns sorted results.

    CD-04 decision: returns list[RerankedDoc] (Pydantic model) rather than
    list[tuple[doc, float]] for clarity in Phase 5 ablation reports.
    """

    @property
    def name(self) -> str:
        """Adapter identifier used in eval manifest headers (Phase 10)."""
        ...

    def rerank(self, query: str, docs: list[str]) -> list[RerankedDoc]:
        """Return docs sorted descending by relevance score."""
        ...


@runtime_checkable
class LLMClient(Protocol):
    """Generates text from a prompt, returning a structured response.

    D-05: Returns CompletionResponse with text, usage (TokenUsage), cost_usd,
    latency_ms, model. Phase 9 MET-05 ($/query + latency percentiles) reads
    directly from this return value.
    D-08: Sync-only for v1 — FastAPI wraps in a thread pool if needed (Phase 13).
    """

    @property
    def name(self) -> str:
        """Adapter identifier used in eval manifest headers (Phase 10)."""
        ...

    def complete(
        self,
        prompt: str,
        system: str | None = None,
    ) -> CompletionResponse:
        """Generate a completion for the given prompt.

        Args:
            prompt: The user-facing prompt text.
            system: Optional system/instruction prompt.

        Returns:
            CompletionResponse with generated text, token usage, cost, and latency.
        """
        ...


@runtime_checkable
class LLMJudge(Protocol):
    """Evaluates the faithfulness of a prediction against reference passages.

    D-07: Returns JudgeVerdict with score [0,1], passed bool, reasoning str,
    and unsupported_claims list. Phase 9 uses score for Wilson CIs (MET-03)
    and passed for pass-rate metrics (MET-04).
    D-04 real adapter: uses the OTHER provider from the generator to avoid
    circular-judge bias (cross-family judging pattern).
    D-08: Sync-only for v1.
    """

    @property
    def name(self) -> str:
        """Adapter identifier used in eval manifest headers (Phase 10)."""
        ...

    def judge(
        self,
        prediction: str,
        reference: list[str],
        rubric: str = "",
    ) -> JudgeVerdict:
        """Evaluate prediction faithfulness against reference passages.

        Args:
            prediction: The generated answer text to evaluate.
            reference:  List of reference passage strings for grounding.
            rubric:     Optional evaluation criteria / rubric text.

        Returns:
            JudgeVerdict with score, passed, reasoning, and unsupported_claims.
        """
        ...


@runtime_checkable
class DenseStore(Protocol):
    """Dense vector store for chunk embeddings (Phase 4 D-02).

    Two-phase build: ``add()`` accumulates batches; ``commit()`` finalises the
    on-disk artefact (or remote collection) and returns the sha256 / collection
    identity recorded in ``data/indices/MANIFEST.json`` (D-13).

    Concrete implementations (Plan 04-04):
        * ``NumpyDenseStore`` (stub mode) — writes ``data/indices/dense/embeddings.npy``
          + ``chunk_ids.json`` (D-04). ``commit()`` returns sha256(embeddings.npy).
        * ``QdrantDenseStore`` (real mode) — drops + recreates collection
          ``docintel-dense-v1`` (D-05/D-06). ``commit()`` returns the collection
          UUID (or another stable identifier) for the MANIFEST.dense.collection
          field.

    ``query()`` returns ``list[tuple[chunk_id, rank, score]]``. RESEARCH §Pattern 1
    pins this 3-tuple shape so RRF (Phase 5 D-11) can consume ranks directly.

    ``verify()`` re-reads the on-disk / remote state and asserts identity with
    the recorded MANIFEST entry — used by ``docintel-index verify`` (D-14).
    """

    @property
    def name(self) -> str:
        """Adapter identifier (e.g. ``"numpy-dense"``, ``"qdrant-dense-v1"``).

        Sourced into ``IndexManifest.dense`` block (D-13) and Phase 10's eval
        manifest header.
        """
        ...

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        """Buffer one batch. Caller invokes repeatedly across batches before commit().

        Args:
            chunks: Chunk metadata, length-aligned with ``vectors`` rows.
            vectors: float32 array of shape ``(len(chunks), embedder.dim)``;
                BGE-small-en-v1.5 → ``(len(chunks), 384)`` (Phase 2 D-01).
        """
        ...

    def commit(self) -> str:
        """Finalise the store and return the identity recorded in MANIFEST.

        Returns:
            For NumpyDenseStore: hex sha256 of ``embeddings.npy``.
            For QdrantDenseStore: the collection's stable identifier
            (UUID / collection name) suitable for ``MANIFEST.dense.collection``.
        """
        ...

    def query(self, q: np.ndarray, k: int) -> list[tuple[str, int, float]]:
        """Retrieve top-k chunks for a single query vector.

        Args:
            q: float32 array of shape ``(embedder.dim,)`` — one query vector.
            k: How many results to return.

        Returns:
            ``[(chunk_id, rank, score), ...]`` sorted by ascending rank.
            ``rank`` is 1-based; ``score`` is informational for ablation
            reports (Phase 5 RRF consumes rank only — D-11).
        """
        ...

    def verify(self) -> bool:
        """Re-validate against the recorded MANIFEST entry (D-14).

        Numpy: re-hash ``embeddings.npy`` and assert match with
        ``MANIFEST.dense.sha256``. Qdrant: ``client.get_collection(...)`` and
        assert points_count + vector_size + distance match the recorded values.
        """
        ...


@runtime_checkable
class BM25Store(Protocol):
    """Sparse BM25 store for lexical retrieval (Phase 4 D-07).

    Same two-phase build shape as DenseStore — ``add()`` accumulates,
    ``commit()`` finalises. Concrete implementation (Plan 04-04):
        * ``Bm25sStore`` — backed by ``bm25s`` + Porter stem + English
          stopwords (D-08, D-09). Writes ``data/indices/bm25/{index.npz, vocab.json, chunk_ids.json}``
          (D-10). ``commit()`` returns sha256(``index.npz``).

    No "tiered BM25" — there is one BM25 implementation shared across stub
    and real modes (D-07). Phase 5's RRF consumes ranks from both DenseStore
    and BM25Store (D-11 rank-only fusion).

    ``query()`` accepts a raw query string (BM25 is text-based, no embedding)
    and returns the same 3-tuple shape as DenseStore so downstream RRF code
    has a single rank-tuple contract.
    """

    @property
    def name(self) -> str:
        """Adapter identifier (e.g. ``"bm25s-en-porter"``).

        Sourced into ``IndexManifest.bm25`` block (D-13) and Phase 10's eval
        manifest header.
        """
        ...

    def add(self, chunks: list[Chunk], text: list[str]) -> None:
        """Buffer one batch.

        Args:
            chunks: Chunk metadata, length-aligned with ``text``.
            text: Pre-tokenisation chunk text (the tokenizer pipeline lives
                inside the BM25Store implementation — D-08 lowercase + stop +
                stem). The caller does NOT tokenise.
        """
        ...

    def commit(self) -> str:
        """Finalise the index and return sha256 of the on-disk ``index.npz``."""
        ...

    def query(self, query_text: str, k: int) -> list[tuple[str, int, float]]:
        """Retrieve top-k chunks for a raw text query (BM25 is text-based, no embedding).

        Args:
            query_text: Raw user query — the BM25Store applies its own
                tokenizer pipeline (D-08).
            k: How many results to return.

        Returns:
            ``[(chunk_id, rank, score), ...]`` sorted by ascending rank.
            ``rank`` is 1-based; ``score`` is informational (D-11 fusion is
            rank-based).
        """
        ...

    def verify(self) -> bool:
        """Re-hash ``index.npz`` and assert match with ``MANIFEST.bm25.sha256`` (D-14)."""
        ...

    def last_vocab_size(self) -> int:
        """Vocabulary size from the most recent ``commit()`` (sourced into MANIFEST).

        Plan 04-05's MANIFEST writer reads this via the store instance to fill
        ``IndexManifestBM25.vocab_size`` (D-13). Returns 0 if ``commit()`` has
        not been called yet. Part of the BM25Store Protocol because D-13's
        ``IndexManifestBM25.vocab_size`` is a load-bearing schema field — every
        BM25 implementation must expose its vocab size for the manifest
        contract.
        """
        ...
