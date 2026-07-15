"""Story 3.7 (FR-C8) — FinanceBench: three SEPARATE regimes never merged, the
~19% floor comparison, and an honest dataset-absent gate (no fabricated score).
"""

from __future__ import annotations

from pathlib import Path

from docintel_core.config import Settings
from docintel_eval.financebench import (
    FINANCEBENCH_MODES,
    VECTOR_GPT4T_FLOOR,
    beats_floor,
    render_financebench_markdown,
    run_financebench,
)


def test_three_separate_regimes_never_merged() -> None:
    assert FINANCEBENCH_MODES == ("open-book", "oracle-context", "closed-book")
    # A merged/"all" mode is rejected — one regime per invocation (FR-C8).
    assert run_financebench(Settings(), "all") == 1
    assert run_financebench(Settings(), "everything") == 1


def test_beats_floor_reports_margin_including_below_floor() -> None:
    assert VECTOR_GPT4T_FLOOR == 0.19
    beats, margin = beats_floor(0.42)
    assert beats and margin > 0
    below, neg = beats_floor(0.10)
    assert not below and neg < 0  # below the floor is honestly negative, not hidden


def test_open_book_render_shows_floor_comparison_others_do_not() -> None:
    ob = render_financebench_markdown("open-book", accuracy=0.42, n=150, representative=True)
    assert "floor" in ob and "0.19" in ob and "BEATS" in ob
    # oracle-context / closed-book: no floor comparison (floor is the retrieval regime's)
    oc = render_financebench_markdown("oracle-context", accuracy=0.55, n=150, representative=True)
    assert "floor to beat" not in oc


def test_render_below_floor_is_honest() -> None:
    md = render_financebench_markdown("open-book", accuracy=0.10, n=150, representative=True)
    assert "does NOT beat" in md


def test_dataset_absent_writes_placeholder_not_a_fake_score(tmp_path: Path) -> None:
    # The external dataset is not vendored → placeholder report, no fabricated number.
    out = tmp_path / "fb"
    assert run_financebench(Settings(), "open-book", output_dir=out) == 0
    import json

    payload = json.loads((out / "financebench.json").read_text())
    assert payload["accuracy"] is None and payload["representative"] is False
    md = (out / "financebench.md").read_text()
    assert "NOT PRESENT" in md and "No score is fabricated" in md
