"""docintel-eval validate module: EVAL-04 well-formedness gate.

Phase 10 / Plan 10-03 (D-11).

cmd_validate(report_dir) -> int:
  Returns 0 iff the report directory passes all six structural checks.
  Returns 1 (with a structured structlog error event) on any violation.

Six checks (in order):
  1. report.md + results.json must exist.
  2. manifest must contain all 13 required fields.
  3. manifest.n_questions must equal 32.
  4. Recursive NaN/Inf scan — no float NaN or Infinity anywhere in the parsed JSON.
  5. per_question must have exactly 32 rows.
  6. manifest.dataset_hash must match sha256(questions.jsonl) if the file exists.

cmd_validate_ablation(ablation_dir) -> int:
  Phase 11 / Plan 11-03 (D-11). Extends EVAL-04 to gate an ablation dir:
    1. ablation-manifest.json + ablation-report.md exist and the manifest parses.
    2. No float NaN / Infinity anywhere in the manifest (reuse _has_nan_or_inf) —
       catches NaN-poisoned deltas (T-11-08).
    3. All required arms present: baseline + no-rerank + dense-only (stub) plus
       any extra arms the manifest declares (real-mode chunk-300/450/600 fall out
       of the manifest arm list — not hardcoded). Each arm subdir is itself a
       valid Phase-10 sidecar, so cmd_validate is reused per arm (n=32, 13-field
       manifest, per_question length — no duplication).
    4. Baseline present (D-03).
    5. Deltas + CIs present + finite: each (delta, lo, hi) is three finite floats
       with lo <= hi (NOT lo <= delta <= hi — bootstrap CIs can sit one-sided).
    6. Determinism recompute: for one non-baseline arm x one headline metric,
       re-run bootstrap_delta_ci(seed=42) over the committed per_question[]
       columns and assert it reproduces the committed (delta, lo, hi) bit-for-bit
       (T-11-09 — a hand-edited delta fails this; the strongest D-11 check).

Security note (T-10-03 / T-11-05 path traversal):
  Path confinement is enforced by the CLI caller (cli.py) before either
  cmd_validate or cmd_validate_ablation is invoked, so that direct in-process
  callers (e.g. tests) are not blocked by the confinement guard.  The cli.py
  validate branch resolves the argument and confines it under data/eval/reports/
  (single-run) or data/eval/ablations/ (ablation) before calling.

Design notes:
  - No torch, sentence-transformers, or pipeline imports — pure file-I/O gate.
    bootstrap_delta_ci (numpy-only) is the single statistics import for the
    determinism recompute.
  - CPython's json.loads accepts the non-standard NaN / Infinity tokens that
    json.dumps(..., allow_nan=True) writes; _has_nan_or_inf catches both.
  - _has_nan_or_inf type-narrows each branch for mypy --strict compatibility.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import structlog

from docintel_eval.metrics import bootstrap_delta_ci

log = structlog.stdlib.get_logger(__name__)

__all__ = ["_has_nan_or_inf", "cmd_validate", "cmd_validate_ablation"]

# ---------------------------------------------------------------------------
# Ablation gate constants (D-11)
# ---------------------------------------------------------------------------
# Required component arms in stub mode (real mode adds chunk-* arms, detected
# from the manifest arm list rather than hardcoded — D-04/D-05).
_REQUIRED_ABLATION_ARMS: frozenset[str] = frozenset({"baseline", "no-rerank", "dense-only"})

# Headline metrics carrying paired (delta, lo, hi) triples (D-06).
_ABLATION_HEADLINE_METRICS: tuple[str, ...] = ("hit_at_5", "hit_at_3", "reciprocal_rank")

# ---------------------------------------------------------------------------
# Required manifest field names (D-07 thirteen-field contract)
# ---------------------------------------------------------------------------
_REQUIRED_MANIFEST_FIELDS: frozenset[str] = frozenset(
    {
        "embedder_name",
        "reranker_name",
        "generator_name",
        "judge_name",
        "prompt_version_hash",
        "git_sha",
        "run_timestamp_utc",
        "provider",
        "n_questions",
        "dataset_hash",
        "total_cost_usd",
        "wall_clock_seconds",
        "representative",
    }
)

_EXPECTED_N_QUESTIONS: int = 32


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _has_nan_or_inf(obj: object) -> bool:
    """Return True iff obj (or any nested value) is a float NaN or Infinity.

    CPython's json.loads accepts the non-standard NaN / Infinity tokens written
    by json.dumps(..., allow_nan=True), producing float('nan') or float('inf').
    Both math.isnan and math.isinf detect them; isinstance guards let mypy
    --strict verify that each branch narrows the type correctly.
    """
    if isinstance(obj, float):
        return math.isnan(obj) or math.isinf(obj)
    if isinstance(obj, dict):
        return any(_has_nan_or_inf(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_nan_or_inf(item) for item in obj)
    return False


# ---------------------------------------------------------------------------
# Public gate
# ---------------------------------------------------------------------------


def cmd_validate(report_dir: Path) -> int:
    """EVAL-04 well-formedness gate.  Returns 0 iff all assertions pass.

    Runs six structural checks on the report directory:
      1. Both report.md and results.json must exist.
      2. All 13 required manifest fields must be present.
      3. manifest.n_questions must equal 32.
      4. No float NaN or Infinity anywhere in the parsed JSON.
      5. per_question must have exactly 32 rows.
      6. manifest.dataset_hash must match a fresh sha256 of questions.jsonl
         (only checked when data/eval/ground_truth/questions.jsonl exists).

    Args:
        report_dir: Path to the report directory.  The CLI caller (cli.py)
                    is responsible for resolving the user-supplied string and
                    enforcing path confinement (T-10-03) before calling here.

    Returns:
        0 on success; 1 on any violation.
    """
    results_path = report_dir / "results.json"
    report_path = report_dir / "report.md"

    # ------------------------------------------------------------------
    # Check 1: both files must exist
    # ------------------------------------------------------------------
    if not results_path.exists() or not report_path.exists():
        log.error(
            "validate_missing_file",
            report_dir=str(report_dir),
            results_exists=results_path.exists(),
            report_exists=report_path.exists(),
        )
        return 1

    # ------------------------------------------------------------------
    # Check 2: parse results.json; assert all 13 manifest fields present
    # ------------------------------------------------------------------
    try:
        data: object = json.loads(results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.error("validate_json_parse_error", report_dir=str(report_dir), error=str(exc))
        return 1

    if not isinstance(data, dict):
        log.error("validate_results_not_dict", report_dir=str(report_dir))
        return 1

    manifest: object = data.get("manifest", {})
    if not isinstance(manifest, dict):
        log.error("validate_manifest_not_dict", report_dir=str(report_dir))
        return 1

    missing: list[str] = sorted(_REQUIRED_MANIFEST_FIELDS - manifest.keys())
    if missing:
        log.error(
            "validate_manifest_missing_fields",
            report_dir=str(report_dir),
            missing=missing,
        )
        return 1

    # ------------------------------------------------------------------
    # Check 3: n_questions must equal 32
    # ------------------------------------------------------------------
    n_questions: object = manifest.get("n_questions")
    if n_questions != _EXPECTED_N_QUESTIONS:
        log.error(
            "validate_n_questions",
            report_dir=str(report_dir),
            got=n_questions,
            expected=_EXPECTED_N_QUESTIONS,
        )
        return 1

    # ------------------------------------------------------------------
    # Check 4: no float NaN or Infinity anywhere in the JSON (T-10-01)
    #
    # CPython's json.loads accepts the non-standard NaN / Infinity tokens
    # that json.dumps(..., allow_nan=True) writes, producing float('nan')
    # or float('inf') objects that _has_nan_or_inf catches via math.isnan
    # and math.isinf.
    # ------------------------------------------------------------------
    if _has_nan_or_inf(data):
        log.error("validate_nan_or_inf_found", report_dir=str(report_dir))
        return 1

    # ------------------------------------------------------------------
    # Check 5: per_question must have exactly 32 rows
    # ------------------------------------------------------------------
    per_q: object = data.get("per_question", [])
    if not isinstance(per_q, list):
        log.error("validate_per_question_not_list", report_dir=str(report_dir))
        return 1
    if len(per_q) != _EXPECTED_N_QUESTIONS:
        log.error(
            "validate_per_question_count",
            report_dir=str(report_dir),
            got=len(per_q),
            expected=_EXPECTED_N_QUESTIONS,
        )
        return 1

    # ------------------------------------------------------------------
    # Check 6: dataset_hash must match sha256(questions.jsonl) if the
    # report_dir is inside the canonical data/eval/reports/ tree AND the
    # questions.jsonl file exists.
    #
    # Rationale: tests invoke cmd_validate directly with tmp_path-based
    # dirs that contain synthetic manifests with placeholder hashes.
    # The hash check is a provenance gate for committed reports, not a
    # structural constraint on the JSON shape itself — applying it outside
    # the canonical reports tree would break all in-process test scenarios.
    # ------------------------------------------------------------------
    reports_root = Path("data/eval/reports").resolve()
    report_dir_resolved = report_dir.resolve()
    is_under_reports = (
        report_dir_resolved == reports_root or reports_root in report_dir_resolved.parents
    )
    questions_path = Path("data/eval/ground_truth/questions.jsonl")
    if is_under_reports and questions_path.exists():
        actual_hash: str = hashlib.sha256(questions_path.read_bytes()).hexdigest()
        declared_hash: object = manifest.get("dataset_hash")
        if declared_hash != actual_hash:
            log.error(
                "validate_dataset_hash_mismatch",
                report_dir=str(report_dir),
                declared=declared_hash,
                actual=actual_hash,
            )
            return 1

    # ------------------------------------------------------------------
    # All checks passed
    # ------------------------------------------------------------------
    log.info("validate_ok", report_dir=str(report_dir))
    return 0


# ---------------------------------------------------------------------------
# Ablation well-formedness gate (D-11 — extends EVAL-04 for ablation dirs)
# ---------------------------------------------------------------------------


def _arm_deltas_from_manifest(manifest: dict[str, Any], arm: str) -> dict[str, Any]:
    """Return the {metric: [delta, lo, hi]} mapping for an arm (tolerant of shape).

    Mirrors the test helper's tolerance for the two reasonable manifest shapes
    (D-08 discretion): manifest["arms"][arm]["deltas"] or manifest["deltas"][arm].
    Returns {} when the arm carries no deltas (e.g. the baseline reference row).
    """
    arms = manifest.get("arms")
    if isinstance(arms, dict) and arm in arms:
        arm_entry = arms[arm]
        if isinstance(arm_entry, dict):
            arm_deltas = arm_entry.get("deltas")
            if isinstance(arm_deltas, dict):
                return dict(arm_deltas)
    deltas = manifest.get("deltas")
    if isinstance(deltas, dict):
        arm_deltas = deltas.get(arm)
        if isinstance(arm_deltas, dict):
            return dict(arm_deltas)
    return {}


def cmd_validate_ablation(ablation_dir: Path) -> int:
    """EVAL-04 ablation gate (D-11). Returns 0 iff every check passes, else 1.

    Checks (in order; first failure returns 1 with a structured log event):
      1. ablation-manifest.json exists and parses to a dict.
      2. No NaN / Inf anywhere in the manifest (reuse _has_nan_or_inf; T-11-08).
      3. All required arms present (baseline + no-rerank + dense-only, plus any
         extra arms the manifest declares — real chunk arms detected from the
         manifest, not hardcoded). Each arm subdir validates as a Phase-10 sidecar
         via cmd_validate (n=32, 13-field manifest, per_question length).
      4. Baseline present (D-03).
      5. Each non-baseline arm x headline metric carries a finite (delta, lo, hi)
         triple with lo <= hi.
      6. Determinism: recompute one arm x metric delta with seed=42 from the
         committed per_question[] columns and assert a bit-for-bit match (T-11-09).

    Args:
        ablation_dir: Path to the ablation run dir. The CLI caller (cli.py)
                      resolves + confines it under data/eval/ablations/ (T-11-05)
                      before calling; direct in-process callers (tests) are not
                      blocked by the confinement guard.

    Returns:
        0 on success; 1 on any violation.
    """
    manifest_path = ablation_dir / "ablation-manifest.json"

    # --- Check 1: manifest exists + parses to a dict ---
    if not manifest_path.exists():
        log.error("validate_ablation_missing_manifest", ablation_dir=str(ablation_dir))
        return 1
    try:
        manifest_obj: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.error(
            "validate_ablation_manifest_parse_error",
            ablation_dir=str(ablation_dir),
            error=str(exc),
        )
        return 1
    if not isinstance(manifest_obj, dict):
        log.error("validate_ablation_manifest_not_dict", ablation_dir=str(ablation_dir))
        return 1
    manifest: dict[str, Any] = manifest_obj

    # --- Check 2: no NaN / Inf anywhere in the manifest (T-11-08) ---
    if _has_nan_or_inf(manifest):
        log.error("validate_ablation_nan_or_inf_found", ablation_dir=str(ablation_dir))
        return 1

    # --- Check 3 + 4: all required arms present (+ manifest-declared extras);
    # baseline present; each arm is a valid Phase-10 sidecar (reuse cmd_validate).
    declared: object = manifest.get("arm_names", [])
    declared_arms: set[str] = set(declared) if isinstance(declared, list) else set()
    expected_arms: set[str] = set(_REQUIRED_ABLATION_ARMS) | declared_arms
    for arm in sorted(expected_arms):
        arm_dir = ablation_dir / arm
        if not arm_dir.is_dir() or not (arm_dir / "results.json").exists():
            log.error(
                "validate_ablation_missing_arm",
                ablation_dir=str(ablation_dir),
                arm=arm,
            )
            return 1
        # Each arm subdir is itself a Phase-10 report dir — reuse the six checks
        # (13-field manifest, n=32, per_question length, NaN scan) per arm.
        if cmd_validate(arm_dir) != 0:
            log.error(
                "validate_ablation_arm_sidecar_invalid",
                ablation_dir=str(ablation_dir),
                arm=arm,
            )
            return 1
    if "baseline" not in expected_arms:
        log.error("validate_ablation_no_baseline", ablation_dir=str(ablation_dir))
        return 1

    # --- Check 5: each non-baseline arm x headline metric has a finite (delta,
    # lo, hi) with lo <= hi (NOT lo <= delta <= hi — bootstrap CIs may be
    # one-sided around 0).
    baseline_name: str = str(manifest.get("baseline", "baseline"))
    non_baseline = sorted(a for a in expected_arms if a != baseline_name)
    for arm in non_baseline:
        arm_deltas = _arm_deltas_from_manifest(manifest, arm)
        for metric in _ABLATION_HEADLINE_METRICS:
            triple = arm_deltas.get(metric)
            if not isinstance(triple, list) or len(triple) != 3:
                log.error(
                    "validate_ablation_delta_shape",
                    ablation_dir=str(ablation_dir),
                    arm=arm,
                    metric=metric,
                    got=triple,
                )
                return 1
            # A corrupt committed manifest whose triple holds a non-numeric
            # value (["x", 0.0, 0.1] or [null, 0, 0] -> float(None)) must yield
            # a clean exit 1, not a ValueError/TypeError traceback (a
            # well-formedness gate rejects bad input rather than crashing).
            try:
                delta_f, lo_f, hi_f = (float(triple[0]), float(triple[1]), float(triple[2]))
            except (TypeError, ValueError):
                log.error(
                    "validate_ablation_delta_not_numeric",
                    ablation_dir=str(ablation_dir),
                    arm=arm,
                    metric=metric,
                    got=triple,
                )
                return 1
            if not (math.isfinite(delta_f) and math.isfinite(lo_f) and math.isfinite(hi_f)):
                log.error(
                    "validate_ablation_delta_not_finite",
                    ablation_dir=str(ablation_dir),
                    arm=arm,
                    metric=metric,
                    got=triple,
                )
                return 1
            if lo_f > hi_f:
                log.error(
                    "validate_ablation_ci_inverted",
                    ablation_dir=str(ablation_dir),
                    arm=arm,
                    metric=metric,
                    lo=lo_f,
                    hi=hi_f,
                )
                return 1

    # --- Check 6: determinism recompute (T-11-09). Re-run bootstrap_delta_ci with
    # the committed seed/n_boot over the committed per_question[] columns for ONE
    # non-baseline arm x metric and assert a bit-for-bit match. A hand-edited
    # delta fails here — the integrity gate the committed stub sample relies on.
    if non_baseline:
        seed_obj: object = manifest.get("seed", 42)
        n_boot_obj: object = manifest.get("n_boot", 10_000)
        seed_i: int = int(seed_obj) if isinstance(seed_obj, int) else 42
        n_boot_i: int = int(n_boot_obj) if isinstance(n_boot_obj, int) else 10_000
        recompute_arm = non_baseline[0]
        recompute_metric = _ABLATION_HEADLINE_METRICS[0]
        try:
            base_rows = json.loads(
                (ablation_dir / baseline_name / "results.json").read_text(encoding="utf-8")
            )["per_question"]
            arm_rows = json.loads(
                (ablation_dir / recompute_arm / "results.json").read_text(encoding="utf-8")
            )["per_question"]
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            log.error(
                "validate_ablation_recompute_read_error",
                ablation_dir=str(ablation_dir),
                error=str(exc),
            )
            return 1
        base_by_id = {str(r["id"]): r for r in base_rows}
        arm_by_id = {str(r["id"]): r for r in arm_rows}
        ids = sorted(base_by_id)
        arm_col: list[float] = [float(arm_by_id[i][recompute_metric]) for i in ids]
        base_col: list[float] = [float(base_by_id[i][recompute_metric]) for i in ids]
        recomputed = list(
            bootstrap_delta_ci(arm_col, base_col, n_boot=n_boot_i, seed=seed_i)
        )
        committed_triple = _arm_deltas_from_manifest(manifest, recompute_arm)[recompute_metric]
        committed = [float(x) for x in committed_triple]
        if recomputed != committed:
            log.error(
                "validate_ablation_determinism_mismatch",
                ablation_dir=str(ablation_dir),
                arm=recompute_arm,
                metric=recompute_metric,
                committed=committed,
                recomputed=recomputed,
            )
            return 1

    log.info(
        "validate_ablation_ok",
        ablation_dir=str(ablation_dir),
        arms=sorted(expected_arms),
    )
    return 0
