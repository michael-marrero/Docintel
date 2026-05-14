"""Tests for the ``docintel-ingest`` CLI subcommand wiring.

Covers VALIDATION.md task (Wave 0 list — CLI subcommands) and Pitfall 9:

* ``--help`` lists every subcommand (``fetch``, ``normalize``, ``chunk``,
  ``all``, ``verify``).
* ``--help`` cold start is under 5 s (uv adds its own startup cost; the
  structural property under test is "no torch import at module top",
  not absolute latency).
* ``--version`` exits 0 and prints a semver-ish string.
* ``PYTHONVERBOSE=1 docintel-ingest --help`` does not mention ``torch``
  or ``transformers`` on stderr (Pitfall 9 — the lazy-import gate).

The tests xfail until Wave 1 lands ``docintel-ingest`` as a workspace
package with a real CLI entry point. The wave-flip commit removes the
xfail markers.
"""

from __future__ import annotations

import os
import re
import subprocess
import time

import pytest

_XFAIL = pytest.mark.xfail(
    raises=(
        ImportError,
        AttributeError,
        AssertionError,
        NotImplementedError,
        FileNotFoundError,
        subprocess.CalledProcessError,
    ),
    strict=False,
    reason="awaits Wave 1 — docintel_ingest.cli + project-script entry",
)


@_XFAIL
def test_help_lists_subcommands() -> None:
    """``docintel-ingest --help`` lists every Wave 0 subcommand."""
    result = subprocess.run(
        ["uv", "run", "docintel-ingest", "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"--help exited {result.returncode}: {result.stderr!r}"
    for sub in ("fetch", "normalize", "chunk", "all", "verify"):
        assert sub in result.stdout, f"subcommand {sub!r} missing from --help"


@_XFAIL
def test_help_latency_under_5s() -> None:
    """``--help`` cold start < 5 s (Pitfall 9 — no torch import at module top)."""
    t0 = time.perf_counter()
    result = subprocess.run(
        ["uv", "run", "docintel-ingest", "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    elapsed = time.perf_counter() - t0
    assert result.returncode == 0
    assert (
        elapsed < 5.0
    ), f"--help took {elapsed:.2f}s — possible torch import at module top (Pitfall 9)"


@_XFAIL
def test_version_flag() -> None:
    """``--version`` exits 0 with a semver-ish string."""
    result = subprocess.run(
        ["uv", "run", "docintel-ingest", "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, f"--version exited {result.returncode}: {result.stderr!r}"
    assert re.search(
        r"\d+\.\d+\.\d+", result.stdout
    ), f"--version output lacks semver: {result.stdout!r}"


@_XFAIL
def test_no_torch_import_on_help() -> None:
    """``PYTHONVERBOSE=1 docintel-ingest --help`` does not pull in torch or transformers (Pitfall 9)."""
    env = {**os.environ, "PYTHONVERBOSE": "1"}
    result = subprocess.run(
        ["uv", "run", "docintel-ingest", "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )
    # CLI must exist for this test to be meaningful — exit 0 + populated --help.
    # Until Wave 1 lands ``docintel-ingest``, ``uv run`` returns a "command not
    # found" failure and the xfail catches the AssertionError below.
    assert (
        result.returncode == 0
    ), f"docintel-ingest --help exited {result.returncode}: stderr={result.stderr!r}"
    for sub in ("fetch", "normalize", "chunk"):
        assert sub in result.stdout, f"subcommand {sub!r} missing — CLI not fully wired"
    assert (
        "transformers" not in result.stderr
    ), "PYTHONVERBOSE traced a transformers import on --help — Pitfall 9 regression"
    assert (
        "torch" not in result.stderr
    ), "PYTHONVERBOSE traced a torch import on --help — Pitfall 9 regression"
