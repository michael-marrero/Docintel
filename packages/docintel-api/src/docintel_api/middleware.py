"""Pure-ASGI trace_id middleware for the docintel FastAPI app (OBS-01, D-01).

Binds a ``trace_id`` into ``structlog.contextvars`` for the duration of every
HTTP request so it rides every downstream log line via the already-wired
``merge_contextvars`` processor (``docintel_core.log`` — FND-02). Covers
``/health`` today and the future ``POST /query`` (Phase 13, D-05) for free.

**Pure ASGI — NOT ``BaseHTTPMiddleware`` / ``@app.middleware("http")``** (RESEARCH
Pitfall 1, verified against Starlette 1.0.0): ``BaseHTTPMiddleware`` runs the
endpoint in a child anyio task whose contextvars are isolated from the
middleware's post-request code (PEP-567). The consolidated ``trace_completed``
record is assembled by ``TraceSpanCollector.__exit__`` *after* the request, so we
keep bind + assemble + clear in a single context. A raw ASGI callable
(``async def __call__(self, scope, receive, send)``) runs everything in one
context, sidestepping the footgun entirely. This project is canary-minded; we do
not rely on the working-by-luck downward direction.

Security (T-12-05 — the single most important control this phase): the inbound
``X-Trace-Id`` header is **untrusted** and is UUID-validated before binding. A
non-UUID (or newline/control-char/fake-JSON) value yields a fresh ``uuid.uuid4()``
— a raw arbitrary header string is NEVER bound into the log sink (Security V5,
log-injection guard; asserted by ``tests/test_trace_middleware.py`` V-03). The UI
already sends a UUID4, so legitimate clients are unaffected.

FND-11: this module MUST NOT read the environment. ``trace_dir`` arrives via the
injected ``Settings`` (from ``main.py``'s ``_settings()`` accessor); ``config.py``
is the only env reader.
"""

from __future__ import annotations

import uuid

from docintel_core.config import Settings
from docintel_core.trace import TraceSpanCollector
from starlette.types import ASGIApp, Receive, Scope, Send

# Locked inbound header contract (D-01). ASGI scope headers are lowercased bytes.
_TRACE_HEADER = b"x-trace-id"


def _is_static_asset(scope: Scope) -> bool:
    """True for static frontend file serving (Story 2.1 mount) — infrastructure,
    not an application request, so it gets no trace context and writes no record.

    The observability showcase (GET /traces) is about the RAG query pipeline;
    tracing every ``/app.js`` / ``/tokens.css`` fetch would write an empty-span
    record per asset per page load and bury the real query traces. API routes are
    extensionless (``/coverage``, ``/query``, ``/health``, ``/traces``,
    ``/trace/{uuid}``); the frontend is ``/`` plus files carrying an extension.
    """
    if scope.get("method") not in ("GET", "HEAD"):
        return False
    path = scope.get("path", "")
    return path == "/" or "." in path.rsplit("/", 1)[-1]


def _validate_trace_id(raw: str | None) -> str:
    """Return a bound-safe trace_id (Security V5).

    Accept ``raw`` only if it parses as a UUID; otherwise mint a fresh UUID4.
    Never bind an arbitrary attacker-controlled string into the log sink.
    """
    if raw is not None:
        try:
            uuid.UUID(raw)
        except (ValueError, AttributeError, TypeError):
            pass
        else:
            return raw
    return str(uuid.uuid4())


class TraceIdMiddleware:
    """Pure-ASGI middleware (NOT ``BaseHTTPMiddleware``) — binds a UUID-validated
    ``trace_id`` so it reaches downstream loggers in the SAME contextvars context.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self._settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Non-HTTP scopes (lifespan, websocket) carry no X-Trace-Id and no
        # request-scoped logging context — pass straight through untouched.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Static frontend assets are infrastructure, not traced application
        # requests — pass through so they don't spam the trace sink (Story 2.1).
        if _is_static_asset(scope):
            await self.app(scope, receive, send)
            return

        # ASGI headers are an iterable of (name, value) byte tuples. Read the
        # FIRST x-trace-id; decode defensively (latin-1 never raises on bytes).
        raw_header: str | None = None
        for name, value in scope["headers"]:
            if name == _TRACE_HEADER:
                raw_header = value.decode("latin-1")
                break

        trace_id = _validate_trace_id(raw_header)

        # The collector binds trace_id on enter, writes one consolidated
        # trace_completed record on exit, and clears contextvars in a finally
        # (D-01 leak guard) — even if the downstream app raises.
        #
        # Phase 13 (Plan 13-02, RESEARCH Pitfall 3): thread the LIVE collector
        # onto ``scope["state"]["trace_collector"]`` so the POST /query handler
        # reuses it via ``request.state.trace_collector`` and records its
        # ``pipeline`` span on the SAME collector — avoiding the double-write
        # that would happen if the handler opened a second collector with the
        # same trace_id (two ``trace_completed`` records for one request).
        with TraceSpanCollector(self._settings.trace_dir, trace_id=trace_id, source="api") as tc:
            scope.setdefault("state", {})
            scope["state"]["trace_collector"] = tc
            await self.app(scope, receive, send)
