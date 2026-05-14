"""Tests for the ``docintel-index verify`` CLI (D-14).

Covers Phase 4's verify contract:

* ``test_verify_clean_build`` — A fresh ``docintel-index build`` followed
  by ``docintel-index verify`` exits 0 on the clean artifacts.
* ``test_verify_detects_tampered_npy`` — Appending a single byte to
  ``data/indices/dense/embeddings.npy`` corrupts its sha256; verify must
  detect the drift and exit 1. Critical hygiene: the test snapshots the
  original bytes BEFORE tampering and restores them in a ``try/finally``
  so a failed assertion does not leave the repo in a corrupted state.

Both tests are ``@pytest.mark.xfail(strict=False)`` until Plan 04-05 lands
``docintel-index verify`` (D-14) and Plan 04-07 flips them green. Module is
``importorskip``-guarded so collection succeeds before ``docintel_index``
ships.

Refs:
- .planning/phases/04-embedding-indexing/04-CONTEXT.md  D-14
- .planning/phases/04-embedding-indexing/04-RESEARCH.md §Pitfall 8 (atomic-write hygiene)
- packages/docintel-ingest/src/docintel_ingest/verify.py — analog (Phase 3)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Guard module collection: Plan 04-05 lands docintel_index; until then the
# import would error and prevent the whole file from being collected.
pytest.importorskip("docintel_index")

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.xfail(
    strict=False,
    reason="Plan 04-05 lands docintel-index build + verify (D-14); Plan 04-07 flips this green.",
)
def test_verify_clean_build() -> None:
    """``docintel-index verify`` exits 0 immediately after a clean build."""
    build = subprocess.run(
        ["uv", "run", "docintel-index", "build"],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert build.returncode == 0, (
        f"docintel-index build exited {build.returncode}: stderr={build.stderr!r}"
    )

    verify = subprocess.run(
        ["uv", "run", "docintel-index", "verify"],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert verify.returncode == 0, (
        f"docintel-index verify exited {verify.returncode} on a clean build: "
        f"stdout={verify.stdout!r} stderr={verify.stderr!r}"
    )


@pytest.mark.xfail(
    strict=False,
    reason="Plan 04-05 lands the tampered-artifact detection path (D-14); Plan 04-07 flips this green.",
)
def test_verify_detects_tampered_npy() -> None:
    """``docintel-index verify`` exits 1 when ``embeddings.npy`` is byte-corrupted.

    Snapshots the original bytes BEFORE tampering; restores them in a
    ``try/finally`` to keep the repo clean even if the assertion fails.
    """
    build = subprocess.run(
        ["uv", "run", "docintel-index", "build"],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert build.returncode == 0, (
        f"docintel-index build exited {build.returncode}: stderr={build.stderr!r}"
    )

    embeddings_path = _REPO_ROOT / "data" / "indices" / "dense" / "embeddings.npy"
    assert embeddings_path.is_file(), (
        f"embeddings.npy missing after build: {embeddings_path}"
    )

    original_bytes = embeddings_path.read_bytes()
    try:
        # Tamper: append a single byte. Corrupts the sha256 recorded in
        # MANIFEST.json without disturbing the on-disk shape that verify
        # uses to locate the file.
        with embeddings_path.open("ab") as fh:
            fh.write(b"\x00")

        verify = subprocess.run(
            ["uv", "run", "docintel-index", "verify"],
            check=False,
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
        )
        assert verify.returncode == 1, (
            "docintel-index verify did NOT detect tampered embeddings.npy "
            f"(returncode={verify.returncode}, expected 1). "
            f"stdout={verify.stdout!r} stderr={verify.stderr!r}"
        )
    finally:
        # Always restore the original bytes — never leave the repo dirty
        # even on assertion failure.
        embeddings_path.write_bytes(original_bytes)
