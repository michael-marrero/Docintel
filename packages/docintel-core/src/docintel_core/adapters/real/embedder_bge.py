"""Real embedder backed by BAAI/bge-small-en-v1.5 via sentence-transformers.

Model: BAAI/bge-small-en-v1.5 — 384-dim unit vectors, 512-token cap.
512-token cap is a structural property of this model. The Phase 5 reranker
silent-truncation canary exists specifically to detect truncation of inputs
longer than 512 tokens. BGEEmbedder exposes max_seq_length = 512 as a class
attribute so the canary can assert against it.

Every call to model.encode() is inside a tenacity @retry decorator (ADP-06,
D-18). The retry covers transient OSError and RuntimeError conditions (e.g.,
transient file-system errors, CPU memory pressure) — NOT network calls (there
is no network call here; inference is local). The grep gate for ADP-06 checks
that any file containing '.encode(' also contains 'from tenacity import'; this
file satisfies that check.

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

from docintel_core.config import Settings

# Two-logger pattern (SP-3): stdlib logger for tenacity before_sleep_log;
# structlog bound logger for all other structured log lines.
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)


class BGEEmbedder:
    """Real Embedder adapter wrapping sentence-transformers SentenceTransformer.

    Satisfies the Embedder Protocol structurally (no inheritance required).
    Model: BAAI/bge-small-en-v1.5 — 384-dim normalized float32 vectors.

    max_seq_length is a class attribute so Phase 5's silent-truncation canary
    can read BGEEmbedder.max_seq_length without instantiating the adapter.
    """

    max_seq_length: int = 512  # Phase 5 canary asserts against this

    def __init__(self, cfg: Settings) -> None:
        """Lazy-load the SentenceTransformer model.

        The 'from sentence_transformers import SentenceTransformer' is inside
        __init__ (not at module top) so stub-mode CI never pays the torch
        import cost (D-12). The model download is cached at
        ~/.cache/huggingface/ after the first instantiation.

        Args:
            cfg: Settings instance (used for future per-env config; not
                 consumed today since BGE has no API key requirement).
        """
        from sentence_transformers import SentenceTransformer  # lazy — torch cost here

        self._model = SentenceTransformer("BAAI/bge-small-en-v1.5")
        # Log once at adapter creation — NOT on every call (Pitfall 1: flood prevention).
        log.info(
            "bge_embedder_loaded",
            model="BAAI/bge-small-en-v1.5",
            max_seq_length=self.max_seq_length,
            note="inputs longer than 512 tokens are silently truncated",
        )

    @property
    def name(self) -> str:
        """Adapter identifier for Phase 10 eval manifest headers."""
        return "bge-small-en-v1.5"

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((OSError, RuntimeError)),
        before_sleep=before_sleep_log(_retry_log, logging.WARNING),
        reraise=True,
    )
    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a batch of texts using BGE-small-en-v1.5.

        Returns normalized float32 array of shape (len(texts), 384).
        Inputs longer than 512 tokens are silently truncated by the tokenizer
        (BGE structural property; logged once in __init__; Phase 5 canary
        detects quality degradation from truncation).

        Args:
            texts: List of text strings to embed.

        Returns:
            np.ndarray of shape (len(texts), 384), dtype float32, L2-normalized.
        """
        result = self._model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(result, dtype=np.float32)
