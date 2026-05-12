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
