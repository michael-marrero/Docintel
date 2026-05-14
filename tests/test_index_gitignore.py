"""Wave 0 scaffold — IDX-04 ``data/indices/`` gitignored gate.

Covers VALIDATION.md Per-Task Verification Map row for IDX-04 (no index
artifacts ever land in git; ``data/indices/`` and any nested cache directory
like ``data/indices/.qdrant/`` are covered by the existing ``.gitignore`` rule
shipped in Plan 03-04).

Plan 04-05 builds the running ``data/indices/`` directory; Plan 04-07 Task 1
removed the former xfail marker so the IDX-04 gate now runs as a hard test.

Analog: documented gate per IDX-04 — no direct test analog in Phase 3.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_indices_dir_ignored() -> None:
    """IDX-04: ``data/indices/`` (and any nested cache dir) is gitignored.

    Two checks:

    1. Source check — ``.gitignore`` contains a ``data/indices/`` line so
       ``git status`` never lists index artifacts as untracked.
    2. Behavioral check — ``git check-ignore`` confirms a synthetic path
       under ``data/indices/.qdrant/storage`` is covered by the umbrella rule
       (NOT just the bare directory).
    """
    gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/indices/" in gitignore, (
        f".gitignore must list 'data/indices/' as a top-level rule — IDX-04. "
        f"current entries: {[ln for ln in gitignore if 'indices' in ln]!r}"
    )

    # Behavioral check — synthesise a nested path that does not have to exist
    # on disk; ``git check-ignore --no-index`` will evaluate the path against
    # the .gitignore rules without requiring the file to be present.
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-v", "data/indices/.qdrant/storage/segment-0"],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0, (
        "git check-ignore must report data/indices/.qdrant/storage/segment-0 as ignored — "
        f"IDX-04 umbrella rule broken. stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "data/indices/" in result.stdout, (
        f"check-ignore matched a different rule than expected: stdout={result.stdout!r}"
    )
