"""Plan 13-01 Wave-0 xfail-strict scaffold for the DECISIONS.md ADR gate (UI-05; D-16).

Locks the "DECISIONS.md exists with >= 8 ADRs" gate BEFORE 13-06 writes it.
Strict-xfail: ``DECISIONS.md`` does not exist yet, so the assertion fails and the
xfail holds. 13-06 ships 8-12 ADRs (``## ADR-NNN`` headings) and removes this
marker; 13-07 confirms none survive.

Node id bound by ``13-VALIDATION.md``: ``test_decisions_md_has_eight_adrs``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_XFAIL_REASON = "Implemented in 13-06 (DECISIONS.md with 8-12 ADRs)"


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


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_decisions_md_has_eight_adrs() -> None:
    """UI-05 / D-16 — repo-root ``DECISIONS.md`` exists with >= 8 ``## ADR-`` headings."""
    decisions = _repo_root() / "DECISIONS.md"
    assert decisions.is_file(), "DECISIONS.md must exist at the repo root (D-16)"
    adr_headings = re.findall(r"(?m)^## ADR-", decisions.read_text(encoding="utf-8"))
    assert len(adr_headings) >= 8, f"expected >= 8 ADR headings, found {len(adr_headings)}"
