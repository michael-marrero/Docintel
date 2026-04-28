"""Tests for the ``GET /health`` endpoint exposed by docintel-api.

The /health JSON shape is locked by CONTEXT.md D-15 and the
``HealthResponse`` model in ``docintel_api.main``. Phase 2 may add fields
(e.g. an ``adapters`` block) but MUST NOT rename or reshape the fields below.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


_REQUIRED_FIELDS = {
    "status",
    "service",
    "version",
    "provider",
    "git_sha",
    "timestamp",
}


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_payload_has_required_fields(client: TestClient) -> None:
    payload = client.get("/health").json()
    missing = _REQUIRED_FIELDS - payload.keys()
    assert not missing, f"missing /health fields: {missing}"


def test_health_payload_values(client: TestClient) -> None:
    payload = client.get("/health").json()
    assert payload["status"] == "ok"
    assert payload["service"] == "docintel-api"
    # Default provider is the offline stub; tests run with no env vars.
    assert payload["provider"] == "stub"
    # version / git_sha are strings (real values vary by build).
    assert isinstance(payload["version"], str) and payload["version"]
    assert isinstance(payload["git_sha"], str) and payload["git_sha"]
    # ISO-8601 UTC ending with 'Z' per main.py's normalisation.
    assert payload["timestamp"].endswith("Z")
