"""In-process dense store backed by NumPy (D-01, D-04, D-11, CD-05).

Satisfies the ``DenseStore`` Protocol structurally (Plan 04-03,
``docintel_core.adapters.protocols``). This is the stub-mode dense backend —
real mode uses ``QdrantDenseStore`` (Plan 04-06).

Storage layout (D-04):
    data/indices/dense/
        embeddings.npy     — plain ``np.save``, float32, L2-normalized
        chunk_ids.json     — JSON list aligned to the .npy row order

Pitfall 3: ``np.save`` is byte-deterministic for float32 arrays under the
pinned ``numpy==2.4.4``. The compressed-save variant is forbidden — zlib
headers embed a timestamp that would break ``MANIFEST.dense.sha256``
byte-identity across re-runs.

Query (CD-05 + Pattern 5): cosine similarity reduces to dot product on
L2-normalized inputs; top-k via ``np.argpartition(-scores, k)`` then
``np.argsort`` of the top-k. Sub-millisecond for the 6,053-chunk corpus.

D-11 ranks-only: ``query()`` returns ``list[tuple[chunk_id, rank, score]]``
where ``rank`` is the int (the 2nd tuple element); Phase 5 RRF consumes
``rank``, ``score`` is informational only.

No tenacity retry wrap — NumPy is in-process (no network calls). The SP-3
two-logger pattern is NOT applied because this file contains no
tenacity-wrapped SDK calls and is NOT scanned by the Phase 4 CI grep gate
(``scripts/check_index_wraps.sh`` only scans for the Qdrant SDK surface).
SUGGESTION 11 — the dead ``_retry_log`` placeholder is omitted.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

import numpy as np
import structlog

from docintel_core.config import Settings
from docintel_core.types import Chunk

log = structlog.stdlib.get_logger(__name__)

_DIM: Final[int] = 384
"""Output dimensionality — matches BGE-small-en-v1.5 (Phase 2 D-01 line 174)
and StubEmbedder (``docintel_core.adapters.stub.embedder._DIM``). Dimension
mismatches surface at ``add()`` rather than at query time.
"""


class NumpyDenseStore:
    """DenseStore implementation over NumPy ``.npy`` (D-04).

    Two-phase build: ``add()`` accumulates float32 vector batches; ``commit()``
    concatenates them, writes ``embeddings.npy`` (plain ``np.save``) +
    ``chunk_ids.json``, and returns ``sha256(embeddings.npy bytes)``.
    """

    def __init__(self, cfg: Settings) -> None:
        """Initialise the buffer; no model load (this is the stub-mode store)."""
        self._cfg = cfg
        self._chunks: list[Chunk] = []
        self._vector_batches: list[np.ndarray] = []
        # Populated by ``commit()`` (or by ``query()`` via lazy disk reload).
        self._embeddings: np.ndarray | None = None
        self._chunk_ids: list[str] = []
        log.info(
            "numpy_dense_store_initialized",
            index_dir=str(Path(self._cfg.index_dir) / "dense"),
            dim=_DIM,
        )

    @property
    def name(self) -> str:
        """Adapter identifier — stable across builds."""
        return "numpy-dense-v1"

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        """Buffer one batch of chunk metadata + their float32 embeddings.

        Args:
            chunks: Chunk metadata; length must match ``vectors`` rows.
            vectors: float32 array of shape ``(len(chunks), _DIM)``. Both
                BGEEmbedder (``normalize_embeddings=True``) and StubEmbedder
                produce L2-normalized vectors at this dimensionality, so no
                defensive re-normalisation is applied here.
        """
        if vectors.shape != (len(chunks), _DIM):
            raise ValueError(
                f"NumpyDenseStore.add: vectors shape {vectors.shape!r} mismatches "
                f"expected (len(chunks)={len(chunks)}, dim={_DIM}). "
                "BGEEmbedder + StubEmbedder both return (N, 384) float32."
            )
        if vectors.dtype != np.float32:
            raise ValueError(
                f"NumpyDenseStore.add: vectors dtype {vectors.dtype!r} must be float32 "
                "(Pitfall 3 — np.save byte determinism requires pinned dtype)."
            )
        # Per-batch logging deliberately omitted (Pitfall 1 — log flood prevention).
        self._chunks.extend(chunks)
        self._vector_batches.append(vectors)

    def commit(self) -> str:
        """Concatenate buffers, write ``embeddings.npy`` + ``chunk_ids.json``, return sha256.

        Returns:
            64-char hex sha256 of the ``embeddings.npy`` bytes verbatim. The
            MANIFEST writer (Plan 04-05) records this under
            ``MANIFEST.dense.sha256`` for ``docintel-index verify`` (D-14).
        """
        dense_dir = Path(self._cfg.index_dir) / "dense"
        dense_dir.mkdir(parents=True, exist_ok=True)

        if not self._chunks:
            # Pitfall 4 empty-corpus edge case — write a (0, dim) array so
            # downstream MANIFEST verify has a hashable artifact. The full
            # corpus is never empty (6,053 chunks across 10-20 filings); this
            # path is defensive.
            log.info("numpy_dense_store_no_chunks", index_dir=str(dense_dir))
            arr = np.zeros((0, _DIM), dtype=np.float32)
        else:
            # ``copy=False`` avoids the buffer copy when the upstream array
            # is already float32 (BGEEmbedder is always float32; StubEmbedder
            # too — verified in Phase 2 tests).
            arr = np.vstack(self._vector_batches).astype(np.float32, copy=False)

        # Plain np.save — NOT the compressed-save variant (Pitfall 3).
        # zlib headers embed timestamps that would break byte-identity across
        # re-runs.
        np.save(dense_dir / "embeddings.npy", arr)

        self._chunk_ids = [c.chunk_id for c in self._chunks]
        (dense_dir / "chunk_ids.json").write_text(
            json.dumps(self._chunk_ids, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        digest = hashlib.sha256(
            (dense_dir / "embeddings.npy").read_bytes()
        ).hexdigest()

        self._embeddings = arr

        log.info(
            "numpy_dense_store_committed",
            chunk_count=len(self._chunk_ids),
            dim=_DIM,
            sha256=digest,
            index_dir=str(dense_dir),
        )
        return digest

    def query(self, q: np.ndarray, k: int) -> list[tuple[str, int, float]]:
        """Top-k cosine similarity over the in-process embedding matrix (Pattern 5).

        Args:
            q: float32 array of shape ``(_DIM,)`` — one query vector,
                L2-normalized by the caller (BGEEmbedder + StubEmbedder both
                produce unit vectors).
            k: How many results to return; clamped to corpus size when smaller.

        Returns:
            ``[(chunk_id, rank, score), ...]`` sorted by ascending rank.
        """
        if self._embeddings is None:
            self._lazy_load_from_disk()
        assert self._embeddings is not None  # narrow for mypy

        # Empty-corpus defensive: matmul on a (0, dim) array returns an empty
        # vector; argpartition would fail on that.
        if self._embeddings.shape[0] == 0:
            return []

        # Cosine similarity reduces to dot product when both sides are
        # L2-normalized (verified upstream in Phase 2).
        scores = self._embeddings @ q.astype(np.float32, copy=False)

        if k >= scores.shape[0]:
            # Edge case: K >= corpus size → just argsort all (Pattern 5).
            top_idx = np.argsort(-scores)
        else:
            # CD-05: O(N) partition; then sort just the top-K (O(K log K)).
            # ``np.argpartition`` with ``-scores`` puts the K largest at the
            # front of the partition (unsorted within themselves).
            partition_idx = np.argpartition(-scores, k)[:k]
            top_idx = partition_idx[np.argsort(-scores[partition_idx])]

        return [
            (self._chunk_ids[int(idx)], rank, float(scores[idx]))
            for rank, idx in enumerate(top_idx)
        ]

    def verify(self) -> bool:
        """File-existence + shape sanity check (D-14).

        Plan 04-05's CLI does the load-bearing sha256 re-check against
        ``MANIFEST.dense.sha256``; this method is the cheap precondition.
        """
        dense_dir = Path(self._cfg.index_dir) / "dense"
        embeddings_path = dense_dir / "embeddings.npy"
        chunk_ids_path = dense_dir / "chunk_ids.json"
        if not embeddings_path.is_file() or not chunk_ids_path.is_file():
            return False
        try:
            arr = np.load(embeddings_path)
            ids = json.loads(chunk_ids_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if arr.ndim != 2 or arr.shape[1] != _DIM:
            return False
        if arr.shape[0] != len(ids):
            return False
        return True

    def _lazy_load_from_disk(self) -> None:
        """Read-side reload — ``np.load`` + ``chunk_ids.json``."""
        dense_dir = Path(self._cfg.index_dir) / "dense"
        self._embeddings = np.load(dense_dir / "embeddings.npy")
        self._chunk_ids = json.loads(
            (dense_dir / "chunk_ids.json").read_text(encoding="utf-8")
        )
