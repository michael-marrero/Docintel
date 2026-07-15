"""Story 4.3 (AD-17) — sealed tier is a construction-time posture with ZERO egress.

The factory rejects any egressing adapter under ``tier=sealed``; the ``open`` tier
and stub mode are unaffected. Retrieve/generate/eval code is byte-identical across
tiers — only the bundle differs (AD-2/AD-3), so there is nothing tier-specific to
test on the hot path.
"""

from __future__ import annotations

import pytest
from docintel_core.adapters.factory import (
    SealedTierViolation,
    _is_local_url,
    ensure_sealed_egress_free,
    make_adapters,
)
from docintel_core.config import Settings


def _cfg(**over) -> Settings:
    return Settings(**over)


def test_sealed_stub_is_local_and_allowed() -> None:
    # stub mode is all-local by construction — sealed is a no-op, real adapters build.
    ensure_sealed_egress_free(_cfg(tier="sealed", llm_provider="stub"))
    bundle = make_adapters(_cfg(tier="sealed", llm_provider="stub"))
    assert bundle.llm.name  # constructed fine


def test_open_tier_never_blocks_even_with_hosted_provider() -> None:
    # open tier permits a hosted LLM (only the LLM call egresses) — no guard trip.
    ensure_sealed_egress_free(_cfg(tier="open", llm_provider="real", llm_real_provider="anthropic"))


def test_sealed_rejects_hosted_anthropic() -> None:
    with pytest.raises(SealedTierViolation, match="Anthropic"):
        ensure_sealed_egress_free(
            _cfg(tier="sealed", llm_provider="real", llm_real_provider="anthropic")
        )


def test_sealed_rejects_openai_without_local_base_url() -> None:
    # openai provider pointed at the public api (base_url None) → rejected.
    with pytest.raises(SealedTierViolation, match="OPENAI_BASE_URL"):
        ensure_sealed_egress_free(
            _cfg(tier="sealed", llm_provider="real", llm_real_provider="openai")
        )
    # a public gateway is also rejected.
    with pytest.raises(SealedTierViolation):
        ensure_sealed_egress_free(
            _cfg(
                tier="sealed",
                llm_provider="real",
                llm_real_provider="openai",
                openai_base_url="https://integrate.api.nvidia.com/v1",
            )
        )


def test_sealed_allows_fully_local_real_config() -> None:
    # local OpenAI-compatible endpoint + local qdrant → sealed passes.
    ensure_sealed_egress_free(
        _cfg(
            tier="sealed",
            llm_provider="real",
            llm_real_provider="openai",
            openai_base_url="http://localhost:8000/v1",
            qdrant_url="http://qdrant:6333",
        )
    )


def test_is_local_url_classification() -> None:
    assert _is_local_url("http://localhost:8000/v1")
    assert _is_local_url("http://127.0.0.1:6333")
    assert _is_local_url("http://qdrant:6333")  # bare docker service name
    assert _is_local_url("http://10.0.0.5:8000")  # private IP
    assert _is_local_url("http://nim.internal/v1")
    assert not _is_local_url("https://api.openai.com/v1")
    assert not _is_local_url("https://integrate.api.nvidia.com/v1")
    assert not _is_local_url(None)
