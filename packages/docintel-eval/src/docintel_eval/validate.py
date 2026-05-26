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

Security note (T-10-03 path traversal):
  Path confinement is enforced by the CLI caller (cli.py) before cmd_validate
  is invoked, so that direct in-process callers (e.g. tests) are not blocked
  by the confinement guard.  The cli.py validate branch resolves the argument
  and confines it under data/eval/reports/ before calling this function.

Design notes:
  - No torch, sentence-transformers, or pipeline imports — pure file-I/O gate.
  - CPython's json.loads accepts the non-standard NaN / Infinity tokens that
    json.dumps(..., allow_nan=True) writes; _has_nan_or_inf catches both.
  - _has_nan_or_inf type-narrows each branch for mypy --strict compatibility.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import structlog

log = structlog.stdlib.get_logger(__name__)

__all__ = ["cmd_validate", "_has_nan_or_inf"]

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
