"""Build the dense + BM25 indices over Phase 3's chunk JSONL (IDX-01..03, D-12, D-13).

Pipeline:
    1. Resolve corpus + index roots from ``cfg.data_dir`` / ``cfg.index_dir``.
    2. Compute ``corpus_identity_hash`` over ``data/corpus/MANIFEST.json``
       (Pitfall 9 — strip ``generated_at`` before hashing).
    3. If a prior ``data/indices/MANIFEST.json`` exists AND its recorded
       ``corpus_manifest_sha256`` matches the current corpus identity hash,
       log ``index_build_skipped_unchanged_corpus`` and return the prior
       manifest unchanged (D-12 — idempotent skip path).
    4. Otherwise read all chunks from ``data/corpus/chunks/**/*.jsonl``
       via ``Chunk.model_validate_json`` per line. Empty lines are skipped
       (Pitfall 4 — empty filings ship zero-byte JSONLs).
    5. Build adapter + index-store bundles via Phase 2 ``make_adapters`` +
       Plan 04-05 Task 1 ``make_index_stores``.
    6. Embed chunks in batches of 64 (CD-07 — fits CPU memory + balances
       throughput on the 6,053-chunk corpus).
    7. Sequential ``dense.commit()`` + ``bm25.commit()`` (BM25 tokenizes the
       full corpus once at commit per Anti-Pattern §485).
    8. Compose ``IndexManifest`` (embedder + dense + bm25 + corpus identity
       + chunk count + ISO-8601 ``built_at`` + git_sha + format_version).
       Dense block dispatches on ``stores.dense.name``:
         * ``numpy-dense-v1`` → IndexManifestDense(backend="numpy", sha256=...).
         * ``qdrant-v1.18.0`` → IndexManifestDense(backend="qdrant",
           collection=..., points_count=..., vector_size=..., distance=...).
    9. Atomic write via ``_atomic_write_manifest`` (Pitfall 8 / CD-08).

D-13 manifest provenance is the load-bearing contract: Phase 10's eval
manifest header reads embedder/dense/bm25 attributes from this file.

D-12 idempotent skip path is what makes ``docintel-index build`` cheap on
CI re-runs: a corpus that has not changed produces the same manifest with
no work done.

FND-11: ``cfg: Settings`` passed in by cli.py; this module does not read
environment variables.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Final

import structlog

from docintel_core.adapters.factory import make_adapters, make_index_stores
from docintel_core.config import Settings
from docintel_core.types import (
    Chunk,
    IndexManifest,
    IndexManifestBM25,
    IndexManifestDense,
    IndexManifestEmbedder,
)

from docintel_index.manifest import (
    MANIFEST_VERSION,
    _atomic_write_manifest,
    bm25_library_version,
    compose_manifest_built_at,
    corpus_identity_hash,
)

# Two-logger pattern (SP-3) — _retry_log unused here; structlog log is the
# actual logger. Kept for grep-symmetry with peers.
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)


BATCH_SIZE: Final[int] = 64
"""Embedder batch size (CD-07).

