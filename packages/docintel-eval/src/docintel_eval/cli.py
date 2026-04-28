"""Eval CLI scaffold for docintel.

Phase 1 deliberately ships a placeholder that exits 1 with a clear message --
the Makefile target `make eval` (CONTEXT.md D-22) wraps this command and is
expected to fail in Phase 1. The real CLI lands in Phases 9-11.

This module MUST NOT read env vars directly. When the real implementation
arrives it will read configuration via docintel_core.config.Settings.
"""

from __future__ import annotations

import sys

from docintel_core import __version__

_NOT_IMPLEMENTED_MESSAGE = (
    f"docintel-eval v{__version__} -- eval CLI is not yet implemented.\n"
    "Lands in Phase 9 (metrics) / Phase 10 (CI integration) / Phase 11 (ablation).\n"
    "See .planning/REQUIREMENTS.md (EV2-*, EV3-*, EV4-*) and .planning/ROADMAP.md."
)


def main() -> int:
    """Entry point referenced by packages/docintel-eval/pyproject.toml.

    Returns 1 unconditionally in Phase 1. The Makefile relies on this exit code.
    """
    print(_NOT_IMPLEMENTED_MESSAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
