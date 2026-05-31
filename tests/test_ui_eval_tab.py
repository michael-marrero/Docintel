"""Eval-Results tab auto-detect contract tests (UI-04; D-12/13).

De-xfailed from Plan 13-01 (Wave-0 xfail-strict scaffold) once Plan 13-04
shipped ``docintel_ui.eval_view._find_eval_report`` +
``representative_banner``. The bodies are unchanged from the scaffold — they
now run green against the pure helpers.

Node ids bound by ``13-VALIDATION.md``: ``test_eval_tab_detects_stub_sample``,
``test_eval_tab_stub_banner``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

# Committed stub-sample results.json — its manifest.representative is False.
_STUB_RESULTS = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "eval"
    / "reports"
    / "stub-sample"
    / "results.json"
)


def _make_stub_data_dir(tmp_path: Path) -> Path:
    """Build a tmp ``data_dir`` holding only ``eval/reports/stub-sample/results.json``."""
    dest = tmp_path / "data" / "eval" / "reports" / "stub-sample"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(_STUB_RESULTS, dest / "results.json")
    return tmp_path / "data"


def test_eval_tab_detects_stub_sample(tmp_path: Path) -> None:
    """D-13 — with no real-mode report present, auto-detect falls back to stub-sample (is_representative False)."""
    from docintel_ui.eval_view import _find_eval_report

    data_dir = _make_stub_data_dir(tmp_path)
    report_path, is_representative = _find_eval_report(str(data_dir))
    assert report_path is not None, "auto-detect must find the committed stub-sample report"
    assert "stub-sample" in str(report_path)
    assert is_representative is False


def test_eval_tab_stub_banner(tmp_path: Path) -> None:
    """D-13 — stub mode (is_representative False) surfaces a 'representative: false' banner."""
    from docintel_ui.eval_view import _find_eval_report, representative_banner

    data_dir = _make_stub_data_dir(tmp_path)
    _, is_representative = _find_eval_report(str(data_dir))
    banner = representative_banner(is_representative)
    assert banner is not None, "a non-representative (stub) report must surface a banner"
    assert "representative" in banner.lower()
