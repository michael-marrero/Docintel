"""Plan 13-02 ``POST /query`` contract tests (UI-01; D-01/D-02).

Wave 0 (Plan 13-01) scaffolded these tests as strict-xfail; Plan 13-02 added
the endpoint and removed the xfail markers in-wave (a passing strict-xfail is
an XPASS that fails the suite); 13-07 confirms none survive across the phase.

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
from docintel_core.types import REFUSAL_TEXT_SENTINEL
from fastapi.testclient import TestClient
from structlog.testing import capture_logs


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


def test_post_query_refusal_card(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """UI-01 / D-04 — a refused generation yields the refusal shape.

    The UI renders a distinct amber refusal card when ``answer.refused is True``
    (or the text is the canonical refusal sentinel). Assert the SHAPE that lets
    the UI make that decision — not a specific wording.

    The stub LLM never returns the refusal sentinel when retrieval returns any
    chunks, and BM25 over the 6053-chunk corpus returns chunks for any
    non-empty question — so we cannot drive the hard-refusal path via the
    real stub. Instead, swap the cached Generator for a stub that returns a
    refused ``GenerationResult`` (the deterministic API shape the UI cares
    about — refused/text-sentinel — flows through ``Answer.from_generation_result``
    unchanged).
    """
    from docintel_api import main as _main
    from docintel_core.types import GenerationResult
    from docintel_generate.prompts import PROMPT_VERSION_HASH

    class _RefusedGen:
        def generate(self, question: str, k: int = 5) -> GenerationResult:
            return GenerationResult(
                text=REFUSAL_TEXT_SENTINEL,
                cited_chunk_ids=[],
                refused=True,
                retrieved_chunks=[],
                completion=None,
                prompt_version_hash=PROMPT_VERSION_HASH,
            )

    monkeypatch.setattr(_main, "_generator", lambda: _RefusedGen())

    resp = client.post(
        "/query",
        json={"question": "What is the best recipe for sourdough bread?"},
        headers={"X-Trace-Id": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    answer = resp.json()["answer"]
    assert answer["refused"] is True or answer["text"].startswith(
        REFUSAL_TEXT_SENTINEL
    ), "a refused generation must surface the refusal shape (D-04)"


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


def test_post_query_multi_hop_combines_documents(client: TestClient) -> None:
    """Story 2.5 (FR-B5) — a comparative/trend question is answered by combining
    evidence across multiple filings into ONE cited answer.

    A cross-period/cross-company question rides the fixed hybrid retrieval path
    (bm25+dense → RRF → rerank → top-5, AD-9 — unchanged by this story) which
    fuses candidates over the whole corpus. The single ``Answer`` it returns must
    therefore carry citations spanning ≥2 distinct filings (a filing = one
    company × fiscal year), and each citation is independently anchored
    (separately pinnable in the UI, UX-DR6). We do not assert a specific pair —
    only that synthesis is genuinely multi-document, not single-filing.
    """
    resp = client.post(
        "/query",
        json={"question": "Which companies grew R&D while margins shrank across 2023 and 2024?"},
        headers={"X-Trace-Id": str(uuid.uuid4())},
    )
    assert resp.status_code == 200
    answer = resp.json()["answer"]
    assert not answer["refused"]
    filings = {(c["company"], c["fiscal_year"]) for c in answer["citations"]}
    assert len(filings) >= 2, f"expected multi-document synthesis, got {filings}"
    # each contributing source is separately citable (distinct chunk_ids)
    assert len({c["chunk_id"] for c in answer["citations"]}) == len(answer["citations"])


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
