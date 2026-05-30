"""Streamlit UI for docintel.

Phase 1 (D-16): three skeletal tabs Query / Traces / Eval-Results — labels
LOCKED across all later phases. Health probe at the top proves docker-compose
plumbing + X-Trace-Id propagation.

Phase 13 (Plan 13-03): the Query tab is now real — a free-text question
(D-05) → ``POST /query`` over HTTP with an ``X-Trace-Id`` header (D-01) →
answer card with inline hoverable numbered citation badges + confidence badge
+ a cost/latency meter from the response trace block (D-03); refusals render
as a distinct amber card (D-04); a Sources list renders below the answer
(D-09). Traces + Eval-Results tabs stay as Plan 1 placeholders — Plan 13-04
owns them in the next wave.

This module MUST NOT read env vars directly — read everything via Settings.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import streamlit as st
from docintel_core import __version__
from docintel_core.config import Settings
from docintel_core.types import REFUSAL_TEXT_SENTINEL, Answer

from docintel_ui.citations import build_sources_list, render_citation_badges

# ---------------------------------------------------------------------------
# Settings & helpers
# ---------------------------------------------------------------------------


@st.cache_resource
def _settings() -> Settings:
    return Settings()


# Locked hero question (CONTEXT Specific Ideas — GT-comparative-001 +TSLA): the
# multi-hop comparative that stresses hybrid retrieval + cross-doc synthesis,
# pre-filled in the text box so the recruiter GIF is a one-click demo.
_HERO_QUESTION = (
    "Which of these companies grew R&D while automotive gross margin "
    "contracted year-over-year in 2023? Compare Apple, Tesla, and Microsoft."
)


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


def _call_query(api_url: str, question: str) -> tuple[bool, dict[str, Any] | str]:
    """Call POST {api_url}/query with an X-Trace-Id header (D-01).

    Mirrors ``_probe_health`` exactly so the never-raises contract is the same:
    sync ``httpx.post``, fresh UUID4 in the ``X-Trace-Id`` header (the
    middleware echoes it onto the response), 30s timeout (stub is instant; a
    real-mode LLM call may take ~10-20s).

    Returns ``(True, payload)`` on success where payload is the response JSON
    (``{"answer": Answer.model_dump(), "trace": {trace_id, spans, total_ms,
    cost_usd}}``). On failure returns ``(False, error_string)`` — never raises.
    """
    trace_id = str(uuid.uuid4())
    try:
        resp = httpx.post(
            f"{api_url}/query",
            json={"question": question},
            headers={"X-Trace-Id": trace_id},
            timeout=30.0,
        )
        resp.raise_for_status()
        return True, resp.json()
    except httpx.HTTPError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    except ValueError as exc:  # JSON decode failure
        return False, f"Invalid JSON from {api_url}/query: {exc}"


def _confidence_badge(confidence: str) -> str:
    """Map confidence string to a Streamlit-renderable colored pill.

    Plain Markdown so no ``unsafe_allow_html`` is needed at the call site (the
    citation badges are the only HTML the tab renders). Uses Streamlit's
    background colour markdown (``:green-background[...]``) which is part of
    the public 1.56 markdown grammar.
    """
    color = {"high": "green", "medium": "orange", "low": "red"}.get(confidence, "gray")
    return f":{color}-background[Confidence: {confidence}]"


def _render_query_result(payload: tuple[bool, dict[str, Any] | str]) -> None:
    """Render the (ok, payload-or-error) tuple stored in session_state.

    Pulled out into its own function so the render path is identical between
    the initial press-submit-then-render path and the re-render-on-rerun path
    (RESEARCH Pitfall 1 — Streamlit reruns the script top-to-bottom; storing
    the result in session_state and re-rendering each cycle keeps the answer
    visible across tab switches).
    """
    ok, body = payload
    if not ok:
        # Reuse the health-probe error-card pattern (CONTEXT Claude's
        # Discretion — UI error states). ``body`` is the typed error string.
        st.error(f"Query failed: {body}")
        return

    assert isinstance(body, dict)
    answer_dict = body.get("answer", {})
    trace_dict = body.get("trace", {})

    # Reconstruct the typed Answer so the citations helper sees a real
    # Citation list (validates the response shape end-to-end).
    answer_obj = Answer.model_validate(answer_dict)

    # ---- Refusal card (D-04) ----
    # Detected via Answer.refused OR text.startswith(REFUSAL_TEXT_SENTINEL).
    # The sentinel check is defense-in-depth: in real mode the LLM may emit
    # the sentinel body without refused=True being routed correctly (the
    # Phase 6 refusal classifier is the gate; the sentinel is the canonical
    # body). The amber st.warning gives the visually-distinct card.
    if answer_obj.refused or answer_obj.text.startswith(REFUSAL_TEXT_SENTINEL):
        st.warning(
            f"{answer_obj.text}\n\n"
            "This question appears to be outside the indexed 10-K corpus. "
            "Try a question about a company's financial disclosures, risk "
            "factors, or MD&A section."
        )
        trace_id = trace_dict.get("trace_id", "")
        if trace_id:
            st.caption(f"Trace: `{trace_id}` (see Traces tab for timing)")
        return

    # ---- Answer card (D-03) ----
    # Inline hoverable numbered badges via the pure citations.py helper. The
    # badges' title attributes are HTML-escaped (V5 / T-13-01) inside the
    # helper, so unsafe_allow_html=True is safe here — no user input flows
    # raw into the HTML.
    st.markdown(render_citation_badges(answer_obj), unsafe_allow_html=True)

    # Confidence + cost/latency meter row.
    col_conf, col_cost, col_latency = st.columns(3)
    with col_conf:
        st.markdown(_confidence_badge(answer_obj.confidence))
    cost_usd = float(trace_dict.get("cost_usd", 0.0))
    total_ms = float(trace_dict.get("total_ms", 0.0))
    with col_cost:
        cost_suffix = " (stub — non-representative)" if cost_usd == 0.0 else ""
        st.metric("Cost", f"${cost_usd:.6f}{cost_suffix}")
    with col_latency:
        latency_suffix = " (stub — non-representative)" if total_ms == 0.0 else ""
        st.metric("Latency", f"{total_ms:.1f} ms{latency_suffix}")

    # Sources list (D-09 — always-visible readable fallback for the GIF).
    sources = build_sources_list(answer_obj)
    if sources:
        st.markdown("**Sources:**")
        for entry in sources:
            st.markdown(entry)

    # Trace-id deep-link affordance (D-02 — the Traces tab can be filtered
    # by this id; Plan 13-04 wires the consumer).
    trace_id = trace_dict.get("trace_id", "")
    if trace_id:
        st.caption(f"Trace: `{trace_id}` (see Traces tab for timing)")


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

    # ---------------- Skeletal tabs (D-16 — labels LOCKED) ----------------
    tab_query, tab_traces, tab_eval = st.tabs(["Query", "Traces", "Eval-Results"])

    with tab_query:
        st.header("Query")
        st.caption(
            "Free-text question over the SEC 10-K corpus. The locked hero "
            "question (multi-hop comparative) is pre-filled — one click to "
            "demo. Hover a citation badge [N] to see the excerpt."
        )
        question = st.text_area(
            "Question",
            value=_HERO_QUESTION,
            height=100,
            help="Free-text only — no company/year filters in v1 (D-05).",
        )
        if st.button("Submit", type="primary"):
            with st.spinner("Querying..."):
                # Store the (ok, payload) tuple in session_state so it survives
                # Streamlit reruns + tab switches (RESEARCH Pitfall 1).
                st.session_state["query_result"] = _call_query(
                    settings.api_url, question
                )

        if "query_result" in st.session_state:
            _render_query_result(st.session_state["query_result"])

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
