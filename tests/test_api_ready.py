"""Story 4.8 (FR-E7) — GET /ready readiness probe: index presence + license gate,
503 when not ready (orchestrator-friendly), non-secret payload only.
"""

from __future__ import annotations

from datetime import date

import pytest
from docintel_api.main import app, reset_settings_cache
from docintel_core.license import License, StubLicenseVerifier
from fastapi.testclient import TestClient

client = TestClient(app)


def test_ready_ok_when_index_present_and_unlicensed_demo() -> None:
    body = client.get("/ready").json()
    # The repo ships built indices → index check passes; no license → demo grant.
    assert set(body) == {"ready", "tier", "provider", "checks", "license"}
    assert body["checks"]["license"] is True
    assert body["license"]["source"] in {"unlicensed-demo", "verified"}
    assert body["tier"] in {"open", "sealed"}


def test_ready_503_on_invalid_license(monkeypatch: pytest.MonkeyPatch) -> None:
    # An expired license → not ready → 503, license.licensed false. No secret leaks.
    expired = StubLicenseVerifier().issue(
        License(licensee="Old Co", expiry=date(2020, 1, 1), tier="any")
    )
    monkeypatch.setenv("DOCINTEL_LICENSE_KEY", expired)
    reset_settings_cache()
    try:
        res = client.get("/ready")
        assert res.status_code == 503
        body = res.json()
        assert body["ready"] is False and body["checks"]["license"] is False
        # non-secret only — the token/signature never appears in the payload
        assert expired not in res.text
    finally:
        monkeypatch.delenv("DOCINTEL_LICENSE_KEY", raising=False)
        reset_settings_cache()
