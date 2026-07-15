"""Story 3.8 (FR-C9) — per-tier proof reporting: open + sealed side by side,
sealed never hidden, non-representative tiers flagged, path-confined specs.
"""

from __future__ import annotations

import pytest
from docintel_eval.per_tier import parse_tier_specs, render_per_tier_markdown, tier_row


def _results(provider: str, representative: bool, hit5: float, faith: float) -> dict:
    return {
        "manifest": {"provider": provider, "representative": representative},
        "retrieval": {"hit_at_5": hit5},
        "faithfulness": {"faithfulness_pass_rate": faith, "faithfulness_ci": [0.0, 1.0]},
        "latency": {"p50_ms": 0.0, "p95_ms": 0.0, "cost_per_query_usd": 0.0},
    }


def test_tier_row_pulls_headline_and_degrades_missing_to_none() -> None:
    row = tier_row("open", _results("real", True, 0.556, 0.893))
    assert row["tier"] == "open" and row["provider"] == "real"
    assert row["hit_at_5"] == 0.556 and row["faithfulness"] == 0.893
    # A near-empty results dict still yields a row (missing → None), not a crash.
    sparse = tier_row("sealed", {"manifest": {"provider": "local"}})
    assert sparse["hit_at_5"] is None and sparse["representative"] is None


def test_render_reports_both_tiers_and_never_hides_sealed() -> None:
    rows = [
        tier_row("open", _results("real", True, 0.556, 0.893)),
        tier_row("sealed", _results("local", True, 0.400, 0.700)),  # lower — still shown
    ]
    md = render_per_tier_markdown(rows)
    assert "| open |" in md and "| sealed |" in md  # both present
    assert "0.400" in md and "0.700" in md  # sealed's lower numbers not clipped
    assert "never to open-tier parity" in md  # PRD RISK-2 honesty note


def test_render_flags_non_representative_tiers() -> None:
    rows = [tier_row("sealed", _results("stub", False, 0.0, 0.0))]
    md = render_per_tier_markdown(rows)
    assert "NON-REPRESENTATIVE" in md and "sealed" in md


def test_parse_tier_specs_rejects_bad_shape_and_path_traversal() -> None:
    good = parse_tier_specs(["open:data/eval/reports/stub-sample"])
    assert good[0][0] == "open"
    with pytest.raises(ValueError):
        parse_tier_specs(["no-colon-here"])
    with pytest.raises(ValueError):
        parse_tier_specs(["open:/etc/passwd"])  # outside data/eval/reports/
