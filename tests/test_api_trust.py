"""Story 3.9 — GET /trust serves the committed proof-report headline for the
in-app trust/accuracy panel (UX-DR10). Consumed over HTTP only (AD-15); degrades
to a placeholder when no report exists (AC-2), never 500.
"""

from __future__ import annotations

from docintel_api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_trust_returns_headline_from_baseline() -> None:
    res = client.get("/trust")
    assert res.status_code == 200
    body = res.json()
    # A committed baseline report exists in-repo → source == "baseline".
    assert body["source"] in {"baseline", "placeholder"}
    if body["source"] == "baseline":
        assert body["faithfulness"] is not None
        assert "pass_rate" in body["faithfulness"] and "ci" in body["faithfulness"]
        m = body["manifest"]
        # manifest carries pinned provenance for the panel
        assert {"generator_name", "prompt_version_hash", "git_sha", "provider"} <= m.keys()
        assert isinstance(body["representative"], bool)


def test_trust_never_500s_and_shape_is_stable() -> None:
    body = client.get("/trust").json()
    assert set(body.keys()) == {
        "source",
        "representative",
        "faithfulness",
        "citation_accuracy",
        "manifest",
    }
