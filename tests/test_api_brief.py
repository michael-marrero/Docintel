"""Story 2.2 — GET /brief/{ticker} streams a four-section cited brief as SSE.

Covered ticker → 4 ``section`` events + a ``done`` event; uncovered → a single
``refused`` event (routes, never fabricates). Same-origin plain HTTP (AD-15).
"""

import json

from docintel_api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    """Parse an SSE stream body into (event, data) pairs."""
    events = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        if event is not None:
            events.append((event, data))
    return events


def _first_covered_ticker() -> str:
    return client.get("/coverage").json()["companies"][0]["ticker"]


def test_brief_streams_four_sections_then_done():
    ticker = _first_covered_ticker()
    res = client.get(f"/brief/{ticker}")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(res.text)
    kinds = [e for e, _ in events]
    assert kinds.count("section") == 4, kinds
    assert kinds[-1] == "done"

    # sections arrive in order 0..3 with a stable key + title + an Answer shape
    section_events = [d for e, d in events if e == "section"]
    assert [d["index"] for d in section_events] == [0, 1, 2, 3]
    for d in section_events:
        assert d["key"] and d["title"]
        ans = d["answer"]
        assert {"text", "citations", "confidence", "refused"} <= ans.keys()

    done = events[-1][1]
    assert done["sections"] == 4
    assert done["ticker"].upper() == ticker.upper()


def test_brief_citations_are_scoped_to_the_requested_company():
    # Ticker-scoped retrieval (Story 2.2): a non-refused section must cite ONLY
    # the requested company's chunks (chunk_id is prefixed with the ticker).
    ticker = _first_covered_ticker().upper()
    events = _parse_sse(client.get(f"/brief/{ticker}").text)
    for _, d in [e for e in events if e[0] == "section"]:
        ans = d["answer"]
        if ans["refused"]:
            continue
        for cit in ans["citations"]:
            assert cit["chunk_id"].upper().startswith(ticker), cit["chunk_id"]


def test_brief_uncovered_ticker_refuses_without_fabricating():
    res = client.get("/brief/ZZZZ")
    assert res.status_code == 200
    events = _parse_sse(res.text)
    assert len(events) == 1
    kind, data = events[0]
    assert kind == "refused"
    assert data["ticker"] == "ZZZZ"
    # no section events, no fabricated brief
    assert not any(e == "section" for e, _ in events)
