"""Story 3.6 (FR-C5) — confidence calibration: Brier, ECE, reliability curve.

Pure-math tests over the metrics primitives (no LLM, no I/O) plus the
CalibrationResult contract. The runner (calibration.run_calibration) is exercised
by the CLI smoke in CI; here we lock the math and the representativeness label.
"""

from __future__ import annotations

import math

import pytest
from docintel_eval.metrics import (
    CONFIDENCE_PROB,
    brier_score,
    compute_calibration,
    expected_calibration_error,
    reliability_bins,
)


def test_brier_perfect_and_worst() -> None:
    # Perfect predictions (p == y) → Brier 0.0
    assert brier_score([1.0, 0.0, 1.0], [True, False, True]) == 0.0
    # Worst predictions (p opposite of y) → Brier 1.0
    assert brier_score([0.0, 1.0], [True, False]) == 1.0
    # A 0.5 hedge on any outcome → 0.25
    assert brier_score([0.5, 0.5], [True, False]) == pytest.approx(0.25)


def test_brier_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        brier_score([0.5], [True, False])
    with pytest.raises(ValueError):
        brier_score([], [])


def test_ece_perfectly_calibrated_is_zero() -> None:
    # Within a bin, accuracy == mean confidence → ECE 0. Put 0.9-confidence preds
    # where exactly 90% are correct (9 of 10) — same bin, acc==conf.
    probs = [0.9] * 10
    outcomes = [True] * 9 + [False]
    assert expected_calibration_error(probs, outcomes, n_bins=10) == pytest.approx(0.0, abs=1e-9)


def test_ece_overconfident_is_large() -> None:
    # All predictions 0.9 confidence but only 10% correct → ECE ≈ 0.8.
    probs = [0.9] * 10
    outcomes = [True] + [False] * 9
    ece = expected_calibration_error(probs, outcomes, n_bins=10)
    assert ece == pytest.approx(0.8, abs=1e-9)


def test_reliability_bins_omit_empty_and_carry_counts() -> None:
    probs = [0.3, 0.3, 0.9]
    outcomes = [False, True, True]
    bins = reliability_bins(probs, outcomes, n_bins=10)
    # Two non-empty bins: the 0.3 bin (count 2) and the 0.9 bin (count 1).
    assert {b["count"] for b in bins} == {2, 1}
    lo3 = next(b for b in bins if b["count"] == 2)
    assert lo3["mean_confidence"] == pytest.approx(0.3)
    assert lo3["accuracy"] == pytest.approx(0.5)  # 1 of 2 correct


def test_compute_calibration_maps_categories_and_labels_representative() -> None:
    # high→0.9, medium→0.6, low→0.3 per the declared prior.
    res = compute_calibration(["high", "medium", "low"], [True, True, False], representative=True)
    assert res.n == 3
    assert res.representative is True
    assert res.confidence_prob_map == CONFIDENCE_PROB
    # Brier = mean((0.9-1)^2, (0.6-1)^2, (0.3-0)^2) = mean(0.01,0.16,0.09)
    assert res.brier == pytest.approx((0.01 + 0.16 + 0.09) / 3)
    assert 0.0 <= res.ece <= 1.0 and math.isfinite(res.ece)


def test_compute_calibration_empty_is_safe_and_nonrepresentative() -> None:
    res = compute_calibration([], [], representative=False)
    assert res.n == 0 and res.brier == 0.0 and res.ece == 0.0
    assert res.reliability == [] and res.representative is False
