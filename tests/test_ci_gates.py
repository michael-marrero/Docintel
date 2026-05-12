"""Structural tests for the adapter-wrap grep gate (ADP-06, D-18).

The grep gate asserts that every real adapter file containing an SDK call
also imports tenacity. This test suite exercises the gate with a negative
fixture (unwrapped call — must fail) and a positive fixture (wrapped — pass).

Wave 4: xfail markers removed; scripts/check_adapter_wraps.sh and the five
real adapter files exist. Both tests are now expected to pass (green).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GATE_SCRIPT = _REPO_ROOT / "scripts" / "check_adapter_wraps.sh"
_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
_UNWRAPPED_FIXTURE = _FIXTURE_DIR / "unwrapped_sdk_call.py.example"


def test_grep_gate_catches_unwrapped() -> None:
    """Grep gate exits non-zero when scanning a file with an unwrapped SDK call.

    Invokes the gate script with the fixtures directory as the scan target.
    The unwrapped_sdk_call.py.example contains client.messages.create() but
    no tenacity import — the gate must catch this and exit non-zero.
    """
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT), str(_UNWRAPPED_FIXTURE.parent)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "grep gate did not catch the unwrapped SDK call fixture. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_grep_gate_passes_wrapped(tmp_path) -> None:
    """Grep gate exits zero when every SDK-calling file also imports tenacity.

    Creates a temporary directory with a single dummy.py that has BOTH a
    client.messages.create() call AND a 'from tenacity import retry' line.
    The gate must accept this and exit zero.
    """
    dummy = tmp_path / "dummy.py"
    dummy.write_text(
        'from tenacity import retry\n\nclient.messages.create(model="claude-sonnet-4-6", max_tokens=1, messages=[])\n',
        encoding="utf-8",
    )
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT), str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "grep gate rejected a properly-wrapped adapter file. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