64 chunks × 384 dim × 4 bytes ≈ 96 KiB per batch — fits comfortably in CPU
L2 cache on the 6,053-chunk corpus. Stub embedder is sub-millisecond per
batch; BGE-small-en-v1.5 (real mode) is ≈ 60 ms per batch on CPU. The full
corpus completes in roughly 6 s real / < 1 s stub.
"""


# Embedder model_id dispatch — keys on bundle.embedder.name. Stub returns
# "stub-embedder"; real returns "bge-small-en-v1.5". Phase 10's eval manifest
# header sources these names verbatim.
_EMBEDDER_MODEL_IDS: Final[dict[str, str]] = {
    "stub-embedder": "stub-hash-v1",
    "bge-small-en-v1.5": "BAAI/bge-small-en-v1.5",
}
_EMBEDDER_DIM: Final[int] = 384


def _read_all_chunks(corpus_root: Path) -> list[Chunk]:
    """Stream every Chunk record from ``data/corpus/chunks/**/*.jsonl``.

    Sorted-filename traversal for deterministic ordering across machines.
    Empty lines are skipped (Pitfall 4 — empty filings ship zero-byte
    JSONLs; sum of non-empty lines across all files == 6,053 in the
    committed corpus). Each line is parsed via
    ``Chunk.model_validate_json`` so a malformed line surfaces immediately
    as a Pydantic ValidationError rather than as a downstream type error.

    Args:
        corpus_root: ``Path(cfg.data_dir) / "corpus"`` — the chunks/ tree
            is one level deeper.

    Returns:
        Flat list of every Chunk in deterministic order.
    """
    chunks_root = corpus_root / "chunks"
    all_chunks: list[Chunk] = []
    for jsonl_path in sorted(chunks_root.rglob("*.jsonl")):
        text = jsonl_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            all_chunks.append(Chunk.model_validate_json(stripped))
    return all_chunks


def _compose_dense_block(dense_name: str, dense_identity: str) -> IndexManifestDense:
    """Dispatch on dense store ``.name`` → IndexManifestDense (D-13 polymorphic).

    NumpyDenseStore returns its ``.commit()`` value as a 64-char hex sha256.
    QdrantDenseStore returns ``"qdrant:{collection}:{points_count}:{vector_size}:{distance}"``
    — parsed here into the four qdrant-block fields.

    Args:
        dense_name: ``bundle.dense.name`` value — ``"numpy-dense-v1"`` or
            ``"qdrant-v1.18.0"``.
        dense_identity: ``bundle.dense.commit()`` return value.

    Returns:
        IndexManifestDense with the polymorphic shape per D-13.
    """
    if "numpy" in dense_name:
        # Stub mode: NumpyDenseStore.commit() returns sha256(embeddings.npy).
        return IndexManifestDense(backend="numpy", sha256=dense_identity)

    # Real mode: QdrantDenseStore.commit() returns
    # "qdrant:{collection}:{points_count}:{vector_size}:{distance}".
    parts = dense_identity.split(":", maxsplit=4)
    if len(parts) != 5 or parts[0] != "qdrant":
        raise ValueError(
            f"QdrantDenseStore.commit returned unexpected identity {dense_identity!r}; "
            "expected 'qdrant:{collection}:{points_count}:{vector_size}:{distance}'"
        )
    _, collection, points_count_s, vector_size_s, distance = parts
    return IndexManifestDense(
        backend="qdrant",
        collection=collection,
        points_count=int(points_count_s),
        vector_size=int(vector_size_s),
        distance=distance,
    )


def build_indices(cfg: Settings) -> IndexManifest:
    """Build the dense + BM25 indices and write data/indices/MANIFEST.json.

    See module docstring for the full 9-step pipeline. Returns the
    IndexManifest written to disk (or the prior one if the D-12 skip path
    fired).

    Args:
        cfg: Settings instance. ``cfg.data_dir`` resolves the corpus tree;
            ``cfg.index_dir`` resolves the index output tree; ``cfg.git_sha``
            is recorded in the manifest for provenance.

    Returns:
        The IndexManifest written (or re-loaded from disk on the skip path).

    Raises:
        FileNotFoundError: ``data/corpus/MANIFEST.json`` does not exist
            (the corpus identity hash is the load-bearing input).
    """
    corpus_root = Path(cfg.data_dir) / "corpus"
    index_root = Path(cfg.index_dir)
    index_root.mkdir(parents=True, exist_ok=True)

    # Step 2: corpus identity hash with generated_at stripped (Pitfall 9).
    corpus_manifest_path = corpus_root / "MANIFEST.json"
    current_corpus_hash = corpus_identity_hash(corpus_manifest_path)

    # Step 3: D-12 skip path. If a prior MANIFEST exists AND its
    # corpus_manifest_sha256 matches the current corpus identity hash, log
    # the skip line and return the prior manifest verbatim. This makes
    # `docintel-index build` cheap on CI re-runs (the second invocation in
    # the same CI job is sub-second).
    prior_manifest_path = index_root / "MANIFEST.json"
    if prior_manifest_path.is_file():
        prior_payload = json.loads(prior_manifest_path.read_text(encoding="utf-8"))
        if prior_payload.get("corpus_manifest_sha256") == current_corpus_hash:
            log.info(
                "index_build_skipped_unchanged_corpus",
                corpus_manifest_sha256=current_corpus_hash,
                prior_manifest_path=str(prior_manifest_path),
            )
            return IndexManifest.model_validate(prior_payload)

    # Step 4: read all chunks (Pitfall 4 — skip empty lines).
    all_chunks = _read_all_chunks(corpus_root)
    log.info(
        "index_build_started",
        chunk_count=len(all_chunks),
        corpus_root=str(corpus_root),
        index_root=str(index_root),
        corpus_manifest_sha256=current_corpus_hash,
    )

    # Step 5: adapter + index-store bundles.
    adapters = make_adapters(cfg)
    embedder = adapters.embedder
    stores = make_index_stores(cfg)

    # Step 6: batch loop. Embed → add to both stores.
    n_batches = (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE
    for batch_idx in range(n_batches):
        start = batch_idx * BATCH_SIZE
        end = start + BATCH_SIZE
        batch = all_chunks[start:end]
        batch_texts = [chunk.text for chunk in batch]
        vectors = embedder.embed(batch_texts)
        stores.dense.add(batch, vectors)
        # BM25Store.add takes (chunks, text) per the Protocol (Plan 04-04
        # SUMMARY Decision 1 — Protocol-precedence). Caller supplies text
        # so the store buffers both without re-iterating chunk.text.
        stores.bm25.add(batch, batch_texts)
        if (batch_idx + 1) % 10 == 0 or batch_idx == n_batches - 1:
            log.info(
                "index_build_progress",
                batch=batch_idx + 1,
                total_batches=n_batches,
                chunks_processed=min(end, len(all_chunks)),
            )

    # Step 7: sequential commit. dense first, then bm25 — order is
    # informational only (neither commit depends on the other).
    dense_identity = stores.dense.commit()
    bm25_identity = stores.bm25.commit()

    # Step 8: compose IndexManifest.
    # Embedder block — model_id dispatch via the lookup table. Unknown names
    # fall back to "unknown" so a future embedder name surfaces visibly in
    # the manifest rather than raising mid-build.
    embedder_model_id = _EMBEDDER_MODEL_IDS.get(embedder.name, "unknown")
    embedder_block = IndexManifestEmbedder(
        name=embedder.name,
        model_id=embedder_model_id,
        dim=_EMBEDDER_DIM,
    )

    # Dense block — polymorphic by backend, dispatched by store name.
    dense_block = _compose_dense_block(stores.dense.name, dense_identity)

    # BM25 block — Pitfall 6 library_version sourced from importlib.metadata.
    # The Bm25sStore exposes last_vocab_size() (Plan 04-04 contract). Tokenizer
    # pipeline metadata mirrors D-08 (lowercase + en stopwords + Porter stem).
    bm25_block = IndexManifestBM25(
        library="bm25s",
        library_version=bm25_library_version(),
        k1=1.5,
        b=0.75,
        tokenizer={
            "lowercase": True,
            "stopwords_lang": "en",
            "stemmer": "porter",
        },
        vocab_size=stores.bm25.last_vocab_size(),
        sha256=bm25_identity,
    )

    manifest = IndexManifest(
        embedder=embedder_block,
        dense=dense_block,
        bm25=bm25_block,
        corpus_manifest_sha256=current_corpus_hash,
        chunk_count=len(all_chunks),
        built_at=compose_manifest_built_at(),
        git_sha=cfg.git_sha,
        format_version=MANIFEST_VERSION,
    )

    # Step 9: atomic write (Pitfall 8 / CD-08).
    _atomic_write_manifest(prior_manifest_path, manifest)

    log.info(
        "index_build_completed",
        chunk_count=len(all_chunks),
        dense_backend=dense_block.backend,
        bm25_vocab_size=bm25_block.vocab_size,
        bm25_library_version=bm25_block.library_version,
        manifest_path=str(prior_manifest_path),
    )
    return manifest
