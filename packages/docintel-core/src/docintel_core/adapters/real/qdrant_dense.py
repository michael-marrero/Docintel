"""Real DenseStore backed by Qdrant v1.18.0 (D-06, D-21, amended CD-06, Pitfall 1).

Satisfies the ``DenseStore`` Protocol structurally (Plan 04-03,
``docintel_core.adapters.protocols``). This is the real-mode dense backend —
stub mode uses ``NumpyDenseStore`` (Plan 04-04).

Collection geometry (D-06): collection name ``docintel-dense-v1``,
``vector_size=384`` (BGE-small-en-v1.5 dim), ``distance=Cosine`` (BGE was
trained with cosine similarity). ``commit()`` drops + recreates the
collection per run so the artifact is byte-identity-stable across rebuilds
(no incremental upsert drift).

Point IDs (amended CD-06, Pitfall 1): Qdrant rejects arbitrary string point
IDs (``UnexpectedResponse 400`` per Qdrant maintainer #3461 / #5646). The
fix is mechanical and preserves the spirit of CD-06: derive a deterministic
UUID via ``uuid.uuid5(DOCINTEL_CHUNK_NAMESPACE, chunk_id)`` and store the
human-readable ``chunk_id`` in ``point.payload["chunk_id"]``. The namespace
UUID is pinned at module level so the mapping is stable across machines and
dep bumps. Plan 04-01's ``tests/test_qdrant_point_ids.py`` carries the
matching literal value — both sides drift together or not at all.

SDK calls (RESEARCH §Pattern 6, §Pitfall 5, §State of the Art): every
Qdrant SDK call site is encapsulated in a private helper method decorated
with ``@retry`` per D-21. The retry policy targets the transient I/O
exception (``ResponseHandlingException``) and bounded backoff
(``wait_exponential(min=1, max=20), stop_after_attempt(5)``). The 4xx/5xx
schema-violation exception (``UnexpectedResponse``) is NOT retried — those
must fail fast. The bulk-insert helper ``upload_points`` is preferred over
the incremental-insert variant for the full batch (Pitfall 5); the v1.18
query helper ``query_points`` is the successor to the deprecated v1.17
search helper. The CI grep gate ``scripts/check_index_wraps.sh`` asserts
that this file imports ``tenacity`` (D-21 — ADP-06 analog for Phase 4).

Payload (RESEARCH §Anti-Pattern line 481): each point's payload carries
ONLY ``{"chunk_id": "..."}``. No chunk text, no embeddings, no metadata.
The source of truth for chunk text is ``data/corpus/chunks/**/*.jsonl``
which is already public-committed. T-4-V5-04 threat disposition: a leaked
Qdrant collection reveals the chunk-id set (same as the public corpus) and
the embeddings (derived from public text). No information escalation.

Two-logger pattern (SP-3): stdlib logger for tenacity ``before_sleep_log``;
structlog bound logger for all other structured log lines. Same shape as
``embedder_bge.py`` lines 35-38.

Lazy-import discipline (D-12): the qdrant_client imports live at module
TOP here because this entire module is imported lazily inside
``make_index_stores``'s real branch (factory.py). Module-top imports also
make this file visible to ``scripts/check_index_wraps.sh`` which greps for
the ``qdrant_client`` token. Stub-mode CI never imports this module so
never pays the qdrant_client import cost.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Final

import numpy as np
import structlog
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from qdrant_client.models import Distance, PointStruct, VectorParams
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from docintel_core.config import Settings
from docintel_core.types import Chunk

# Two-logger pattern (SP-3) — stdlib for tenacity before_sleep_log; structlog
# for all structured log lines. Same shape as embedder_bge.py:35-38.
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)


# Pinned namespace UUID for chunk_id → point_id derivation (amended CD-06,
# Pitfall 1). Computed once via:
#   python -c "import uuid; print(uuid.uuid5(uuid.NAMESPACE_DNS, 'docintel.dense.v1'))"
# The literal value lives here (NOT computed at import time) so any drift is
# visible in code review. tests/test_qdrant_point_ids.py carries the matching
# literal; both sides drift together or not at all.
DOCINTEL_CHUNK_NAMESPACE: Final[uuid.UUID] = uuid.UUID("576cc79e-7285-5efc-8e6e-b66d3e6f92ae")


_VECTOR_SIZE: Final[int] = 384
"""BGE-small-en-v1.5 dim (Phase 2 D-01). Pinned for D-06 collection geometry."""


def chunk_id_to_point_id(chunk_id: str) -> str:
    """Deterministic UUID derivation: ``uuid5(DOCINTEL_CHUNK_NAMESPACE, chunk_id)``.

    Qdrant accepts UUID strings as point IDs but rejects arbitrary
    application-defined strings (``UnexpectedResponse 400``). uuid5 is
    sha-1-based and content-addressed: same ``chunk_id`` always maps to the
    same point ID across machines, builds, and dep bumps.

    The human-readable ``chunk_id`` is stashed in ``point.payload["chunk_id"]``
    so ``query()`` returns the application-facing ID without reverse-lookup
    cost (Pitfall 1, amended CD-06).

    Args:
        chunk_id: Application-side chunk identifier
            (e.g. ``"AAPL-FY2024-Item-1A-007"``).

    Returns:
        Lowercase UUID string suitable for ``PointStruct(id=...)``.
    """
    return str(uuid.uuid5(DOCINTEL_CHUNK_NAMESPACE, chunk_id))


class QdrantDenseStore:
    """DenseStore implementation over Qdrant v1.18.0 (D-06).

    Two-phase build: ``add()`` accumulates float32 vector batches; ``commit()``
    drops + recreates the collection (idempotent re-build per D-06), uploads
    one point per chunk via the bulk-insert helper ``upload_points`` (NOT the
    incremental-insert variant — Pitfall 5), then reads the collection-info
    helper ``get_collection`` to record the final geometry (points_count,
    vector_size, distance) on the instance.

    ``query()`` uses the v1.18 query helper ``query_points`` (successor to
    the deprecated v1.17 search helper) and recovers application-side
    chunk_ids from ``point.payload["chunk_id"]``.

    ``verify()`` re-reads ``client.get_collection`` and confirms the
    SERVICE-side identity (points_count > 0, vector_size == 384,
    distance == "Cosine"). Plan 04-05's verify.py CLI does the load-bearing
    MANIFEST-block comparison against the recorded values.

    Every ``self._client.*`` call site is encapsulated in a private helper
    method decorated with ``@retry`` per D-21. The CI grep gate
    ``scripts/check_index_wraps.sh`` asserts the tenacity import is present.
    """

    def __init__(self, cfg: Settings) -> None:
        """Initialise the buffer + open the Qdrant HTTP client.

        Args:
            cfg: Settings instance. ``cfg.qdrant_url`` resolves the HTTP
                endpoint (default ``http://qdrant:6333`` — the docker-compose
                service-name target). ``cfg.qdrant_collection`` defaults to
                ``"docintel-dense-v1"`` (D-06).
        """
        self._cfg = cfg
        self._client = QdrantClient(url=cfg.qdrant_url)
        self._collection = cfg.qdrant_collection
        self._chunks: list[Chunk] = []
        self._vector_batches: list[np.ndarray] = []
        # Populated by commit() / verify(); used by Plan 04-05's MANIFEST writer.
        self._points_count: int = 0
        self._vector_size: int = 0
        self._distance: str = ""
        log.info(
            "qdrant_dense_store_initialized",
            url=cfg.qdrant_url,
            collection=self._collection,
            vector_size=_VECTOR_SIZE,
        )

    @property
    def name(self) -> str:
        """Adapter identifier — pinned to the SDK version for MANIFEST provenance.

        The literal ``"qdrant-v1.18.0"`` is fine — a future SDK bump
        regenerates the MANIFEST. Phase 10's eval manifest header sources
        this verbatim.
        """
        return "qdrant-v1.18.0"

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        """Buffer one batch of chunk metadata + their float32 embeddings.

        Args:
            chunks: Chunk metadata; length must match ``vectors`` rows.
            vectors: float32 array of shape ``(len(chunks), 384)``. Both
                BGEEmbedder and StubEmbedder produce L2-normalized 384-dim
                float32 vectors at this stage.
        """
        if vectors.shape != (len(chunks), _VECTOR_SIZE):
            raise ValueError(
                f"QdrantDenseStore.add: vectors shape {vectors.shape!r} mismatches "
                f"expected (len(chunks)={len(chunks)}, dim={_VECTOR_SIZE}). "
                "BGEEmbedder + StubEmbedder both return (N, 384) float32."
            )
        if vectors.dtype != np.float32:
            raise ValueError(
                f"QdrantDenseStore.add: vectors dtype {vectors.dtype!r} must be "
                "float32 (collection vector_size is 384-dim float32)."
            )
        # Per-batch logging deliberately omitted (Pitfall 1 — log flood prevention).
        self._chunks.extend(chunks)
        self._vector_batches.append(vectors)

    def commit(self) -> str:
        """Drop + recreate the collection, upload all points, return identity string.

        Steps:
            1. ``_delete_collection_safe()`` — drop existing collection
               (idempotent re-build per D-06). 404 is treated as success.
            2. ``_create_collection()`` — create collection with
               ``VectorParams(size=384, distance=Cosine)``.
            3. Concatenate buffered vectors.
            4. Build ``PointStruct`` iterator: each point's ID is
               ``uuid5(NS, chunk_id)``; payload is ``{"chunk_id": ...}`` only
               (RESEARCH §Anti-Pattern §481 — no text in payload).
            5. ``_upload_points()`` — ``client.upload_points(...)`` with
               ``batch_size=256, parallel=1, wait=True`` (Pitfall 5).
            6. ``_get_collection_info()`` — record points_count + vector_size +
               distance on the instance for query() / verify() / MANIFEST.

        Returns:
            Identity string in the format
            ``"qdrant:{collection}:{points_count}:{vector_size}:{distance}"``
            for ``_dense_id`` traceability. Plan 04-05's build.py composes
            ``IndexManifestDense`` from these fields (no on-disk .npy to hash).
        """
        # Step 1: drop existing collection (idempotent).
        self._delete_collection_safe()
        # Step 2: create collection with pinned geometry (D-06).
        self._create_collection()

        # Step 3: concatenate buffered vectors. Empty-corpus edge case
        # (Pitfall 4) — defensively handle the (0, 384) case so the upload
        # iterator is empty rather than erroring.
        if not self._chunks:
            log.info("qdrant_dense_store_no_chunks", collection=self._collection)
            arr = np.zeros((0, _VECTOR_SIZE), dtype=np.float32)
        else:
            arr = np.vstack(self._vector_batches).astype(np.float32, copy=False)

        # Step 4: build PointStruct iterator. Payload carries the human-readable
        # chunk_id only — no text, no metadata (Anti-Pattern §481, T-4-V5-04).
        points = [
            PointStruct(
                id=chunk_id_to_point_id(chunk.chunk_id),
                vector=arr[i].tolist(),
                payload={"chunk_id": chunk.chunk_id},
            )
            for i, chunk in enumerate(self._chunks)
        ]

        # Step 5: upload via wrapped helper (only if there is something to upload).
        if points:
            self._upload_points(points)

        # Step 6: record final geometry from the server side.
        info = self._get_collection_info()
        # info.points_count is Optional[int] in qdrant-client; defensively
        # coerce to 0 if missing.
        self._points_count = int(info.points_count) if info.points_count is not None else 0
        # info.config.params.vectors is the VectorParams (or Mapping for named
        # vectors — D-06 uses unnamed/default).
        vectors_config: Any = info.config.params.vectors
        self._vector_size = int(vectors_config.size)
        # Use the enum's `.value` ("Cosine") rather than `.name` ("COSINE"):
        # types.py:319 + verify() and MANIFEST schema all expect the
        # serialized form per Phase 4 D-06. Surfaced by workflow_dispatch
        # run 25947851137 — commit stored "COSINE", verify compared to
        # "Cosine", mismatch killed the D-14 gate on every healthy collection.
        self._distance = str(vectors_config.distance.value)

        identity = (
            f"qdrant:{self._collection}:{self._points_count}:"
            f"{self._vector_size}:{self._distance}"
        )
        log.info(
            "qdrant_dense_store_committed",
            collection=self._collection,
            points_count=self._points_count,
            vector_size=self._vector_size,
            distance=self._distance,
        )
        return identity

    def query(self, q: np.ndarray, k: int) -> list[tuple[str, int, float]]:
        """Top-k cosine similarity via ``client.query_points`` (v1.18 successor to .search).

        Args:
            q: float32 array of shape ``(384,)`` — one query vector,
                L2-normalized by the caller (BGEEmbedder + StubEmbedder both
                produce unit vectors).
            k: How many results to return.

        Returns:
            ``[(chunk_id, rank, score), ...]`` sorted by ascending rank.
            ``rank`` is 0-based; ``score`` is the Qdrant similarity score
            (informational for ablation reports — D-11 RRF consumes rank only).
        """
        response = self._query_points(q.astype(np.float32, copy=False).tolist(), k)
        out: list[tuple[str, int, float]] = []
        for rank, point in enumerate(response.points):
            # Defensive: payload should always carry "chunk_id" (we wrote it
            # at upload time). If missing, skip rather than crash — surfaces
            # as a quiet drop in query results rather than a hard failure.
            payload = point.payload or {}
            chunk_id = payload.get("chunk_id")
            if not isinstance(chunk_id, str):
                continue
            out.append((chunk_id, rank, float(point.score)))
        return out

    def verify(self) -> bool:
        """Re-read ``client.get_collection`` + ``client.count`` and confirm SERVICE-side identity (D-14).

        Returns True iff the collection exists with ``points_count > 0``,
        ``vector_size == 384``, and ``distance == "Cosine"``. Plan 04-05's
        verify.py CLI does the load-bearing comparison against the MANIFEST-
        recorded values; this method confirms the server identity matches
        the pinned D-06 geometry.

        **Phase 6 / Plan 04-05 amendment (workflow_dispatch run 25947078366):**
        ``CollectionInfo.points_count`` is populated lazily by Qdrant's
        optimizer — immediately after a batch insert it can read 0 or None
        even with ``wait=True`` on every upsert. ``client.count(exact=True)``
        is the load-bearing exact count; ``get_collection`` is used only for
        the static geometry (vector_size + distance). Without this split,
        a verify call that races the optimizer reports failure on a healthy
        collection (D-14 false positive).
        """
        try:
            info = self._get_collection_info()
            count_result = self._count_points_exact()
        except (ResponseHandlingException, UnexpectedResponse):
            return False
        points_count = int(count_result.count)
        if points_count == 0:
            return False
        vectors_config: Any = info.config.params.vectors
        if int(vectors_config.size) != _VECTOR_SIZE:
            return False
        # Match commit()'s `.value` discipline (see line ~265 comment).
        if str(vectors_config.distance.value) != "Cosine":
            return False
        return True

    # ----- Private @retry-wrapped helpers (one per qdrant_client.* call site) -----
    #
    # D-21: every Qdrant SDK call site is tenacity-wrapped with the verbatim
    # policy from embedder_bge.py:81-87 BUT with retry_if_exception_type
    # targeting ResponseHandlingException (transient I/O) rather than
    # (OSError, RuntimeError). UnexpectedResponse (4xx/5xx schema errors)
    # is NOT retried — those must fail fast.

    def _delete_collection_safe(self) -> None:
        """Drop the collection if it exists; treat 404 as success.

        ``client.delete_collection`` raises ``UnexpectedResponse`` with
        ``status_code == 404`` when the collection does not exist. The
        try/except below treats that case as a successful idempotent delete.
        Other UnexpectedResponse codes (400/401/403/5xx) propagate so the
        outer @retry policy can decide whether to retry (only transient I/O
        is retried; schema errors are not).
        """
        try:
            self._delete_collection()
        except UnexpectedResponse as exc:
            # Defensive 404 swallow: idempotent delete is the D-06 contract.
            # Other status codes propagate so the caller sees the real error.
            status_code = getattr(exc, "status_code", None)
            if status_code == 404:
                return
            raise

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(ResponseHandlingException),
        before_sleep=before_sleep_log(_retry_log, logging.WARNING),
        reraise=True,
    )
    def _delete_collection(self) -> None:
        """Wrapped ``client.delete_collection`` — transient I/O is retried."""
        self._client.delete_collection(collection_name=self._collection)

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(ResponseHandlingException),
        before_sleep=before_sleep_log(_retry_log, logging.WARNING),
        reraise=True,
    )
    def _create_collection(self) -> None:
        """Wrapped ``client.create_collection`` — D-06 geometry pinned."""
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
        )

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(ResponseHandlingException),
        before_sleep=before_sleep_log(_retry_log, logging.WARNING),
        reraise=True,
    )
    def _upload_points(self, points: list[PointStruct]) -> None:
        """Wrapped ``upload_points`` — Pitfall 5 (NOT the incremental-insert variant)."""
        self._client.upload_points(
            collection_name=self._collection,
            points=points,
            batch_size=256,
            parallel=1,
            wait=True,
        )

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(ResponseHandlingException),
        before_sleep=before_sleep_log(_retry_log, logging.WARNING),
        reraise=True,
    )
    def _query_points(self, query_vector: list[float], k: int) -> Any:
        """Wrapped ``client.query_points`` — v1.18 successor to deprecated ``.search``."""
        return self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=k,
        )

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(ResponseHandlingException),
        before_sleep=before_sleep_log(_retry_log, logging.WARNING),
        reraise=True,
    )
    def _get_collection_info(self) -> Any:
        """Wrapped ``client.get_collection`` — carries ``points_count`` + ``vectors`` config.

        Note: ``CollectionInfo.points_count`` is populated by Qdrant's optimizer
        and may be stale (None or 0) immediately after batch insertion. Use
        ``_count_points_exact`` for the load-bearing count check (verify()
        amendment for workflow_dispatch run 25947078366).
        """
        return self._client.get_collection(collection_name=self._collection)

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(ResponseHandlingException),
        before_sleep=before_sleep_log(_retry_log, logging.WARNING),
        reraise=True,
    )
    def _count_points_exact(self) -> Any:
        """Wrapped ``client.count`` with ``exact=True`` — bypasses the optimizer lag.

        Returns a ``CountResult`` whose ``.count`` is the EXACT current point
        count in the collection, irrespective of optimizer state. This is the
        D-14 verify path's count source; ``_get_collection_info()`` still
        carries the static geometry (vector_size + distance).
        """
        return self._client.count(collection_name=self._collection, exact=True)
