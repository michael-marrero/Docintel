"""Verify the committed indices against MANIFEST.json (D-14, IDX-03).

Reproducibility contract: every recorded sha256 in
``data/indices/MANIFEST.json`` matches the on-disk file's current sha256.
A mismatch returns exit code 1 (CI failure); a clean run returns 0.

The dense check dispatches on the manifest's ``dense.backend``:
    * ``"numpy"`` → re-hash ``data/indices/dense/embeddings.npy`` and
      compare against ``manifest.dense.sha256``.
    * ``"qdrant"`` → instantiate the QdrantDenseStore via the index-store
      bundle, call ``dense.verify()`` (re-queries ``get_collection`` and
      asserts points_count + vector_size + distance match the pinned
      D-06 geometry).

The bm25 check re-hashes the sorted-filename concat of
``data/indices/bm25/*.index.*`` (same algorithm Bm25sStore.commit uses)
and compares against ``manifest.bm25.sha256``.

A corpus-drift check is informational only: re-compute
``corpus_identity_hash`` from ``data/corpus/MANIFEST.json`` and compare to
``manifest.corpus_manifest_sha256``. A mismatch means "rebuild needed",
NOT "verify failed" — log a warning but still return 0 if dense + bm25
match their own recorded hashes. D-14 says "every recorded sha matches
the on-disk file"; corpus drift is orthogonal to artifact integrity.

Precondition: ``cfg.data_dir == "data"`` (mirroring
``docintel_ingest.verify.verify_idempotency`` lines 113-118 — same rationale:
MANIFEST paths are repo-root-relative). A developer overriding
``DOCINTEL_DATA_DIR`` would hit the precondition assertion and get an
actionable error message rather than a wall of spurious mismatches.

FND-11: ``cfg: Settings`` passed in by cli.py; this module does not read
environment variables.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import structlog

from docintel_core.adapters.factory import make_index_stores
from docintel_core.config import Settings
from docintel_core.types import IndexManifest

from docintel_index.manifest import (
    IndexDiscrepancy,
    corpus_identity_hash,
    sha256_file,
)

# Two-logger pattern (SP-3) — _retry_log unused here; structlog is the actual logger.
_retry_log = logging.getLogger(__name__)
log = structlog.stdlib.get_logger(__name__)


def _hash_bm25_artifacts(bm25_dir: Path) -> str:
    """Re-hash the sorted-filename concat of bm25s output files (D-14).

    Mirrors ``Bm25sStore.commit`` exactly (Plan 04-04): sha256 of the
    concatenated bytes of every ``*.index.*`` file under ``bm25_dir`` in
    sorted-filename order. ``chunk_ids.json`` is EXCLUDED (its content is
    content-derived from already-hashed Chunk metadata — Plan 04-04 Open
    Question #1 RESOLVED).
    """
    h = hashlib.sha256()
    for path in sorted(bm25_dir.glob("*.index.*")):
        h.update(path.read_bytes())
    return h.hexdigest()


def verify_indices(cfg: Settings) -> int:
    """Verify ``data/indices/MANIFEST.json`` against on-disk artifacts (D-14).

    Steps:
        1. Assert ``cfg.data_dir == "data"`` (mirrors ingest verify).
        2. Load ``data/indices/MANIFEST.json`` via
           ``IndexManifest.model_validate(json.loads(...))`` — a tampered
           manifest with an extra key fails Pydantic ``extra="forbid"`` and
           returns 1 from the wrapping try/except.
        3. Dense check: dispatch on ``manifest.dense.backend``:
             * ``"numpy"`` → re-hash ``embeddings.npy`` and compare to
               ``manifest.dense.sha256``.
             * ``"qdrant"`` → instantiate the index-store bundle and call
               ``dense.verify()`` (queries Qdrant ``get_collection``).
        4. BM25 check: re-hash sorted-filename concat of ``*.index.*``
           files and compare to ``manifest.bm25.sha256``.
        5. Corpus identity check (informational only): re-hash
           ``data/corpus/MANIFEST.json`` minus ``generated_at``; log a
           warning on drift but do NOT fail (rebuild needed, not verify
           failed).
        6. Return 0 on clean / 1 on any artifact-integrity violation.

    Args:
        cfg: Settings instance. ``cfg.data_dir`` resolves all paths.

    Returns:
        Shell exit code: 0 = clean, 1 = at least one violation.

    Raises:
        AssertionError: ``cfg.data_dir != "data"`` (the default).
    """
    assert cfg.data_dir == "data", (
        f"verify_indices requires cfg.data_dir == 'data' (the default) but got "
        f"{cfg.data_dir!r}. MANIFEST stores repo-root-relative paths; a non-"
        "default DOCINTEL_DATA_DIR breaks the cross-machine reproducibility "
        "contract. Unset DOCINTEL_DATA_DIR before running `docintel-index verify`."
    )

    index_root = Path(cfg.index_dir)
    manifest_path = index_root / "MANIFEST.json"
    if not manifest_path.is_file():
        log.error("verify_no_manifest", manifest_path=str(manifest_path))
        return 1

    # Load + schema-validate. Tampering with extra keys fails extra="forbid".
    try:
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = IndexManifest.model_validate(manifest_payload)
    except (json.JSONDecodeError, ValueError) as exc:
        log.error(
            "verify_manifest_malformed",
            manifest_path=str(manifest_path),
            error=str(exc),
        )
        return 1

    discrepancies: list[IndexDiscrepancy] = []

    # Dense check — dispatch on backend.
    if manifest.dense.backend == "numpy":
        embeddings_path = index_root / "dense" / "embeddings.npy"
        if not embeddings_path.is_file():
            log.error("verify_dense_missing", path=str(embeddings_path))
            return 1
        actual_sha = sha256_file(embeddings_path)
        expected_sha = manifest.dense.sha256 or ""
        if actual_sha != expected_sha:
            discrepancies.append(
                IndexDiscrepancy(
                    path=str(embeddings_path),
                    expected_sha256=expected_sha,
                    actual_sha256=actual_sha,
                )
            )
    else:
        # qdrant backend — service-side check via the store's verify() method.
        bundle = make_index_stores(cfg)
        if not bundle.dense.verify():
            log.error(
                "verify_qdrant_dense_failed",
                collection=manifest.dense.collection,
                expected_points_count=manifest.dense.points_count,
                expected_vector_size=manifest.dense.vector_size,
                expected_distance=manifest.dense.distance,
            )
            return 1

    # BM25 check — same algorithm Bm25sStore.commit uses.
    bm25_dir = index_root / "bm25"
    if not bm25_dir.is_dir():
        log.error("verify_bm25_dir_missing", path=str(bm25_dir))
        return 1
    actual_bm25_sha = _hash_bm25_artifacts(bm25_dir)
    if actual_bm25_sha != manifest.bm25.sha256:
        discrepancies.append(
            IndexDiscrepancy(
                path=str(bm25_dir),
                expected_sha256=manifest.bm25.sha256,
                actual_sha256=actual_bm25_sha,
            )
        )

    # Corpus drift check (informational only — D-14 separates artifact integrity
    # from corpus freshness). Warn on drift, do NOT fail.
    corpus_manifest_path = Path(cfg.data_dir) / "corpus" / "MANIFEST.json"
    if corpus_manifest_path.is_file():
        current_corpus_hash = corpus_identity_hash(corpus_manifest_path)
        if current_corpus_hash != manifest.corpus_manifest_sha256:
            log.warning(
                "verify_corpus_drift",
                manifest_recorded=manifest.corpus_manifest_sha256,
                corpus_current=current_corpus_hash,
                note="indices are byte-stable but the corpus has changed; rebuild recommended",
            )

    if discrepancies:
        for d in discrepancies:
            log.error(
                "verify_artifact_drift",
                path=d.path,
                expected_sha256=d.expected_sha256,
                actual_sha256=d.actual_sha256,
            )
        log.error("index_verify_failed", n_discrepancies=len(discrepancies))
        return 1

    log.info(
        "index_verify_clean",
        chunk_count=manifest.chunk_count,
        dense_backend=manifest.dense.backend,
        bm25_vocab_size=manifest.bm25.vocab_size,
    )
    return 0
