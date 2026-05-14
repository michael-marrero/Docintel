"""Structural tests for the index-wrap grep gate (D-21 — ADP-06 analog for Phase 4).

The grep gate asserts that every file under
``packages/docintel-core/src/docintel_core/adapters/real/`` containing a
``qdrant_client`` SDK call (``QdrantClient(``, ``.upsert(``, ``.upload_points(``,
``.query_points(``, ``.get_collection(``, ``.create_collection(``,
``.delete_collection(``) also imports ``tenacity``. This test suite exercises
the gate with a negative fixture (un-wrapped call — must fail) and a positive
fixture (wrapped — pass), mirroring ``tests/test_ingest_wraps_gate.py`` from
Phase 3.

Plan 04-02 shipped ``scripts/check_index_wraps.sh`` (vacuous pass today —
no qdrant_client.* files exist yet under adapters/real/); Plan 04-01 shipped
``tests/fixtures/missing_tenacity/qdrant_fake.py`` (the negative-case
fixture). Both are wave-1 parallel, so the assertions below are
``@pytest.mark.xfail(strict=False)`` until Plan 04-07 flips them green.

Refs:
- .planning/phases/04-embedding-indexing/04-CONTEXT.md  D-21
- .planning/phases/04-embedding-indexing/04-RESEARCH.md §Pattern 6, §Pitfall 6
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GATE_SCRIPT = _REPO_ROOT / "scripts" / "check_index_wraps.sh"
_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "missing_tenacity"


@pytest.mark.xfail(
    strict=False,
    reason="Plan 04-02 lands the gate; Plan 04-01 lands the missing-tenacity fixture (wave-1 parallel). Plan 04-07 flips this green.",
)
def test_grep_gate_catches_unwrapped() -> None:
    """Grep gate exits non-zero when scanning a directory with an un-wrapped Qdrant call.

    Invokes the gate script with the ``tests/fixtures/missing_tenacity``
    directory as the scan target. Plan 04-01's ``qdrant_fake.py`` fixture
    contains ``from qdrant_client import QdrantClient`` + a
    ``client.upsert(...)`` call with NO ``from tenacity import`` — the gate
    must catch this and exit non-zero.
    """
    # Gate script must exist for this test to be meaningful — otherwise
    # ``bash <missing>`` returns 127 and the test would pass for the wrong
    # reason.
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT), str(_FIXTURE_DIR)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "index grep gate did not catch the unwrapped qdrant_client fixture. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


@pytest.mark.xfail(
    strict=False,
    reason="Plan 04-02 lands the gate. Self-contained positive-case test should pass once the gate is wired; xfail-strict-false until Plan 04-07 final flip.",
)
def test_grep_gate_passes_wrapped(tmp_path: Path) -> None:
    """Grep gate exits zero when every qdrant_client call sits next to a tenacity import.

    Writes a single dummy.py with BOTH ``from tenacity import retry`` AND a
    ``from qdrant_client import QdrantClient`` plus a ``client.upsert(...)``
    call. The gate must accept this and exit zero.
    """
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    dummy = tmp_path / "dummy.py"
    dummy.write_text(
        "from tenacity import retry\n"
        "from qdrant_client import QdrantClient\n\n"
        "client = QdrantClient(url='http://x')\n"
        "client.upsert(collection_name='c', points=[])\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT), str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "index grep gate rejected a properly-wrapped qdrant_client file. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
