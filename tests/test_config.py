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
