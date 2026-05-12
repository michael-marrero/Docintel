"""Real Reranker adapter backed by BAAI/bge-reranker-base via sentence-transformers.

Model: BAAI/bge-reranker-base — 278M params, 512-token cap, CPU-runnable.
Same token cap as BGEEmbedder (D-01, D-02) so the silent-truncation canary
story is coherent: both embedding and reranking sides can exhibit truncation.

Every call to model.predict() is inside a tenacity @retry decorator (ADP-06,
D-18). The grep gate for ADP-06 checks that any file containing '.predict('
also contains 'from tenacity import'; this file satisfies that check.

No API key used. SP-4 (SecretStr.get_secret_value()) is not applicable here.
"""

from __future__ import annotations

import logging

import numpy as np
import structlog
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from docintel_core.adapters.types import RerankedDoc
from docintel_core.config import Settings

# Two-logger pattern (SP-3): stdlib logger for tenacity before_sleep_log;
# structlog bound logger for all other structured log lines.
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)


class BGEReranker:
    """Real Reranker adapter wrapping sentence-transformers CrossEncoder.

    Satisfies the Reranker Protocol structurally (no inheritance required).
    Model: BAAI/bge-reranker-base — raw logit scores, higher = more relevant.
    CPU-runnable at top-N=20 within seconds (D-02).
    """

    def __init__(self, cfg: Settings) -> None:
        """Lazy-load the CrossEncoder model.

        The 'from sentence_transformers import CrossEncoder' is inside
        __init__ (not at module top) so stub-mode CI never pays the torch
        import cost (D-12).

        Args:
            cfg: Settings instance (not consumed today; BGE has no API key
                 requirement).
        """
        from sentence_transformers import CrossEncoder  # lazy — torch cost here

        self._model = CrossEncoder("BAAI/bge-reranker-base")
        log.info(
            "bge_reranker_loaded",
            model="BAAI/bge-reranker-base",
            note="inputs longer than 512 tokens are silently truncated",
        )

    @property
    def name(self) -> str:
        """Adapter identifier for Phase 10 eval manifest headers."""
        return "bge-reranker-base"

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((OSError, RuntimeError)),
        before_sleep=before_sleep_log(_retry_log, logging.WARNING),
        reraise=True,
    )
    def rerank(self, query: str, docs: list[str]) -> list[RerankedDoc]:
        """Score (query, doc) pairs and return docs sorted by relevance.

        Scores are raw logits from the cross-encoder; higher = more relevant.
        No normalization is applied — raw scores are sufficient for ranking.

        Args:
            query: The search query string.
            docs:  List of document strings to rank against the query.

        Returns:
            List of RerankedDoc sorted descending by score.
        """
        pairs = [(query, doc) for doc in docs]
        scores: np.ndarray = self._model.predict(pairs, convert_to_numpy=True)
        results = [
            RerankedDoc(
                doc_id=str(i),
                text=doc,
                score=float(scores[i]),
                original_rank=i,
            )
            for i, doc in enumerate(docs)
        ]
        return sorted(results, key=lambda r: r.score, reverse=True)
