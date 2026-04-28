"""Streamlit UI for docintel.

Phase 1 scope (CONTEXT.md D-16):
  - Three skeletal tabs: Query / Traces / Eval-Results
  - Each tab shows a "Coming in Phase 13" placeholder
  - The page header probes GET /health on the API service and renders the JSON.
    This proves the docker-compose network plumbing AND the X-Trace-Id propagation
    path on day 1 (lands again in Phase 12 with full trace context).

This module MUST NOT call os.environ / os.getenv — read everything via Settings.
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx
import streamlit as st

from docintel_core import __version__
from docintel_core.config import Settings


# ---------------------------------------------------------------------------
# Settings & helpers
# ---------------------------------------------------------------------------

@st.cache_resource
def _settings() -> Settings:
    return Settings()


def _probe_health(api_url: str, trace_id: str) -> tuple[bool, dict[str, Any] | str]:
    """Call GET {api_url}/health with an X-Trace-Id header.

    Returns (ok, payload). On success payload is the JSON dict; on failure it is
    a human-readable error string. Never raises.
    """
    try:
        resp = httpx.get(
            f"{api_url}/health",
            headers={"X-Trace-Id": trace_id},
            timeout=2.0,
        )
        resp.raise_for_status()
        return True, resp.json()
    except httpx.HTTPError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    except ValueError as exc:  # JSON decode failure
        return False, f"Invalid JSON from {api_url}/health: {exc}"


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def main() -> None:
    settings = _settings()
    st.set_page_config(page_title="docintel", layout="wide")

    st.title("docintel")
    st.caption(
        f"Production-shaped RAG over SEC 10-K filings · UI v{__version__} · "
        f"provider={settings.llm_provider}"
    )

    # ---------------- API health probe ----------------
    st.subheader("API health")
    trace_id = str(uuid.uuid4())
    ok, payload = _probe_health(settings.api_url, trace_id)
    if ok:
        st.success(f"API reachable at {settings.api_url}")
        st.json(payload)
    else:
        st.error(f"API not reachable at {settings.api_url}: {payload}")
    st.caption(f"X-Trace-Id sent: `{trace_id}`")

    # ---------------- Skeletal tabs (D-16) ----------------
    tab_query, tab_traces, tab_eval = st.tabs(["Query", "Traces", "Eval-Results"])

    with tab_query:
        st.header("Query")
        st.info(
            "Coming in Phase 13. This tab will host the query box, answer with "
            "hoverable citations, refusal-aware UI, and per-query cost meter "
            "(API-03, API-06)."
        )

    with tab_traces:
        st.header("Traces")
        st.info(
            "Coming in Phase 13 (depends on Phase 12 trace plumbing). This tab "
            "will render a flame-chart-ish view of recent queries from the JSONL "
            "trace log (API-04)."
        )

    with tab_eval:
        st.header("Eval-Results")
        st.info(
            "Coming in Phase 13 (depends on Phase 11 ablation). This tab will "
            "show the latest baseline + ablation tables with Wilson confidence "
            "intervals (API-05)."
        )


main()
