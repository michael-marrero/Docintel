"""Structural test that gitleaks is installed and catches obvious leaks.

The CI pipeline will run gitleaks across the full repo on every push; this
test guards that the binary exists locally and is wired into the dev loop.
A developer running ``pytest`` should learn immediately if their machine
cannot run the same scan that CI runs.

The fixture under ``tests/fixtures/leaked_key.example`` contains a sentinel
``sk-...`` style key. We expect gitleaks (run with the repo's
``.gitleaks.toml`` config) to flag it and exit non-zero.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent
_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "leaked_key.example"
_GITLEAKS_CONFIG = _REPO_ROOT / ".gitleaks.toml"
# The fixture ships an OpenAI-style sentinel key. We assert the *prefix*
# rather than the full string so a future fixture refresh (e.g. swapping
# in a different sentinel) doesn't silently break this test — it'll fail
# loudly and a contributor will know to update both ends together.
_FAKE_KEY_PREFIX = "sk-"


def test_gitleaks_flags_fixture() -> None:
    if shutil.which("gitleaks") is None:
        pytest.skip("gitleaks binary not installed; CI runs the real scan")

    assert _FIXTURE.is_file(), f"missing leak fixture: {_FIXTURE}"

    cmd = [
        "gitleaks",
        "detect",
        "--no-git",
        "--source",
        str(_FIXTURE.parent),
        "--report-format",
        "json",
        "--report-path",
        "/dev/stdout",
        "--verbose",
    ]
    if _GITLEAKS_CONFIG.is_file():
        cmd.extend(["--config", str(_GITLEAKS_CONFIG)])

    result = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )

    # gitleaks exits non-zero when leaks are found — that's exactly what we
    # want here, since the fixture is a deliberate plant.
    assert result.returncode != 0, (
        "gitleaks did not flag the planted fake key. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    combined = result.stdout + result.stderr
    assert _FAKE_KEY_PREFIX in combined, (
        f"gitleaks ran but did not surface a key matching prefix {_FAKE_KEY_PREFIX!r}. "
        f"Output:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
