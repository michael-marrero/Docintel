"""Hard-coded LLM pricing table for docintel.

Keys: (provider, model_id) -> (prompt_$/1M_tokens, completion_$/1M_tokens)
Values are USD per 1 million tokens. Versioned in git so eval reports are
reproducible by git SHA.

D-06: cost_for() uses direct dict subscription PRICING[(provider, model)],
which raises KeyError on any unknown (provider, model) pair. This is
intentional — silent zero is explicitly forbidden. The CI test
test_unknown_model_raises enforces this gate on every PR.

Prices verified 2026-05-12 against:
- Anthropic: platform.claude.com/docs/en/about-claude/pricing
- OpenAI: pricepertoken.com (gpt-4o, gpt-4.1)
"""

from __future__ import annotations

PRICING: dict[tuple[str, str], tuple[float, float]] = {
    # Anthropic — verified 2026-05-12
    ("anthropic", "claude-sonnet-4-6"): (3.00, 15.00),
    ("anthropic", "claude-sonnet-4-5"): (3.00, 15.00),
    ("anthropic", "claude-haiku-4-5"): (1.00, 5.00),
    # OpenAI — verified 2026-05-12
    ("openai", "gpt-4o"): (2.50, 10.00),
    ("openai", "gpt-4.1"): (2.00, 8.00),
    # Stub — zero cost, deterministic
    ("stub", "stub"): (0.00, 0.00),
}


def cost_for(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Compute USD cost for a single API call.

    Raises KeyError if (provider, model) is not in PRICING — this is
    intentional. A CI test asserts every adapter's model ID is keyed here;
    model renames that drift from the pricing table fail loudly rather than
    silently returning 0.0 (D-06, T-02-04).

    Args:
        provider:          Provider string, e.g. "anthropic", "openai", "stub".
        model:             Model ID string, e.g. "claude-sonnet-4-6", "gpt-4o".
        prompt_tokens:     Number of input/prompt tokens consumed.
        completion_tokens: Number of output/completion tokens generated.

    Returns:
        Cost in USD as a float.

    Raises:
        KeyError: If (provider, model) is not in PRICING.
    """
    prompt_rate, compl_rate = PRICING[(provider, model)]
    return (prompt_tokens * prompt_rate + completion_tokens * compl_rate) / 1_000_000
