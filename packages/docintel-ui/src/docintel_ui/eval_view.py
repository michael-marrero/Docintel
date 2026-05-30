"""Pure helpers for the docintel Eval-Results tab (UI-04; D-12/13).

Streamlit-free, environment-variable-free, unit-testable. Owns four pieces of
read-only display logic the Streamlit tab in ``streamlit_app.py`` then composes
with native widgets:

1. ``_find_eval_report(data_dir) -> (Path | None, is_representative)`` —
   auto-detects the newest timestamped real report under
   ``data/eval/reports/`` (manifest carries ``representative: true``); falls
   back to the committed ``stub-sample`` directory with
   ``is_representative=False`` when no real report is present. Returns
   ``(None, False)`` when neither is on disk (D-13).
2. ``parse_retrieval_rows(results)`` — flattens the ``retrieval`` sub-tree of a
   committed ``results.json`` into rows for the headline Hit@5/Hit@3/MRR
   table with Wilson 95% CIs (MRR has no CI in the current schema → blank).
3. ``parse_ablation_rows(manifest)`` — flattens an ``ablation-manifest.json``
   into one row per arm carrying each headline metric value plus its
   ``delta / [lo, hi]`` bootstrap CI (baseline arm shows "baseline" instead of
   a delta since its ``deltas`` dict is empty).
4. ``representative_banner(is_representative)`` — banner-text predicate: when
   ``False`` returns the canonical honest-stub warning string; when ``True``
   returns ``None`` (so the caller renders nothing).

Module split rationale (Plan 13-04 boundary): this file imports NO
``streamlit`` and reads NO environment variables (FND-11 — env reads live in
``docintel_core.config.Settings`` only). The streamlit tab in
``streamlit_app.py`` consumes these helpers via ``st.table`` /
``st.warning`` / ``st.markdown``; the auto-detect + banner predicate are
unit-tested in ``tests/test_ui_eval_tab.py`` without a running Streamlit
server (the Wave 0 contract from Plan 13-01).

Security (T-13-07 — path traversal in eval-report scan): every path is
confined inside ``Path(data_dir) / "eval"``; only known subdirectory names
(``reports/``, ``ablations/``, ``stub-sample/``) are iterated. No user input
ever feeds the path; no hardcoded container data root (Pitfall 9). The
``data_dir`` arrives from ``Settings.data_dir`` (the single env reader,
FND-11), so the boundary is enforced by configuration, not by ad-hoc string
manipulation.

JSON schemas (verified against the committed stub-sample, 13-04 Task 1
``read_first`` § ``data/eval/reports/stub-sample/results.json`` and
``data/eval/ablations/stub-sample/ablation-manifest.json``):

* ``results.json`` carries a ``retrieval`` block with
  ``hit_at_{1,3,5,10}`` + their ``_ci`` keys (two-element ``[lo, hi]`` lists),
  ``mrr`` (no CI), ``faithfulness`` (with ``faithfulness_pass_rate`` +
  ``faithfulness_ci``), and a top-level ``manifest`` whose
  ``representative`` bool drives the banner.
* ``ablation-manifest.json`` carries ``arm_names`` (list), ``arms`` (dict
  arm-name → ``{metrics, deltas, components}``; baseline ``deltas`` is the
  empty dict), ``headline_metrics`` (list of metric keys), and ``baseline``.
* Per-arm ``deltas[metric] = [delta, lo, hi]`` triplets are the bootstrap
  CIs. Baseline rows have an empty ``deltas`` dict — caller writes
  ``"baseline"`` instead of a delta.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = [
    "_find_eval_report",
    "parse_retrieval_rows",
    "parse_ablation_rows",
    "parse_faithfulness_row",
    "load_results",
    "load_ablation_manifest",
    "representative_banner",
]


# Known subdirectory names — the only entries we will ever descend into under
# ``Path(data_dir) / "eval"``. This is the path-traversal-safety control
# (T-13-07): no user-controlled path component flows into the filesystem walk.
_STUB_SAMPLE_DIR = "stub-sample"
_REPORTS_SUBDIR = "reports"
_ABLATIONS_SUBDIR = "ablations"


# Honest stub banner — the canonical wording for D-13's "representative: false"
# banner. Render via ``st.warning`` so it gets the prominent amber treatment.
_STUB_BANNER = (
    "Showing **stub-sample** results — these numbers are "
    "**`representative: false`** (stub LLM; latency $0$ ms; cost $\\$0$). "
    "Run a real-mode eval (`docintel-eval run` with `LLM_PROVIDER` set to a "
    "real provider) for meaningful Hit@K / MRR / faithfulness metrics."
)


def _find_eval_report(data_dir: str) -> tuple[Path | None, bool]:
    """Auto-detect the eval report directory to render (D-13).

    Resolution order:

    1. ``Path(data_dir) / "eval" / "reports"``. Among its direct child
       directories, collect those whose name is NOT ``stub-sample`` AND that
       contain a ``results.json`` file. Sort by ``name`` (real reports are
       timestamped, so lexical sort == newest-last). If any exist, return
       ``(newest, True)`` — the real report supersedes the stub fallback.
    2. Else if ``stub-sample/results.json`` exists at the same base, return
       ``(stub_sample_dir, False)`` — the committed fallback for a fresh
       clone offline (D-13).
    3. Else return ``(None, False)`` — caller renders an "eval has not been
       run yet" notice.

    Path-confinement (T-13-07): we only ever touch the canonical subdir
    names; no user input contributes to the path. ``data_dir`` arrives from
    ``Settings.data_dir`` (FND-11), so the entire path is configuration-
    derived, not request-derived.

    Args:
        data_dir: the ``Settings.data_dir`` value — the project's data root
            (e.g. ``"data"`` locally or the configured container data root). The
            ``eval/`` subtree is rooted under this.

    Returns:
        ``(report_path, is_representative)``. ``report_path`` is the
        directory containing ``results.json`` (and typically ``report.md``).
        ``is_representative`` is ``True`` ONLY when we resolved to a real
        timestamped report whose manifest carries ``representative: true``
        (and a ``results.json`` exists on disk); ``False`` for the
        stub-sample fallback and for the "not found" terminal case.
    """
    reports_base = Path(data_dir) / "eval" / _REPORTS_SUBDIR

    if reports_base.is_dir():
        real_reports = sorted(
            d
            for d in reports_base.iterdir()
            if d.is_dir()
            and d.name != _STUB_SAMPLE_DIR
            and (d / "results.json").is_file()
        )
        if real_reports:
            return real_reports[-1], True

    stub_sample = reports_base / _STUB_SAMPLE_DIR
    if stub_sample.is_dir() and (stub_sample / "results.json").is_file():
        return stub_sample, False

    return None, False


def representative_banner(is_representative: bool) -> str | None:
    """Return the banner text for ``representative: false`` mode (D-13).

    When ``is_representative`` is ``False``, returns a prominent honest-stub
    warning string that the Streamlit tab renders via ``st.warning`` above
    the headline tables. When ``True``, returns ``None`` (no banner —
    real-mode numbers stand on their own).

    The banner string includes the lowercase substring ``"representative"``
    so the Wave 0 contract test (``test_eval_tab_stub_banner``) can detect
    that the banner is meaningful (not just a "warning! warning!" placeholder).
    """
    if is_representative:
        return None
    return _STUB_BANNER


def _fmt_ci(ci_pair: list[float] | tuple[float, float] | None) -> str:
    """Render a ``[lo, hi]`` CI pair as a compact bracketed string.

    Returns the empty string for a ``None`` or empty pair so the headline
    table can show a blank cell for metrics that carry no CI (MRR in the
    current schema). Out-of-shape pairs (anything other than length 2) are
    also rendered as blank — defensive, since the JSON shape is verified
    against the committed sample but a future schema drift would otherwise
    crash the entire tab.
    """
    if not ci_pair or len(ci_pair) != 2:
        return ""
    lo, hi = ci_pair
    return f"[{lo:.3f}, {hi:.3f}]"


def load_results(report_dir: Path) -> dict[str, Any]:
    """Load a ``results.json`` from ``report_dir`` (path-confined per
    ``_find_eval_report`` upstream).

    Thin wrapper around ``json.loads`` over the file at
    ``report_dir / "results.json"``. Centralises the path construction so
    the tab body has a single place to call.
    """
    data: dict[str, Any] = json.loads((report_dir / "results.json").read_text())
    return data


def load_ablation_manifest(ablations_dir: Path) -> dict[str, Any] | None:
    """Load an ``ablation-manifest.json`` from ``ablations_dir`` if present.

    Returns ``None`` when no manifest is on disk (a real eval with no
    matching ablation run is a valid state — the tab just skips the
    ablation table). Path-confined by the caller (the tab uses
    ``Path(settings.data_dir) / "eval" / "ablations" / "stub-sample"`` or
    the resolved real-mode sibling).
    """
    manifest_path = ablations_dir / "ablation-manifest.json"
    if not manifest_path.is_file():
        return None
    data: dict[str, Any] = json.loads(manifest_path.read_text())
    return data


def parse_retrieval_rows(results: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten ``results["retrieval"]`` into the Hit@5/Hit@3/MRR headline rows.

    Reads the verified-shape keys ``hit_at_5``, ``hit_at_3``, ``mrr``, plus
    ``hit_at_5_ci`` and ``hit_at_3_ci`` (two-element ``[lo, hi]`` Wilson
    intervals). MRR has no CI in the current schema (it's a mean reciprocal
    rank, not a rate); the CI cell is rendered blank.

    Returns:
        A list of row dicts with keys ``Metric``, ``Value``, and
        ``95% Wilson CI``. Designed for direct consumption by
        ``st.table(rows)`` or ``pd.DataFrame(rows)``.
    """
    retrieval = results.get("retrieval", {})
    return [
        {
            "Metric": "Hit@5",
            "Value": f"{retrieval.get('hit_at_5', 0.0):.3f}",
            "95% Wilson CI": _fmt_ci(retrieval.get("hit_at_5_ci")),
        },
        {
            "Metric": "Hit@3",
            "Value": f"{retrieval.get('hit_at_3', 0.0):.3f}",
            "95% Wilson CI": _fmt_ci(retrieval.get("hit_at_3_ci")),
        },
        {
            "Metric": "MRR",
            "Value": f"{retrieval.get('mrr', 0.0):.3f}",
            "95% Wilson CI": "",  # MRR has no CI in the current schema
        },
    ]


