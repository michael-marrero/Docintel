"""Idempotency tests for ``docintel-index build`` (D-12 + Pitfall 9).

Covers Phase 4's headline acceptance gate:

* ``test_skip_unchanged_corpus`` — Running ``docintel-index build`` twice
  against an unchanged ``data/corpus/MANIFEST.json`` short-circuits on the
  second invocation. The first run writes the index + MANIFEST; the second
  run hashes the corpus MANIFEST, matches the prior index MANIFEST's
  ``corpus_manifest_sha256``, and exits 0 fast with the structlog line
  ``index_build_skipped_unchanged_corpus``. The two MANIFEST.json files
  must be byte-identical (skip path returns the existing manifest unchanged).
* ``test_manifest_byte_identical_after_skip`` — Stricter cross-check:
  sha256 the MANIFEST.json bytes before + after a second invocation; assert
  equality. Defensive against any future "re-stamp built_at on skip"
  regression that would silently break byte-identity.

Plan 04-05 landed ``docintel-index build`` and Plan 04-07 Task 1 removed the
former xfail markers so these assertions now run as hard tests. Module is
``importorskip``-guarded so collection succeeds even if ``docintel_index``
is uninstalled.

Refs:
- .planning/phases/04-embedding-indexing/04-CONTEXT.md  D-12, D-22
- .planning/phases/04-embedding-indexing/04-RESEARCH.md §Pitfall 9
- tests/test_chunk_idempotency.py — analog pattern
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

# Guard module collection: Plan 04-05 lands docintel_index; until then the
# import would error and prevent the whole file from being collected.
pytest.importorskip("docintel_index")

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _canonicalize_manifest(manifest: dict) -> dict:
    """Strip volatile fields so two runs can be compared structurally.

    ``built_at`` is the only known volatile field on a skip path that the
    contract reserves the right to re-stamp; everything else MUST match.
    The skip path itself (Plan 04-05) returns the existing manifest
    unchanged (so byte-identity holds even with built_at in), but
    canonicalising here makes the test robust to a future contract shift.
    """
    canonical = copy.deepcopy(manifest)
    canonical.pop("built_at", None)
    return canonical


def test_skip_unchanged_corpus(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    """Two back-to-back ``docintel-index build`` invocations: second one skips.

    Asserts:
    1. Both invocations exit 0.
    2. The second invocation's combined stdout+stderr contains the structlog
       line ``index_build_skipped_unchanged_corpus``.
    3. The MANIFEST.json (modulo ``built_at``) is structurally identical
       between the two runs.
    """
    manifest_path = _REPO_ROOT / "data" / "indices" / "MANIFEST.json"

    # First run — build the index.
    first = subprocess.run(
        ["uv", "run", "docintel-index", "build"],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert first.returncode == 0, (
        f"first docintel-index build exited {first.returncode}: stderr={first.stderr!r}"
    )
    assert manifest_path.is_file(), f"MANIFEST.json not written: {manifest_path}"
    first_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Second run — must skip (corpus MANIFEST unchanged).
    second = subprocess.run(
        ["uv", "run", "docintel-index", "build"],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert second.returncode == 0, (
        f"second docintel-index build exited {second.returncode}: stderr={second.stderr!r}"
    )
    second_combined = (second.stdout or "") + (second.stderr or "")
    assert "index_build_skipped_unchanged_corpus" in second_combined, (
        "second invocation did not log the skip event. "
        f"stdout={second.stdout!r} stderr={second.stderr!r}"
    )

    second_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert _canonicalize_manifest(first_manifest) == _canonicalize_manifest(second_manifest), (
        "MANIFEST.json drifted between two unchanged-corpus builds; "
        "skip-path contract violated."
    )


def test_manifest_byte_identical_after_skip() -> None:
    """MANIFEST.json bytes are sha256-identical across a skip-path re-run.

    The skip path (D-12) returns the existing manifest unchanged — this
    test asserts that contract holds at the byte level (no whitespace
    drift, no key reordering, no built_at re-stamp). A regression here
    would silently break the ``docintel-index verify`` round-trip.
    """
    manifest_path = _REPO_ROOT / "data" / "indices" / "MANIFEST.json"

    # First build — ensure a manifest exists.
    first = subprocess.run(
        ["uv", "run", "docintel-index", "build"],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert first.returncode == 0, f"build exited {first.returncode}: stderr={first.stderr!r}"
    assert manifest_path.is_file(), f"MANIFEST.json not written: {manifest_path}"

    before_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    # Second build — skip path.
    second = subprocess.run(
        ["uv", "run", "docintel-index", "build"],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert second.returncode == 0, f"re-build exited {second.returncode}: stderr={second.stderr!r}"

    after_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert before_sha == after_sha, (
        "MANIFEST.json bytes drifted across a skip-path re-run "
        f"(before={before_sha} after={after_sha})"
    )
