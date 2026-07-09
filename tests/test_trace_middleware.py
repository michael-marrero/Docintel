"""Plan 12-01 Wave 0 xfail-strict scaffold for the OBS-01 trace_id middleware.

Covers 12-VALIDATION.md rows V-01..V-03 — the pure-ASGI ``TraceIdMiddleware``
that Plan 12-04 attaches to the FastAPI app
(``packages/docintel-api/src/docintel_api/middleware.py`` + ``main.py``):

* test_trace_id_reaches_downstream_logs (V-01) — drive the app via a
  ``TestClient`` with header ``X-Trace-Id: <valid uuid4>``; capture logs via
  ``structlog.testing.capture_logs``; the request's ``trace_id`` appears on a
  log event emitted inside the endpoint. ``/health`` is the only route today —
  sufficient to prove downstream propagation (merge_contextvars surfaces the
  bound trace_id on every line for free, FND-02).
* test_generates_uuid_when_header_absent (V-02) — no ``X-Trace-Id`` header →
  a bound ``trace_id`` exists on a downstream event and parses as a UUID4.
* test_rejects_non_uuid_header (V-03) — ``X-Trace-Id: not-a-uuid`` → the bound
  ``trace_id`` is a *fresh* UUID4, NOT the literal ``not-a-uuid``. This is the
  Security V5 log-injection guard — the single most important security control
  this phase (an untrusted header must be UUID-validated before binding).

Wave-0 semantics (project xfail-first convention, Phases 6-11): every test is
``@pytest.mark.xfail(strict=True, ...)``. At Wave 0 the app has no middleware,
so no ``trace_id`` is bound on downstream events and these assertions fail —
the expected strict-xfail trigger. Plan 12-04 attaches the middleware and
Plan 12-05's xfail-removal sweep flips these to green.

Analogs:
* ``tests/test_health.py`` — the FastAPI ``TestClient`` ``client`` fixture
  convention (from ``tests/conftest.py``) for driving the app.
* ``tests/test_retriever_search.py:107-163`` — the ``capture_logs``
  downstream-event assertion convention.
* 12-RESEARCH.md §"Pattern 2" lines 313-356 (pure-ASGI middleware shape +
  the UUID-validation security control).
* 12-PATTERNS.md §"structlog capture_logs test pattern" (lines 421-435).
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from structlog.testing import capture_logs


def _is_uuid(value: object) -> bool:
    """True iff ``value`` is a string parseable as a UUID."""
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def _downstream_trace_ids(records: list[dict]) -> list[str]:
    """All distinct ``trace_id`` values bound on captured downstream events."""
    return [rec["trace_id"] for rec in records if "trace_id" in rec]


def test_trace_id_reaches_downstream_logs(client: TestClient) -> None:
    """V-01 — header trace_id appears on a downstream log event (merge_contextvars).

    Send a request to ``/health`` (the only route today) with a valid
    ``X-Trace-Id`` header. The middleware binds it into ``structlog.contextvars``
    so every log line emitted while handling the request carries it; capture
    the logs and assert the request's exact ``trace_id`` shows up on a
    downstream event.
    """
    sent = str(uuid.uuid4())
    with capture_logs() as records:
        resp = client.get("/health", headers={"X-Trace-Id": sent})
    assert resp.status_code == 200
    assert sent in _downstream_trace_ids(records), (
        "V-01: the inbound X-Trace-Id must be bound onto a downstream log event "
        f"via merge_contextvars; captured trace_ids={_downstream_trace_ids(records)!r}"
    )


def test_generates_uuid_when_header_absent(client: TestClient) -> None:
    """V-02 — absent X-Trace-Id → a UUID4 is generated and bound.

    With NO ``X-Trace-Id`` header, the middleware must mint a fresh UUID4 and
    bind it; a downstream event must carry a ``trace_id`` that parses as a UUID.
    """
    with capture_logs() as records:
        resp = client.get("/health")
    assert resp.status_code == 200
    bound = _downstream_trace_ids(records)
    assert bound, "V-02: a generated trace_id must be bound on a downstream event"
    assert any(
        _is_uuid(tid) for tid in bound
    ), f"V-02: generated trace_id must parse as a UUID; got {bound!r}"


def test_rejects_non_uuid_header(client: TestClient) -> None:
    """V-03 — non-UUID X-Trace-Id → a fresh UUID4 (log-injection guard, Security V5).

    The inbound ``X-Trace-Id`` is untrusted. When it is not a valid UUID
    (``not-a-uuid``), the middleware must NOT bind the raw string — it must mint
    a fresh UUID4 instead. This is the single most important security control
    this phase: a raw attacker-controlled header must never reach the log sink.
    """
    bad = "not-a-uuid"
    with capture_logs() as records:
        resp = client.get("/health", headers={"X-Trace-Id": bad})
    assert resp.status_code == 200
    bound = _downstream_trace_ids(records)
    assert bound, "V-03: a trace_id must still be bound on a downstream event"
    assert (
        bad not in bound
    ), "V-03 (Security V5): the raw non-UUID header must NOT be bound verbatim"
    assert any(
        _is_uuid(tid) for tid in bound
    ), f"V-03: a fresh UUID4 must be bound instead of {bad!r}; got {bound!r}"
