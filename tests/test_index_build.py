"""Wave 0 scaffold — IDX-01 / IDX-02 cross-store alignment / Pitfall 9 corpus-hash tests.

Covers VALIDATION.md Per-Task Verification Map rows for IDX-01 (stub dense build
writes ``data/indices/dense/embeddings.npy`` + ``chunk_ids.json``), IDX-02 (BM25
and dense stores share the same ``chunk_ids.json`` list in the same order), and
Pitfall 9 (``corpus_identity_hash`` excludes ``generated_at`` so the corpus hash
is stable across runs even when the corpus MANIFEST gets a fresh timestamp).

Plans 04-04/04-05 landed ``packages/docintel-index/src/docintel_index/build.py``
and the ``uv run docintel-index build`` CLI; Plan 04-07 Task 1 removed the
former xfail markers so these tests now run as hard assertions.

Analog: ``tests/test_chunk_idempotency.py`` — same ``_REPO_ROOT`` constant,
same ``subprocess.run(... check=False, capture_output=True ...)`` shape.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from docintel_index.build import corpus_identity_hash

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_stub_dense_build_writes_npy(tmp_path: Path) -> None:
    """IDX-01: stub-mode ``docintel-index build`` writes the dense + manifest artifacts."""
    result = subprocess.run(
        ["uv", "run", "docintel-index", "build"],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert (
        result.returncode == 0
    ), f"docintel-index build exited {result.returncode}: stderr={result.stderr!r}"

    indices_root = _REPO_ROOT / "data" / "indices"
    npy_path = indices_root / "dense" / "embeddings.npy"
    chunk_ids_path = indices_root / "dense" / "chunk_ids.json"
    manifest_path = indices_root / "MANIFEST.json"

    assert npy_path.is_file(), f"dense embeddings.npy missing: {npy_path}"
    assert chunk_ids_path.is_file(), f"dense chunk_ids.json missing: {chunk_ids_path}"
    assert manifest_path.is_file(), f"MANIFEST.json missing: {manifest_path}"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert (
        manifest["embedder"]["name"] == "stub-embedder"
    ), f"stub-mode default embedder name must be 'stub-embedder' (FND-08); got {manifest['embedder'].get('name')!r}"


def test_dense_and_bm25_share_chunk_ids() -> None:
    """IDX-02: dense + bm25 stores carry the same ordered chunk_ids list, length == corpus chunk count."""
    indices_root = _REPO_ROOT / "data" / "indices"
    dense_ids = json.loads((indices_root / "dense" / "chunk_ids.json").read_text(encoding="utf-8"))
    bm25_ids = json.loads((indices_root / "bm25" / "chunk_ids.json").read_text(encoding="utf-8"))

    assert dense_ids == bm25_ids, (
        "dense and bm25 chunk_ids.json must be byte-identical lists — "
        "IDX-02 cross-store alignment"
    )

    corpus_chunks_root = _REPO_ROOT / "data" / "corpus" / "chunks"
    expected_count = 0
    for jsonl in sorted(corpus_chunks_root.rglob("*.jsonl")):
        expected_count += sum(
            1 for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    assert len(dense_ids) == expected_count, (
        f"chunk_ids length ({len(dense_ids)}) does not match corpus chunk count ({expected_count}) — "
        "Pitfall 4 empty-filing handling"
    )


def test_corpus_hash_ignores_generated_at(tmp_path: Path) -> None:
    """Pitfall 9: corpus_identity_hash strips ``generated_at`` so re-runs are hash-stable."""
    source = _REPO_ROOT / "data" / "corpus" / "MANIFEST.json"
    payload = json.loads(source.read_text(encoding="utf-8"))

    copy_a = tmp_path / "manifest_a.json"
    copy_b = tmp_path / "manifest_b.json"
    copy_a.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    # Rewrite generated_at in the second copy — any other field staying constant
    # means the identity hash MUST be equal across both files.
    payload["generated_at"] = "1999-12-31T23:59:59Z"
    copy_b.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    hash_a = corpus_identity_hash(copy_a)
    hash_b = corpus_identity_hash(copy_b)
    assert hash_a == hash_b, (
        "corpus_identity_hash must drop generated_at before hashing — Pitfall 9. "
        f"hash_a={hash_a!r} hash_b={hash_b!r}"
    )

    # Sanity: the raw bytes ARE different (so we're actually testing the strip).
    assert (
        hashlib.sha256(copy_a.read_bytes()).hexdigest()
        != hashlib.sha256(copy_b.read_bytes()).hexdigest()
    ), "test fixture invalid — copy_a and copy_b are byte-identical so we're not exercising the strip"


def test_build_skips_empty_filings() -> None:
    """Pitfall 4: ``chunk_count`` in MANIFEST matches the actual non-zero chunk count from JSONL files.

    AMZN/META/XOM × 3 FYs ship 0-chunk JSONLs (empty 10-K artifacts); the build
    must not double-count those into the index.
    """
    indices_root = _REPO_ROOT / "data" / "indices"
    manifest = json.loads((indices_root / "MANIFEST.json").read_text(encoding="utf-8"))

    corpus_chunks_root = _REPO_ROOT / "data" / "corpus" / "chunks"
    actual_count = 0
    for jsonl in sorted(corpus_chunks_root.rglob("*.jsonl")):
        actual_count += sum(
            1 for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()
        )

    assert manifest["chunk_count"] == actual_count, (
        f"MANIFEST chunk_count={manifest['chunk_count']} != actual non-empty chunks={actual_count} — "
        "Pitfall 4 empty-filing skip"
    )