def parse_faithfulness_row(results: dict[str, Any]) -> dict[str, str]:
    """Flatten ``results["faithfulness"]`` into a single headline row.

    Reads ``faithfulness_pass_rate`` + the two-element Wilson CI under
    ``faithfulness_ci``. Returned as a single-row dict so the tab body can
    surface it next to the retrieval table without inventing another widget.
    """
    faithfulness = results.get("faithfulness", {})
    return {
        "Metric": "Faithfulness pass rate",
        "Value": f"{faithfulness.get('faithfulness_pass_rate', 0.0):.3f}",
        "95% Wilson CI": _fmt_ci(faithfulness.get("faithfulness_ci")),
    }


def parse_ablation_rows(manifest: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten an ablation manifest into one row per arm.

    For each arm in ``manifest["arm_names"]``, builds a row carrying the
    arm name plus, for every metric in ``manifest["headline_metrics"]``,
    the arm's metric value AND its bootstrap CI triplet (``[delta, lo, hi]``)
    formatted as ``"{value:.3f} (Δ{delta:+.3f} [lo, hi])"``. The baseline
    arm has an empty ``deltas`` dict by construction — its row shows
    ``"{value:.3f} (baseline)"`` instead of a delta (no arm can be its own
    delta).

    Returns:
        A list of row dicts where the first column is ``Arm`` and each
        subsequent column is a headline metric name (verbatim from
        ``headline_metrics``). Designed for direct consumption by
        ``st.table(rows)`` or ``pd.DataFrame(rows)``.
    """
    arm_names: list[str] = manifest.get("arm_names", [])
    arms: dict[str, Any] = manifest.get("arms", {})
    headline_metrics: list[str] = manifest.get("headline_metrics", [])

    rows: list[dict[str, str]] = []
    for arm_name in arm_names:
        arm = arms.get(arm_name, {})
        arm_metrics: dict[str, float] = arm.get("metrics", {})
        arm_deltas: dict[str, list[float]] = arm.get("deltas", {})
        row: dict[str, str] = {"Arm": arm_name}
        for metric in headline_metrics:
            value = arm_metrics.get(metric, 0.0)
            if metric in arm_deltas and len(arm_deltas[metric]) == 3:
                delta, lo, hi = arm_deltas[metric]
                row[metric] = (
                    f"{value:.3f} (Δ{delta:+.3f} [{lo:.3f}, {hi:.3f}])"
                )
            else:
                # Baseline arm carries empty deltas — show "baseline" so the
                # reader knows it's the reference, not just "missing CI".
                row[metric] = f"{value:.3f} (baseline)"
        rows.append(row)
    return rows
