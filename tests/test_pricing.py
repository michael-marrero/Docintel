"""Tests for docintel_core.pricing — cost table coverage + unknown-model failure.

D-06: cost_for must raise KeyError for unknown (provider, model) rather than
silently returning 0.0. This gate catches model renames that drift from the
pricing table.

All tests are marked xfail until Wave 1 ships docintel_core.pricing.
"""

from __future__ import annotations

import pytest

_XFAIL = pytest.mark.xfail(
    raises=(ImportError, AttributeError, NotImplementedError, AssertionError),
    strict=False,
    reason="awaits Wave 1 — docintel_core.pricing not yet created (see 02-VALIDATION.md)",
)


@_XFAIL
def test_cost_calculation() -> None:
    """Anthropic claude-sonnet-4-6: 100 prompt + 50 completion tokens yields exact USD."""
    from docintel_core.pricing import cost_for

    result = cost_for("anthropic", "claude-sonnet-4-6", 100, 50)
    # 100 * 3.00 + 50 * 15.00 = 300 + 750 = 1050 micro-USD → 0.00000105 USD
    expected = (100 * 3.00 + 50 * 15.00) / 1_000_000
    assert abs(result - expected) < 1e-9


@_XFAIL
def test_unknown_model_raises() -> None:
    """cost_for raises KeyError for an unknown (provider, model) — D-06 loud-fail gate."""
    from docintel_core.pricing import cost_for

    with pytest.raises(KeyError):
        cost_for("anthropic", "claude-unknown-99", 100, 50)


@_XFAIL
def test_stub_model_costs_zero() -> None:
    """Stub provider/model pair always costs $0.00."""
    from docintel_core.pricing import cost_for

    assert cost_for("stub", "stub", 9999, 9999) == 0.0
