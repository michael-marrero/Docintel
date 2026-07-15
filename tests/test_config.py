"""Tests for ``docintel_core.config.Settings``.

Locks the three Phase 1 invariants:

* ``llm_provider`` defaults to ``"stub"`` (offline-first guarantee, FND-08).
* ``DOCINTEL_LLM_PROVIDER=real`` flips it to ``"real"`` (env-driven, D-18).
* ``api_url`` defaults to ``http://api:8000`` so the UI can find the API
  inside docker-compose without explicit configuration.
"""

from __future__ import annotations

import pytest
from docintel_core.config import Settings


def test_default_provider_is_stub(clean_docintel_env) -> None:
    """With no env vars set, the provider must be the offline stub."""
    assert Settings().llm_provider == "stub"


def test_provider_overridable_via_env(clean_docintel_env, monkeypatch: pytest.MonkeyPatch) -> None:
    """The DOCINTEL_ prefix lets operators flip to the real provider."""
    monkeypatch.setenv("DOCINTEL_LLM_PROVIDER", "real")
    assert Settings().llm_provider == "real"


def test_api_url_default(clean_docintel_env) -> None:
    """Default API URL targets the docker-compose ``api`` service."""
    assert Settings().api_url == "http://api:8000"


def test_real_provider_default_is_anthropic(clean_docintel_env) -> None:
    """Default real-mode provider is Anthropic (D-09, CD-07)."""
    assert Settings().llm_real_provider == "anthropic"


def test_real_provider_overridable_via_env(
    clean_docintel_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The DOCINTEL_LLM_REAL_PROVIDER env var flips the real provider to OpenAI."""
    monkeypatch.setenv("DOCINTEL_LLM_REAL_PROVIDER", "openai")
    assert Settings().llm_real_provider == "openai"


# ---------------------------------------------------------------------------
# D-14 / ADR-014: OpenAI-compatible endpoint override (NIM) + distinct judge model
# ---------------------------------------------------------------------------


def test_openai_endpoint_overrides_default_to_safe_values(clean_docintel_env) -> None:
    """Without env, the NIM knobs default to api.openai.com + gpt-4o + no judge override."""
    cfg = Settings()
    assert cfg.openai_base_url is None
    assert cfg.openai_model == "gpt-4o"
    assert cfg.judge_model is None


def test_nim_endpoint_overridable_via_env(
    clean_docintel_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DOCINTEL_OPENAI_BASE_URL / _MODEL / DOCINTEL_JUDGE_MODEL drive the NIM wiring (D-14)."""
    monkeypatch.setenv("DOCINTEL_OPENAI_BASE_URL", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setenv("DOCINTEL_OPENAI_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("DOCINTEL_JUDGE_MODEL", "meta/llama-3.3-70b-instruct")
    cfg = Settings()
    assert cfg.openai_base_url == "https://integrate.api.nvidia.com/v1"
    assert cfg.openai_model == "openai/gpt-oss-120b"
    assert cfg.judge_model == "meta/llama-3.3-70b-instruct"
