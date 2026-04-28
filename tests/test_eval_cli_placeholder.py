"""Tests for the Phase 1 placeholder ``docintel-eval`` CLI.

The real eval harness lands in Phase 9 (metrics) / 10 (CI integration) /
11 (ablation). Phase 1 ships only a stub that exits 1 with a clear message,
because the Makefile's ``make eval`` target wraps this command (CONTEXT.md
D-22) and is expected to fail visibly until those phases land.

This test pins both behaviours so a future contributor can't accidentally
ship a no-op ``return 0`` and silently make ``make eval`` look green.
"""

from __future__ import annotations

import subprocess
import sys


def test_eval_cli_exits_nonzero_with_pointer_message() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "docintel_eval.cli"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, (
        f"expected exit code 1 from placeholder CLI, got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    # The message must point future readers at the real implementation phases.
    assert (
        "Phase 9" in result.stderr
        or "Phase 9-10" in result.stderr
        or (
            "lands in Phase 9" in result.stderr.lower()
            or "lands in phase 9" in result.stderr.lower()
        )
    ), f"placeholder message missing Phase 9/10 pointer; stderr={result.stderr!r}"
