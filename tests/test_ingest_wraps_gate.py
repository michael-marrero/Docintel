"""Structural tests for the ingest-wrap grep gate (D-18 — ADP-06 analog).

The grep gate asserts that every file under ``packages/docintel-ingest/src``
containing a ``sec_edgar_downloader`` SDK call (``Downloader(`` or
``dl.get(``) also imports ``tenacity``. This test suite exercises the
gate with a negative fixture (unwrapped call — must fail) and a
positive fixture (wrapped — pass), mirroring ``tests/test_ci_gates.py``
from Phase 2.

Tests xfail until Plan 03-02 ships ``scripts/check_ingest_wraps.sh``.
The wave-flip commit removes these xfail markers.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GATE_SCRIPT = _REPO_ROOT / "scripts" / "check_ingest_wraps.sh"
_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
_UNWRAPPED_FIXTURE = _FIXTURE_DIR / "unwrapped_edgar_call.py.example"

_XFAIL = pytest.mark.xfail(
    raises=(FileNotFoundError, AssertionError, NotImplementedError),
    strict=False,
    reason="awaits Plan 03-02 — scripts/check_ingest_wraps.sh (D-18 analog)",
)


@_XFAIL
def test_grep_gate_catches_unwrapped() -> None:
    """Grep gate exits non-zero when scanning a file with an unwrapped SDK call.

    Invokes the gate script with the fixtures directory as the scan target.
    ``unwrapped_edgar_call.py.example`` contains ``Downloader(...)`` and
    ``dl.get(...)`` with NO ``from tenacity import`` — the gate must catch
    this and exit non-zero.
    """
    # Gate script must exist for this test to be meaningful — otherwise
    # ``bash <missing>`` returns 127 and the test would pass for the wrong
    # reason. Until Plan 03-02 ships the script, this assertion fires the
    # xfail.
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT), str(_UNWRAPPED_FIXTURE.parent)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "ingest grep gate did not catch the unwrapped sec-edgar-downloader fixture. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


@_XFAIL
def test_grep_gate_passes_wrapped(tmp_path) -> None:
    """Grep gate exits zero when every sec-edgar-downloader call sits next to a tenacity import.

    Writes a single dummy.py with BOTH ``from tenacity import retry`` AND a
    ``Downloader(...)`` plus ``dl.get(...)`` call. The gate must accept this
    and exit zero.
    """
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    dummy = tmp_path / "dummy.py"
    dummy.write_text(
        "from tenacity import retry\nfrom sec_edgar_downloader import Downloader\n\n"
        'dl = Downloader("test", "test@example.com")\ndl.get("10-K", "AAPL")\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT), str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "ingest grep gate rejected a properly-wrapped sec-edgar-downloader file. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
