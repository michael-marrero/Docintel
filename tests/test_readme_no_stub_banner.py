"""Wave-0 xfail-strict scaffold — EMP-02 / D-10 README real-numbers paste assertion.

Plan 14-01 Wave 0 (Phase 14 empirical-closure) lands this red test BEFORE
Plan 14-06 performs the mechanical D-10 PASTE-REAL-NUMBERS swap. Today the
README block at ``README.md:42-77`` carries ``representative: false`` (the
stub-mode placeholder); after 14-06 swaps in real numbers from the
baseline-referenced report it must carry ``representative: true`` and the
``representative: false`` banner must be gone.

D-10 anchor block convention: the HTML comments
``<!-- PASTE-REAL-NUMBERS: ... -->`` and ``<!-- END-PASTE-REAL-NUMBERS -->``
delimit the swap region. The test scopes its assertion to that slice so a
``representative: false`` mention elsewhere in the README (e.g., in the
"Eval methodology" paragraph at line 117) does NOT trip the gate. Per
14-RESEARCH Pitfall 4, ``re.search(..., re.DOTALL)`` is the robust
multi-line slice; a sed-based swap would be fragile.

Lifecycle: xfail-strict in Wave 0 (Plan 14-01) until Plan 14-06 lands the
mechanical paste. An XPASS would then fail the suite, so 14-06 also removes
the xfail marker in the same plan.

Analogs:
* ``tests/test_docs_gates.py:16-35`` — ``_repo_root()`` walk-up helper +
  read tracked markdown file + ``re.findall`` + count assertion (the
  exact role-match: scan a tracked markdown file at repo root for a
  forbidden/required substring).
* 14-PATTERNS.md §"NEW tests/test_readme_no_stub_banner.py" (slice via
  ``re.search(..., re.DOTALL)`` + 2-assertion shape).
"""

from __future__ import annotations

import re
from pathlib import Path


def _repo_root() -> Path:
    """Walk up from this file to the dir containing ``pyproject.toml`` / ``.git``.

    Verbatim from ``tests/test_docs_gates.py:16-26`` — robust to cwd /
    ``monkeypatch.chdir`` since this gate reads a repo-root file, not a
    cwd-relative one.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() or (parent / ".git").exists():
            return parent
    return here.parents[1]


def test_readme_paste_block_has_no_stub_banner() -> None:
    """EMP-02 / D-10: PASTE-REAL-NUMBERS block has no ``representative: false`` and gains ``representative: true``.

    Slices the block delimited by ``<!-- PASTE-REAL-NUMBERS: ... -->`` and
    ``<!-- END-PASTE-REAL-NUMBERS -->`` via ``re.search(..., re.DOTALL)``
    and asserts exactly two things:

      (a) ``"representative: false"`` is NOT in the block (stub banner is gone).
      (b) ``"representative: true"`` IS in the block (real numbers landed).
    """
    readme = _repo_root() / "README.md"
    assert readme.is_file(), f"EMP-02: README.md must exist at {readme}"
    text = readme.read_text(encoding="utf-8")

    match = re.search(
        r"<!-- PASTE-REAL-NUMBERS:.*?<!-- END-PASTE-REAL-NUMBERS -->",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, (
        "EMP-02 / D-10: PASTE-REAL-NUMBERS anchor block not found in README. "
        "Expected the `<!-- PASTE-REAL-NUMBERS: ... -->` ... "
        "`<!-- END-PASTE-REAL-NUMBERS -->` markers at README.md:42-77."
    )
    block = match.group(0)

    assert "representative: false" not in block, (
        "EMP-02 / D-10: README PASTE-REAL-NUMBERS block still contains "
        "`representative: false` — Plan 14-06 paste did not land or is incomplete."
    )
    assert "representative: true" in block, (
        "EMP-02 / D-10: README PASTE-REAL-NUMBERS block missing "
        "`representative: true` — Plan 14-06 must paste real-eval numbers "
        "from the baseline-referenced report."
    )
