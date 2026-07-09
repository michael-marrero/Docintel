"""Streamlit UI for docintel.

Phase 1 (D-16): three skeletal tabs Query / Traces / Eval-Results — labels
LOCKED across all later phases. Health probe at the top proves docker-compose
plumbing + X-Trace-Id propagation.

Phase 13 (Plan 13-03): the Query tab is real — free-text question (D-05) →
``POST /query`` over HTTP with an ``X-Trace-Id`` header (D-01) → answer card
with inline hoverable numbered citation badges + confidence badge + a
cost/latency meter from the response trace block (D-03); refusals render as
a distinct amber card (D-04); a Sources list renders below the answer (D-09).

Phase 13 (Plan 13-04): the Traces and Eval-Results tabs are real:

* Traces tab fetches ``GET /traces`` over HTTP (D-10 — the UI never reads the
  trace_dir directly; the API owns the JSONL files), renders a newest-first
  recent-queries table (``st.dataframe`` with row-selection), and on
  row-select renders per-stage horizontal timing bars via Altair
  ``mark_bar`` + ``x``/``x2`` cumulative-start waterfall (D-11). Stub-mode
  ``duration_ms == 0`` is labelled honestly so the recruiter GIF reads as
  non-representative.
* Eval-Results tab uses the pure helpers in ``docintel_ui.eval_view`` to
  auto-detect the newest real report under ``data/eval/reports/`` else the
  committed ``stub-sample`` (D-13), surfaces the ``representative: false``
  warning banner above the headline tables when in stub mode, and renders
  the native Streamlit headline tables for retrieval (Hit@5/Hit@3/MRR +
  Wilson CIs) + faithfulness + ablation arm deltas (bootstrap CIs from
  ``ablation-manifest.json``), plus an ``st.expander`` carrying the full
  committed ``report.md`` / ``ablation-report.md`` (D-12).

This module MUST NOT read env vars directly — read everything via Settings.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import altair as alt
import httpx
import pandas as pd
import streamlit as st
from docintel_core import __version__
from docintel_core.config import Settings
from docintel_core.types import REFUSAL_TEXT_SENTINEL, Answer

from docintel_ui.citations import build_sources_list, render_citation_badges
from docintel_ui.eval_view import (
    _find_eval_report,
    load_ablation_manifest,
    load_results,
    parse_ablation_rows,
    parse_faithfulness_row,
    parse_retrieval_rows,
    representative_banner,
)

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


def _fetch_traces(api_url: str) -> tuple[bool, list[dict[str, Any]] | str]:
    """Call GET {api_url}/traces (D-10).

    Mirrors ``_probe_health`` exactly: sync ``httpx.get``, fresh UUID4 in the
    ``X-Trace-Id`` header (the API echoes it; the middleware binds it for the
    /traces request itself), short 3s timeout (the API just reads a few JSONL
    files), never-raises ``(ok, payload)`` return.

    Returns ``(True, traces_list)`` on success where ``traces_list`` is the
    response JSON (newest-first per the API; Plan 13-02 reverses
    ``load_traces`` output before returning). On failure returns
    ``(False, error_string)``.
    """
    trace_id = str(uuid.uuid4())
    try:
        resp = httpx.get(
            f"{api_url}/traces",
            headers={"X-Trace-Id": trace_id},
            timeout=3.0,
        )
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, list):
            return False, f"Unexpected /traces payload (not a list): {type(body).__name__}"
        return True, body
    except httpx.HTTPError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    except ValueError as exc:  # JSON decode failure
        return False, f"Invalid JSON from {api_url}/traces: {exc}"


def _render_stage_bars(trace: dict[str, Any]) -> None:
    """Render per-stage horizontal timing bars for a single trace (D-11).

    Builds a cumulative-start waterfall from the trace's ``spans`` list
    (each span carries ``name`` + ``duration_ms``) and renders an Altair
    ``mark_bar`` with ``x`` = ``start_ms``, ``x2`` = ``end_ms``, ``y`` =
    ``stage``. This is the canonical Altair Gantt-chart primitive
    (RESEARCH Focus Area 2; ``st.bar_chart`` cannot render horizontal
    range-encoded bars).

    Stub-mode traces carry ``duration_ms == 0.0`` on every span (the stub
    LLM is instant) — the chart still renders (zero-width bars) and the
    caption labels the situation honestly so the recruiter GIF reads as
    non-representative.
    """
    spans = trace.get("spans", [])
    if not spans:
        st.info("No span data in this trace.")
        return

    cumulative_start = 0.0
    rows: list[dict[str, Any]] = []
    for span in spans:
        duration = float(span.get("duration_ms", 0.0))
        rows.append(
            {
                "stage": str(span.get("name", "unknown")),
                "start_ms": cumulative_start,
                "end_ms": cumulative_start + duration,
                "duration_ms": duration,
            }
        )
        cumulative_start += duration

    df = pd.DataFrame(rows)

    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("start_ms:Q", title="Time (ms)"),
            x2=alt.X2("end_ms:Q"),
            y=alt.Y("stage:N", title="Stage", sort=None),
            color=alt.Color("stage:N", legend=None),
            tooltip=[
                alt.Tooltip("stage:N", title="Stage"),
                alt.Tooltip("duration_ms:Q", title="Duration (ms)", format=".1f"),
                alt.Tooltip("start_ms:Q", title="Start (ms)", format=".1f"),
            ],
        )
        .properties(height=150, title="Per-stage timing (waterfall)")
    )

    st.altair_chart(chart, use_container_width=True)

    total_ms = float(trace.get("total_ms", 0.0))
    cost_usd = float(trace.get("cost_usd", 0.0))
    stub_note = (
        " · stub mode — all durations are 0 ms (non-representative)" if total_ms == 0.0 else ""
    )
    st.caption(f"Total: {total_ms:.1f} ms · Cost: ${cost_usd:.6f}{stub_note}")


def _render_traces_tab(settings: Settings) -> None:
    """Render the Traces tab body — recent-queries table + selected timing bars.

    Fetches over HTTP from ``GET /traces`` (D-10 — never reads ``trace_dir``
    directly). The API already returns newest-first (Plan 13-02 reverses
    ``load_traces`` output, RESEARCH Pitfall 8); we slice the first 50 for
    the table. ``st.dataframe`` with ``selection_mode="single-row"`` +
    ``on_select="rerun"`` is the Streamlit 1.56 row-selection API
    (RESEARCH Focus Area 2 / Pitfall 5).
    """
    ok, body = _fetch_traces(settings.api_url)
    if not ok:
        st.error(f"Could not fetch traces from {settings.api_url}/traces: {body}")
        return

    assert isinstance(body, list)
    if not body:
        st.info("No traces yet. Run a query from the Query tab to populate this view.")
        return

    # Defensive newest-first slice — the API reverses load_traces, but we
    # apply ``list(...)[:50]`` here so the row indices used by the dataframe
    # selection map 1:1 onto the displayed rows even if the API ever changes
    # its ordering convention (Pitfall 8 defense-in-depth).
    display_traces: list[dict[str, Any]] = list(body)[:50]

    summary_rows: list[dict[str, Any]] = []
    for record in display_traces:
        trace_id_short = str(record.get("trace_id", ""))[:8]
        summary_rows.append(
            {
                "trace_id": f"{trace_id_short}…",
                "total_ms": float(record.get("total_ms", 0.0)),
                "cost_usd": float(record.get("cost_usd", 0.0)),
                "refused": bool(record.get("refused", False)),
                "source": str(record.get("source", "")),
            }
        )

    selected = st.dataframe(
        summary_rows,
        selection_mode="single-row",
        on_select="rerun",
        use_container_width=True,
        hide_index=False,
    )

    selection_rows = getattr(getattr(selected, "selection", None), "rows", []) or []
    if selection_rows:
        idx = int(selection_rows[0])
        if 0 <= idx < len(display_traces):
            _render_stage_bars(display_traces[idx])
    else:
        st.caption("Select a row above to see per-stage timing bars.")


def _render_eval_tab(settings: Settings) -> None:
    """Render the Eval-Results tab body — auto-detect, banner, native tables, expander.

    Calls ``_find_eval_report(settings.data_dir)`` for the report dir +
    representative flag (D-13 auto-detect; T-13-07 path-confined). Renders:

    1. The ``representative: false`` warning banner above the headline tables
       in stub mode (D-13 honest-stub labelling).
    2. Native ``st.table`` for the retrieval headline rows (Hit@5/Hit@3/MRR +
       Wilson CIs) and a faithfulness pass-rate row (D-12).
    3. Native ``st.table`` for the ablation arms (deltas + bootstrap CIs)
       sourced from the matching ablation manifest if present.
    4. An ``st.expander`` carrying the full committed ``report.md`` +
       ``ablation-report.md`` for depth (D-12 — recruiters skim the tables;
       engineers read the markdown).

    All file paths are confined to ``Path(settings.data_dir) / "eval" / ...``
    (Pitfall 9 / FND-11 — never hardcode the container data root).
    """
    report_dir, is_representative = _find_eval_report(settings.data_dir)

    if report_dir is None:
        st.warning(
            "No eval report found under "
            f"`{Path(settings.data_dir) / 'eval' / 'reports'}`. "
            "Run `docintel-eval run` to generate one."
        )
        return

    banner = representative_banner(is_representative)
    if banner is not None:
        st.warning(banner)

    results = load_results(report_dir)
    st.subheader("Retrieval metrics")
    st.table(parse_retrieval_rows(results))

    st.subheader("Faithfulness")
    st.table([parse_faithfulness_row(results)])

    # Ablation manifest — mirror the report-dir auto-detect convention.
    # When we resolved a real timestamped report, look for an
    # identically-named ablation sibling; otherwise fall back to stub-sample.
    ablations_base = Path(settings.data_dir) / "eval" / "ablations"
    if is_representative:
        ablations_dir = ablations_base / report_dir.name
        if not ablations_dir.is_dir():
            ablations_dir = ablations_base / "stub-sample"
    else:
        ablations_dir = ablations_base / "stub-sample"
    manifest = load_ablation_manifest(ablations_dir)
    if manifest is not None:
        st.subheader("Ablation deltas")
        st.caption(
            f"Baseline = `{manifest.get('baseline', '?')}` · "
            f"Δ = bootstrap mean change vs baseline · "
            f"`[lo, hi]` = 95% bootstrap CI · "
            f"n_boot = {manifest.get('n_boot', '?')}"
        )
        st.table(parse_ablation_rows(manifest))

    # Full-report expander (D-12 — depth on demand).
    report_md = report_dir / "report.md"
    if report_md.is_file():
        with st.expander("Full eval report (markdown)"):
            st.markdown(report_md.read_text())

    ablation_md = ablations_dir / "ablation-report.md"
    if ablation_md.is_file():
        with st.expander("Full ablation report (markdown)"):
            st.markdown(ablation_md.read_text())


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
                st.session_state["query_result"] = _call_query(settings.api_url, question)

        if "query_result" in st.session_state:
            _render_query_result(st.session_state["query_result"])

    with tab_traces:
        st.header("Traces")
        st.caption(
            "Recent queries with per-stage timing. Select a row to see "
            "horizontal timing bars (waterfall) for that trace. Stub mode "
            "shows zero-width bars — durations are 0 ms by construction."
        )
        _render_traces_tab(settings)

    with tab_eval:
        st.header("Eval-Results")
        st.caption(
            "Headline retrieval + ablation metrics from the most recent eval "
            "run (auto-detected). If no real run is on disk this falls back "
            "to the committed stub-sample and surfaces a "
            "`representative: false` banner."
        )
        _render_eval_tab(settings)


main()
