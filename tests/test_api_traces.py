"""Plan 13-01 Wave-0 xfail-strict scaffold for ``GET /traces`` + ``GET /trace/{id}`` (UI-01; D-10).

Locks the trace read-endpoint contract BEFORE 13-02 implements it. Every test is
strict-xfail: the endpoints do not exist yet (404), so the assertions fail and
the xfail holds. 13-02 adds the endpoints (reading via
``docintel_core.trace.load_traces`` over ``settings.trace_dir``) and removes
these markers; 13-07 confirms none survive.

The tests seed a tmp ``trace_dir`` with records in the consolidated
``trace_completed`` shape produced by ``docintel_core.trace.TraceSpanCollector``,
point ``DOCINTEL_TRACE_DIR`` at it, and clear the Settings cache so the request
handler's ``_settings()`` re-reads it (D-10: the UI fetches over HTTP; the API is
the sole reader of ``trace_dir``).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from docintel_core.trace import load_traces

_XFAIL_REASON = "Implemented in 13-02 (GET /traces + GET /trace/{id})"


def _seed_trace_dir(trace_dir: Path, *trace_ids: str) -> None:
    """Write one consolidated ``trace_completed`` JSONL record per id (trace.py shape)."""
    trace_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {
                "trace_id": tid,
                "source": "api",
                "total_ms": 12.34,
                "spans": [
                    {"name": "retrieval", "duration_ms": 4.2},
                    {"name": "generation", "duration_ms": 8.1},
                ],
                "cost_usd": 0.0,
                "model": "stub-llm",
                "refused": False,
            }
        )
        for tid in trace_ids
    ]
    (trace_dir / "traces-seed.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _point_settings_at(monkeypatch: pytest.MonkeyPatch, trace_dir: Path) -> None:
    """Repoint Settings.trace_dir at ``trace_dir`` for the next request handler read."""
    monkeypatch.setenv("DOCINTEL_TRACE_DIR", str(trace_dir))
    from docintel_api.main import reset_settings_cache

    reset_settings_cache()


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_get_traces_returns_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """GET /traces returns a JSON list; each element carries ``trace_id`` + ``total_ms``."""
    trace_dir = tmp_path / "seedtraces"
    known = str(uuid.uuid4())
    _seed_trace_dir(trace_dir, known, str(uuid.uuid4()))
    # sanity: the seed is readable by the same helper the endpoint uses
    assert any(rec["trace_id"] == known for rec in load_traces(str(trace_dir)))
    _point_settings_at(monkeypatch, trace_dir)

    resp = client.get("/traces")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list) and body, f"expected non-empty list, got {body!r}"
    for rec in body:
        assert "trace_id" in rec and "total_ms" in rec


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_get_trace_by_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """GET /trace/{id} returns the single matching ``trace_completed`` record."""
    trace_dir = tmp_path / "seedtraces"
    known = str(uuid.uuid4())
    _seed_trace_dir(trace_dir, known)
    _point_settings_at(monkeypatch, trace_dir)

    resp = client.get(f"/trace/{known}")
    assert resp.status_code == 200
    assert resp.json()["trace_id"] == known


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_get_trace_unknown_returns_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """GET /trace/{unknown} returns 404 — with a positive control proving the route exists.

    A bare 404 is ambiguous at Wave 0: an *undefined* route also 404s, which would
    make this a false XPASS. The positive control (a seeded known id MUST return
    200) makes the test genuinely fail until 13-02 mounts the endpoint, so the
    strict-xfail holds; once 13-02 lands, both assertions pass.
    """
    trace_dir = tmp_path / "seedtraces"
    known = str(uuid.uuid4())
    _seed_trace_dir(trace_dir, known)
    _point_settings_at(monkeypatch, trace_dir)

    # Positive control: the endpoint must exist and resolve the seeded id.
    assert client.get(f"/trace/{known}").status_code == 200
    # The real assertion: an unknown id is a 404 from the (existing) endpoint.
    assert client.get(f"/trace/{uuid.uuid4()}").status_code == 404
