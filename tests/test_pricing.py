"""Tests for docintel_core.pricing — cost table coverage + unknown-model failure.

D-06: cost_for must raise KeyError for unknown (provider, model) rather than
silently returning 0.0. This gate catches model renames that drift from the
pricing table.

Wave 1: xfail markers removed — docintel_core.pricing shipped in Plan 02-02.
"""

from __future__ import annotations

import pytest


def test_cost_calculation() -> None:
    """Anthropic claude-sonnet-4-6: 100 prompt + 50 completion tokens yields exact USD."""
    from docintel_core.pricing import cost_for

    result = cost_for("anthropic", "claude-sonnet-4-6", 100, 50)
    # 100 * 3.00 + 50 * 15.00 = 300 + 750 = 1050 micro-USD → 0.00000105 USD
    expected = (100 * 3.00 + 50 * 15.00) / 1_000_000
    assert abs(result - expected) < 1e-9


def test_unknown_model_raises() -> None:
    """cost_for raises KeyError for an unknown (provider, model) — D-06 loud-fail gate."""
    from docintel_core.pricing import cost_for

    with pytest.raises(KeyError):
        cost_for("anthropic", "claude-unknown-99", 100, 50)


def test_stub_model_costs_zero() -> None:
    """Stub provider/model pair always costs $0.00."""
    from docintel_core.pricing import cost_for

    assert cost_for("stub", "stub", 9999, 9999) == 0.0


def test_nim_models_priced_zero_not_keyerror() -> None:
    """NIM-served models are keyed (D-14) so cost_for returns 0.0 instead of raising.

    build.nvidia.com hosted inference is a free dev-credit tier — the marginal
    $/token is 0. The point of registering them is to clear the D-06 KeyError
    gate (an unregistered generator model would crash the eval mid-run).
    """
    from docintel_core.pricing import cost_for

    assert cost_for("openai", "openai/gpt-oss-120b", 1_000, 500) == 0.0
    assert cost_for("openai", "meta/llama-3.3-70b-instruct", 1_000, 500) == 0.0
