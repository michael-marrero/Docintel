"""Wave 0 scaffold — IDX-01 real-mode integration test (Qdrant + BGE-small-en-v1.5).

Covers VALIDATION.md real-mode rows for IDX-01: ``docintel-index build`` in
real mode (``DOCINTEL_LLM_PROVIDER=real``) creates the ``docintel-dense-v1``
Qdrant collection with 384-dim cosine-similarity vectors, populates one point
per chunk, and writes a MANIFEST.json whose ``dense.backend == "qdrant"``,
``dense.points_count == chunk_count``, ``dense.vector_size == 384``, and
``dense.distance == "Cosine"``. The embedder block carries
``embedder.name == "bge-small-en-v1.5"`` (Plan 04-04 BGE adapter).

This file is a Wave 0 scaffold. It carries BOTH:

  * ``@pytest.mark.real`` — gated behind ``-m real``; default ``pytest`` deselects
    these tests so they never run in stub-mode CI. The marker is registered
    in pyproject.toml by Plan 04-02 (parallel wave 1).
  * ``@pytest.mark.xfail(strict=False, reason=...)`` — applied module-wide so
    the file collects without errors before Plan 04-04 (QdrantDenseStore +
    factory wiring) and Plan 04-05 (build pipeline) ship.

Plan 04-07 Task 2 removes ONLY the ``pytest.mark.xfail`` element from the
``pytestmark`` list — the ``pytest.mark.real`` element stays so the file
remains gated by ``pytest -m real`` (no accidental real-mode invocation
against an absent Qdrant service). Real-mode execution path is
Plan 04-06's ``real-index-build`` GitHub workflow_dispatch job, per D-20.

Refs: IDX-01 real-mode; D-20 workflow_dispatch only; Plan 04-04 (QdrantDenseStore
+ factory + embedder factory); Plan 04-05 (build pipeline); Plan 04-06 (CI job);
Plan 04-07 (xfail removal — real marker stays).

Analog: ``tests/test_chunk_idempotency.py`` — same ``_REPO_ROOT`` constant +
``subprocess.run(check=False, capture_output=True)`` pattern.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

# Module-level marker list — applies BOTH markers to every test below.
# Plan 04-07 Task 2 removes ONLY the xfail element from this list;
# pytest.mark.real stays so the file remains gated by ``pytest -m real``.
pytestmark = [
    pytest.mark.real,
    pytest.mark.xfail(
        strict=False,
        reason=(
            "implementations land in Plans 04-04/04-05; gated CI lands in Plan 04-06; "
            "xfail removed in Plan 04-07 Task 2 (real marker stays)"
        ),
    ),
]

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_qdrant_collection_created() -> None:
    """IDX-01 real-mode: ``docintel-index build`` creates the Qdrant collection + manifest."""
    if os.environ.get("DOCINTEL_LLM_PROVIDER") != "real":
        pytest.skip("real-mode test requires DOCINTEL_LLM_PROVIDER=real")

    result = subprocess.run(
        ["uv", "run", "docintel-index", "build"],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert (
        result.returncode == 0
    ), f"docintel-index build (real) exited {result.returncode}: stderr={result.stderr!r}"

    manifest = json.loads(
        (_REPO_ROOT / "data" / "indices" / "MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["dense"]["backend"] == "qdrant", (
        f"real-mode build must set dense.backend='qdrant'; got {manifest['dense']['backend']!r}"
    )
    assert manifest["dense"]["collection"] == "docintel-dense-v1", (
        f"real-mode build must use canonical collection name 'docintel-dense-v1'; "
        f"got {manifest['dense'].get('collection')!r}"
    )
    assert manifest["dense"]["points_count"] == manifest["chunk_count"], (
        f"dense.points_count ({manifest['dense']['points_count']}) must equal "
        f"chunk_count ({manifest['chunk_count']}) — one point per chunk"
    )
    assert manifest["dense"]["vector_size"] == 384, (
        f"dense.vector_size must be 384 for BGE-small-en-v1.5; "
        f"got {manifest['dense']['vector_size']!r}"
    )
    assert manifest["dense"]["distance"] == "Cosine", (
        f"dense.distance must be 'Cosine' (BGE was trained with cosine); "
        f"got {manifest['dense']['distance']!r}"
    )


def test_qdrant_verify_clean() -> None:
    """IDX-01 real-mode: ``docintel-index verify`` exits 0 on a clean build."""
    if os.environ.get("DOCINTEL_LLM_PROVIDER") != "real":
        pytest.skip("real-mode test requires DOCINTEL_LLM_PROVIDER=real")

    result = subprocess.run(
        ["uv", "run", "docintel-index", "verify"],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert (
        result.returncode == 0
    ), f"docintel-index verify (real) exited {result.returncode}: stderr={result.stderr!r}"


def test_real_mode_embedder_is_bge() -> None:
    """IDX-01 real-mode: MANIFEST records the BGE-small-en-v1.5 embedder identity."""
    if os.environ.get("DOCINTEL_LLM_PROVIDER") != "real":
        pytest.skip("real-mode test requires DOCINTEL_LLM_PROVIDER=real")

    manifest = json.loads(
        (_REPO_ROOT / "data" / "indices" / "MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["embedder"]["name"] == "bge-small-en-v1.5", (
        f"real-mode embedder.name must be 'bge-small-en-v1.5'; "
        f"got {manifest['embedder']['name']!r}"
    )
    assert manifest["embedder"]["model_id"] == "BAAI/bge-small-en-v1.5", (
        f"real-mode embedder.model_id must be 'BAAI/bge-small-en-v1.5'; "
        f"got {manifest['embedder']['model_id']!r}"
    )
    assert manifest["embedder"]["dim"] == 384, (
        f"BGE-small-en-v1.5 produces 384-dim vectors; got {manifest['embedder']['dim']!r}"
    )
