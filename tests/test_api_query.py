"""Plan 13-01 Wave-0 xfail-strict scaffold for ``POST /query`` (UI-01; D-01/D-02).

Locks the ``POST /query`` contract BEFORE 13-02 implements it (the project's
tests-first Wave-0 convention — 02-01, 04-01, 06-01, 12-01). Every test is
``@pytest.mark.xfail(strict=True)``: the endpoint does not exist yet, so each
assertion fails and the strict-xfail holds (a *passing* strict-xfail is an XPASS
that fails the suite). Plan 13-02 adds the endpoint and removes these markers
in-wave; 13-07 confirms none survive.

Node ids are bound by ``13-VALIDATION.md`` (Per-Task Verification Map) verbatim:
``test_post_query_stub_response``, ``test_post_query_refusal_card``,
``test_post_query_single_trace_record``, plus ``test_post_query_rejects_extra_fields``
(binds the T-13-02 input-validation 422 gate — Security V5).

Assertions are written against types that ALREADY exist (``Answer`` / ``Citation``
in ``docintel_core.types``; the ``trace_completed`` record shape from
``docintel_core.trace``) so the contract is real, not a stub.

Analogs: ``tests/test_health.py`` (the TestClient ``client`` fixture from
conftest); ``tests/test_trace_middleware.py`` (the ``capture_logs`` downstream
event convention).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from docintel_core.types import REFUSAL_TEXT_SENTINEL

_XFAIL_REASON = "Implemented in 13-02 (POST /query + GET /trace endpoints)"


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_post_query_stub_response(client: TestClient) -> None:
    """UI-01 / D-02 — POST /query returns an ``answer`` object + a ``trace`` block.

    The response JSON must carry an ``answer`` (the Answer shape: text, citations,
    confidence, refused) and a ``trace`` block (trace_id, ordered spans, total_ms,
    cost_usd). The bound trace_id must equal the inbound ``X-Trace-Id`` (the Phase
    12 middleware binds it end-to-end — D-01).
    """
    sent = str(uuid.uuid4())
    resp = client.post(
        "/query",
        json={"question": "What was Apple's revenue in fiscal 2024?"},
        headers={"X-Trace-Id": sent},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert "answer" in body and "trace" in body, f"response missing answer/trace: {body!r}"
    answer = body["answer"]
    for key in ("text", "citations", "confidence", "refused"):
        assert key in answer, f"answer missing key {key!r}: {answer!r}"
    assert isinstance(answer["citations"], list)

    trace = body["trace"]
    for key in ("trace_id", "spans", "total_ms", "cost_usd"):
        assert key in trace, f"trace missing key {key!r}: {trace!r}"
    assert trace["trace_id"] == sent, "the trace block must echo the inbound X-Trace-Id (D-01)"


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_post_query_refusal_card(client: TestClient) -> None:
    """UI-01 / D-04 — an out-of-corpus question yields the refusal shape.

    The UI renders a distinct amber refusal card when ``answer.refused is True``
    (or the text is the canonical refusal sentinel). Assert the SHAPE that lets
    the UI make that decision — not a specific wording.
    """
    resp = client.post(
        "/query",
        json={"question": "What is the best recipe for sourdough bread?"},
        headers={"X-Trace-Id": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    answer = resp.json()["answer"]
    assert answer["refused"] is True or answer["text"].startswith(REFUSAL_TEXT_SENTINEL), (
        "an out-of-corpus question must surface the refusal shape (D-04)"
    )


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_post_query_single_trace_record(client: TestClient) -> None:
    """UI-01 — exactly ONE ``trace_completed`` record per POST /query (no double-collector).

    RESEARCH Pitfall 3: if the handler opens its OWN ``TraceSpanCollector`` while
    the middleware already owns one, TWO ``trace_completed`` records are written
    per request. The handler must REUSE the middleware's collector (threaded via
    the ASGI scope). ``capture_logs()`` observes the consolidated record the
    collector emits on exit — exactly one must carry this request's trace_id.
    """
    sent = str(uuid.uuid4())
    with capture_logs() as records:
        resp = client.post(
            "/query",
            json={"question": "What was Apple's revenue in fiscal 2024?"},
            headers={"X-Trace-Id": sent},
        )
    assert resp.status_code == 200
    completed = [
        rec
        for rec in records
        if rec.get("event") == "trace_completed" and rec.get("trace_id") == sent
    ]
    assert len(completed) == 1, (
        f"expected exactly one trace_completed for {sent}, got {len(completed)} "
        "(double-collector? — RESEARCH Pitfall 3)"
    )


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_post_query_rejects_extra_fields(client: TestClient) -> None:
    """Security V5 (T-13-02) — POST /query rejects unknown body fields with 422.

    ``QueryRequest`` is ``extra="forbid"``: ``question`` is the only accepted
    field. An extra key (``evil``) must be rejected at the validation boundary
    (422), never silently ignored.
    """
    resp = client.post(
        "/query",
        json={"question": "What was Apple's revenue?", "evil": 1},
        headers={"X-Trace-Id": str(uuid.uuid4())},
    )
    assert resp.status_code == 422
