"""Tests for the D-19 Settings amendment — EDGAR User-Agent + request rate.

Covers VALIDATION.md task 3-0X-01:

* ``Settings.edgar_user_agent`` defaults to ``"docintel-ci ci@example.com"``
  (RESEARCH.md §Pattern 5 line 404 — the offline-safe identity used in CI
  so ``Downloader(...)`` can be constructed without ever hitting sec.gov).
* ``DOCINTEL_EDGAR_USER_AGENT`` flips it (env-driven, D-19).
* ``Settings.edgar_request_rate_hz`` defaults to ``8.0`` (D-19 — leaves
  headroom under SEC's 10 req/s cap, matches RESEARCH.md Pitfall 8).
* ``DOCINTEL_EDGAR_REQUEST_RATE_HZ`` flips it.

Plan 03-02 amended ``docintel_core.config.Settings`` with the two new
fields; the wave-flip post-merge gate removed the xfail markers below.
"""

from __future__ import annotations

import pytest
from docintel_core.config import Settings


def test_edgar_user_agent_default(clean_docintel_env) -> None:
    """With no env vars set, edgar_user_agent is the CI-safe placeholder."""
    assert Settings().edgar_user_agent == "docintel-ci ci@example.com"


def test_edgar_user_agent_overridable_via_env(
    clean_docintel_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DOCINTEL_EDGAR_USER_AGENT flips the User-Agent at runtime."""
    monkeypatch.setenv("DOCINTEL_EDGAR_USER_AGENT", "Test Person test@example.com")
    assert Settings().edgar_user_agent == "Test Person test@example.com"


def test_edgar_request_rate_hz_default(clean_docintel_env) -> None:
    """Default request rate is 8.0 Hz (under SEC's 10 req/s cap, D-19)."""
    settings = Settings()
    assert settings.edgar_request_rate_hz == 8.0
    assert isinstance(settings.edgar_request_rate_hz, float)


def test_edgar_request_rate_hz_overridable_via_env(
    clean_docintel_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DOCINTEL_EDGAR_REQUEST_RATE_HZ flips the request rate at runtime."""
    monkeypatch.setenv("DOCINTEL_EDGAR_REQUEST_RATE_HZ", "12.5")
    assert Settings().edgar_request_rate_hz == 12.5
