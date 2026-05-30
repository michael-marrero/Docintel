"""Docs gate for the repo-root ``DECISIONS.md`` ADR count (UI-05 / D-16).

De-xfailed in Plan 13-06 once ``DECISIONS.md`` was authored with 10 ADRs.
The xfail-strict marker was removed in-wave per project convention (a passing
strict-xfail is an XPASS that fails the suite).

Node id bound by ``13-VALIDATION.md``: ``test_decisions_md_has_eight_adrs``.
"""

from __future__ import annotations

import re
from pathlib import Path


def _repo_root() -> Path:
    """Walk up from this file to the dir containing ``pyproject.toml`` / ``.git``.

    Robust to cwd / ``monkeypatch.chdir`` — this gate reads a repo-root file, not
    a cwd-relative one, so it must not depend on the working directory.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() or (parent / ".git").exists():
            return parent
    return here.parents[1]


def test_decisions_md_has_eight_adrs() -> None:
    """UI-05 / D-16 — repo-root ``DECISIONS.md`` exists with >= 8 ``## ADR-`` headings."""
    decisions = _repo_root() / "DECISIONS.md"
    assert decisions.is_file(), "DECISIONS.md must exist at the repo root (D-16)"
    adr_headings = re.findall(r"(?m)^## ADR-", decisions.read_text(encoding="utf-8"))
    assert len(adr_headings) >= 8, f"expected >= 8 ADR headings, found {len(adr_headings)}"
