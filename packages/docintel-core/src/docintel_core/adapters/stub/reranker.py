"""Deterministic stub reranker -- cosine similarity over stub embeddings.

Shares the hash-based vector function with StubEmbedder (D-15). Because both
stubs use the exact same hashing scheme, ablation comparisons between
dense-only and reranked retrieval produce non-degenerate score deltas even
in stub/CI mode -- the Phase 5 reranker silent-truncation canary can be
exercised without a real cross-encoder.

No randomness, no clock reads (ADP-07).
No retry wrapping -- stubs never make network calls. The CI grep gate for
tenacity is scoped to adapters/real/ only.
"""

from __future__ import annotations

import numpy as np

from docintel_core.adapters.stub.embedder import _text_to_vector
from docintel_core.adapters.types import RerankedDoc


class StubReranker:
    """Deterministic cosine-similarity reranker for stub/CI mode.

    Satisfies the Reranker Protocol structurally (no inheritance).
    Scores each (query, doc) pair via cosine similarity over the same
    hash-based unit vectors produced by StubEmbedder.
    Deterministic: identical inputs always produce identical rankings.
    No external dependencies.
    """

    @property
    def name(self) -> str:
        """Adapter identifier for Phase 10 eval manifest headers."""
        return "stub-reranker"

    def rerank(self, query: str, docs: list[str]) -> list[RerankedDoc]:
        """Score and sort docs by cosine similarity to the query.

        Both query and doc vectors are unit-normalised (from _text_to_vector),
        so np.dot(q_vec, d_vec) == cosine_similarity(q_vec, d_vec).

        Args:
            query: The query string to score against.
            docs:  List of document strings to score and sort.

        Returns:
            List of RerankedDoc sorted descending by score.
            Empty docs list returns an empty list.
        """
        q_vec = _text_to_vector(query)
        results: list[RerankedDoc] = []
        for i, doc in enumerate(docs):
            d_vec = _text_to_vector(doc)
            score = float(np.dot(q_vec, d_vec))  # both unit-norm -> cosine
            results.append(RerankedDoc(doc_id=str(i), text=doc, score=score, original_rank=i))
        return sorted(results, key=lambda r: r.score, reverse=True)
