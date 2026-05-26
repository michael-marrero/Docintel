"""Behavioral tests for the Phase 10 eval harness (EVAL-01..EVAL-04, D-01/D-08).

Wave-0 semantics (Plan 10-01): all 13 tests are scaffolded here as
xfail(strict=True) scaffolds EXCEPT the two static .gitignore gates
(test_reports_not_gitignored, test_cache_gitignored) which already
describe true repo state and pass without any implementation.

All non-static tests defer imports into the test body so collection
never crashes — the ImportError or subprocess non-zero exit is the
expected strict-xfail trigger until Waves 1-2 land the run/validate CLI.

Requirement coverage:
  EVAL-01 — test_run_exits_zero_stub, test_eval_cli_help_fast
  EVAL-02 — test_results_json_manifest_fields, test_report_md_sections,
             test_manifest_prompt_hash_not_hardcoded
  EVAL-03 — test_reports_not_gitignored, test_cache_gitignored
  EVAL-04 — test_validate_ok_on_wellformed, test_validate_fails_missing_manifest_field,
             test_validate_fails_nan, test_validate_fails_wrong_n
  D-01    — test_rankings_use_k10
  D-08    — test_stub_representative_false
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module-level path anchors (test_eval_dataset_schema.py pattern — line 31)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_QUESTIONS_PATH = _REPO_ROOT / "data" / "eval" / "ground_truth" / "questions.jsonl"
_REPORTS_DIR = _REPO_ROOT / "data" / "eval" / "reports"
_GITIGNORE_PATH = _REPO_ROOT / ".gitignore"

# ---------------------------------------------------------------------------
# Manifest field set (EVAL-02 / D-07) — authoritative 13-field list
# ---------------------------------------------------------------------------
_REQUIRED_MANIFEST_FIELDS = frozenset(
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

# ---------------------------------------------------------------------------
# D-05 report section headers (six sections — locked)
# ---------------------------------------------------------------------------
_REPORT_SECTIONS = (
    "## Manifest",
    "## Headline Results",
    "## Latency",
    "## Per-Question-Type Breakdown",
    "## Refusal",
    "## Hero",
)

# ---------------------------------------------------------------------------
# Helper: build a minimal well-formed results.json dict for validate tests
# ---------------------------------------------------------------------------


def _make_valid_results(*, n_questions: int = 32) -> dict:
    """Return a minimal structurally-valid results dict (EVAL-04 gate input).

    All 13 manifest fields present, n_questions=32, no NaN, per_question
    has exactly 32 rows — satisfies the validate well-formedness contract.
    """
    manifest = {
        "embedder_name": "stub-embedder",
        "reranker_name": "stub-reranker",
        "generator_name": "stub-llm",
        "judge_name": "stub-judge",
        "prompt_version_hash": "65da07f1ba3e",
        "git_sha": "abc123",
        "run_timestamp_utc": "2026-05-25T07:00:00Z",
        "provider": "stub",
        "n_questions": n_questions,
        "dataset_hash": "a" * 64,
        "total_cost_usd": 0.0,
        "wall_clock_seconds": 1.0,
        "representative": False,
    }
    per_question = [
        {
            "id": f"GT-factual-{i:03d}",
            "question_type": "single_doc",
            "refused": False,
            "hit_at_1": 0,
            "hit_at_3": 0,
            "hit_at_5": 0,
            "hit_at_10": 0,
            "reciprocal_rank": 0.0,
            "citation_precision": 0.0,
            "n_citations": 0,
            "total_ms": 0.0,
            "cost_usd": 0.0,
        }
        for i in range(32)
    ]
    return {"manifest": manifest, "per_question": per_question}


# ---------------------------------------------------------------------------
# EVAL-01: docintel-eval run exits 0 in stub mode and writes report artifacts
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="run/validate CLI lands in Wave 1-2",
)
def test_run_exits_zero_stub() -> None:
    """EVAL-01: docintel-eval run exits 0 in stub mode and writes report artifacts.

    Asserts:
    - exit code is 0 (stub run completes without error)
    - a new timestamped dir is created under data/eval/reports/
    - both report.md and results.json exist inside that dir
    """
    import os

    env = {**os.environ, "DOCINTEL_LLM_PROVIDER": "stub", "HF_HUB_OFFLINE": "1"}
    before = set(_REPORTS_DIR.glob("*/")) if _REPORTS_DIR.exists() else set()

    result = subprocess.run(
        [sys.executable, "-m", "docintel_eval.cli", "run"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=env,
    )
    assert result.returncode == 0, (
        f"EVAL-01: docintel-eval run must exit 0 in stub mode. " f"stderr={result.stderr!r}"
    )

    after = set(_REPORTS_DIR.glob("*/"))
    new_dirs = after - before
    assert new_dirs, "EVAL-01: run must create a new timestamped dir under data/eval/reports/"
    report_dir = next(iter(new_dirs))
    assert (
        report_dir / "report.md"
    ).exists(), f"EVAL-01: {report_dir}/report.md must exist after run"
    assert (
        report_dir / "results.json"
    ).exists(), f"EVAL-01: {report_dir}/results.json must exist after run"


# ---------------------------------------------------------------------------
# EVAL-01: --help cold-start must complete in under 5 seconds (lazy-import gate)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="run/validate CLI lands in Wave 1-2",
)
def test_eval_cli_help_fast() -> None:
    """EVAL-01: docintel-eval --help cold-start stays under 5 seconds.

    Guards against the Pitfall 9 torch/sentence-transformers import cost.
    Lazy-import subcommand dispatch must keep --help fast even after the
    full pipeline (sentence_transformers, numpy) is installed.
    """
    import os

    env = {**os.environ, "HF_HUB_OFFLINE": "1"}
    t_start = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "docintel_eval.cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=env,
    )
    elapsed = time.perf_counter() - t_start
    assert result.returncode == 0, (
        f"EVAL-01: docintel-eval --help must exit 0, got {result.returncode}. "
        f"stderr={result.stderr!r}"
    )
    assert elapsed < 5.0, (
        f"EVAL-01: --help must complete under 5s (lazy-import gate); took {elapsed:.2f}s. "
        "Check for eager torch/sentence-transformers imports at module level."
    )


# ---------------------------------------------------------------------------
# EVAL-02: results.json manifest must have all 13 required fields
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="run/validate CLI lands in Wave 1-2",
)
def test_results_json_manifest_fields(tmp_path: Path) -> None:
    """EVAL-02: results.json manifest has all 13 required fields (D-07).

    Runs docintel-eval run, loads the output results.json, and asserts
    the manifest dict contains every key in _REQUIRED_MANIFEST_FIELDS.
    """
    import os

    env = {**os.environ, "DOCINTEL_LLM_PROVIDER": "stub", "HF_HUB_OFFLINE": "1"}
    before = set(_REPORTS_DIR.glob("*/")) if _REPORTS_DIR.exists() else set()

    result = subprocess.run(
        [sys.executable, "-m", "docintel_eval.cli", "run"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=env,
    )
    assert result.returncode == 0, f"run must exit 0; stderr={result.stderr!r}"

    after = set(_REPORTS_DIR.glob("*/"))
    new_dirs = after - before
    assert new_dirs, "run must create a report dir"
    report_dir = next(iter(new_dirs))

    data = json.loads((report_dir / "results.json").read_text(encoding="utf-8"))
    manifest = data.get("manifest", {})
    missing = _REQUIRED_MANIFEST_FIELDS - manifest.keys()
    assert not missing, (
        f"EVAL-02: results.json manifest is missing required fields: {sorted(missing)!r}. "
        f"Present: {sorted(manifest.keys())!r}"
    )


# ---------------------------------------------------------------------------
# EVAL-02: report.md must contain all six D-05 section headers
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="run/validate CLI lands in Wave 1-2",
)
def test_report_md_sections(tmp_path: Path) -> None:
    """EVAL-02: report.md contains all six D-05 section headers.

    The six locked sections are: Manifest, Headline Results, Latency,
    Per-Question-Type Breakdown, Refusal, Hero.
    """
    import os

    env = {**os.environ, "DOCINTEL_LLM_PROVIDER": "stub", "HF_HUB_OFFLINE": "1"}
    before = set(_REPORTS_DIR.glob("*/")) if _REPORTS_DIR.exists() else set()

    result = subprocess.run(
        [sys.executable, "-m", "docintel_eval.cli", "run"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=env,
    )
    assert result.returncode == 0, f"run must exit 0; stderr={result.stderr!r}"

    after = set(_REPORTS_DIR.glob("*/"))
    new_dirs = after - before
    assert new_dirs, "run must create a report dir"
    report_dir = next(iter(new_dirs))

    text = (report_dir / "report.md").read_text(encoding="utf-8")
    for header in _REPORT_SECTIONS:
        assert header in text, (
            f"EVAL-02: report.md is missing D-05 section {header!r}. "
            "All six sections are required: Manifest, Headline Results, "
            "Latency, Per-Question-Type Breakdown, Refusal, Hero."
        )


# ---------------------------------------------------------------------------
# EVAL-02: prompt_version_hash must match runtime PROMPT_VERSION_HASH
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="run/validate CLI lands in Wave 1-2",
)
def test_manifest_prompt_hash_not_hardcoded(tmp_path: Path) -> None:
    """EVAL-02: manifest prompt_version_hash matches runtime PROMPT_VERSION_HASH.

    Asserts the hash is sourced at runtime from docintel_generate.prompts,
    not hardcoded. The hash rotates with prompt edits (Phase 7 D-04).
    """
    import os

    from docintel_generate.prompts import PROMPT_VERSION_HASH  # type: ignore[import-not-found]

    env = {**os.environ, "DOCINTEL_LLM_PROVIDER": "stub", "HF_HUB_OFFLINE": "1"}
    before = set(_REPORTS_DIR.glob("*/")) if _REPORTS_DIR.exists() else set()

    result = subprocess.run(
        [sys.executable, "-m", "docintel_eval.cli", "run"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=env,
    )
    assert result.returncode == 0, f"run must exit 0; stderr={result.stderr!r}"

    after = set(_REPORTS_DIR.glob("*/"))
    new_dirs = after - before
    assert new_dirs, "run must create a report dir"
    report_dir = next(iter(new_dirs))

    data = json.loads((report_dir / "results.json").read_text(encoding="utf-8"))
    manifest_hash = data["manifest"]["prompt_version_hash"]
    assert manifest_hash == PROMPT_VERSION_HASH, (
        f"EVAL-02: manifest prompt_version_hash {manifest_hash!r} does not match "
        f"runtime PROMPT_VERSION_HASH {PROMPT_VERSION_HASH!r}. "
        "The hash must be sourced at runtime (D-07), not hardcoded."
    )


# ---------------------------------------------------------------------------
# EVAL-03: static .gitignore gates — these are PLAIN (non-xfail) tests
# because they describe already-true repo state (no implementation needed).
# ---------------------------------------------------------------------------


def test_reports_not_gitignored() -> None:
    """EVAL-03: data/eval/reports/ must NOT be in .gitignore.

    Reports are committed per EVAL-03 — recruiters and engineers browse
    them to verify real metric numbers without running a key-gated eval.
    """
    content = _GITIGNORE_PATH.read_text(encoding="utf-8")
    assert "data/eval/reports" not in content, (
        "EVAL-03: data/eval/reports/ must NOT be gitignored. "
        "Committed reports are the portfolio artifact (EVAL-03)."
    )


def test_cache_gitignored() -> None:
    """EVAL-03: data/eval/cache/ must be in .gitignore.

    The cache directory holds intermediate artifacts (embeddings, indices
    for eval runs) that are too large and ephemeral to commit.
    """
    content = _GITIGNORE_PATH.read_text(encoding="utf-8")
    assert "data/eval/cache/" in content, (
        "EVAL-03: data/eval/cache/ must be gitignored. " "Add 'data/eval/cache/' to .gitignore."
    )


# ---------------------------------------------------------------------------
# EVAL-04: validate exits 0 on a well-formed report dir (tmp_path fixture)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="run/validate CLI lands in Wave 1-2",
)
def test_validate_ok_on_wellformed(tmp_path: Path) -> None:
    """EVAL-04: docintel-eval validate exits 0 on a structurally valid report dir.

    Builds a minimal well-formed report dir (13-field manifest, 32 per_question
    rows, no NaN) in tmp_path and asserts validate returns 0.
    """
    from docintel_eval.validate import cmd_validate  # type: ignore[import-not-found]

    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "report.md").write_text("# docintel Eval Report\n", encoding="utf-8")
    (report_dir / "results.json").write_text(
        json.dumps(_make_valid_results(), indent=2) + "\n", encoding="utf-8"
    )

    exit_code = cmd_validate(report_dir)
    assert (
        exit_code == 0
    ), f"EVAL-04: cmd_validate must return 0 for a well-formed report; got {exit_code}"


# ---------------------------------------------------------------------------
# EVAL-04: validate exits 1 when a manifest field is missing
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="run/validate CLI lands in Wave 1-2",
)
def test_validate_fails_missing_manifest_field(tmp_path: Path) -> None:
    """EVAL-04: validate exits 1 when a required manifest field is absent.

    Removes 'generator_name' from an otherwise-valid results.json and
    asserts validate returns 1 (T-10-01: tampered manifest detection).
    """
    from docintel_eval.validate import cmd_validate  # type: ignore[import-not-found]

    data = _make_valid_results()
    del data["manifest"]["generator_name"]

    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "report.md").write_text("# docintel Eval Report\n", encoding="utf-8")
    (report_dir / "results.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    exit_code = cmd_validate(report_dir)
    assert exit_code == 1, (
        f"EVAL-04: cmd_validate must return 1 when 'generator_name' is missing; " f"got {exit_code}"
    )


# ---------------------------------------------------------------------------
# EVAL-04: validate exits 1 when any float value is NaN (Pitfall 7)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="run/validate CLI lands in Wave 1-2",
)
def test_validate_fails_nan(tmp_path: Path) -> None:
    """EVAL-04: validate exits 1 when results.json contains a float NaN.

    Uses Python's float('nan') injected into a per_question row. validate
    must detect it and return 1 (T-10-01: fabricated/corrupted values).
    Note: standard json.dumps serialises NaN as 'NaN' which json.loads
    reads back as float('nan') — validate's recursive _has_nan scan catches this.
    """

    # We can't write true JSON NaN via json.dumps (it's non-standard), so we
    # write the raw text with a NaN token and read it back via json.loads with
    # the parse_constant override, OR we inject via raw string substitution.
    # The simplest portable approach: write the dict as text with literal 'NaN'.
    data = _make_valid_results()
    data["per_question"][0]["total_ms"] = float("nan")

    # json.dumps writes NaN as 'NaN' (non-standard JSON, but Python allows it)
    raw = json.dumps(data, allow_nan=True, indent=2) + "\n"
    assert "NaN" in raw, "precondition: NaN must appear in raw JSON text"

    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "report.md").write_text("# docintel Eval Report\n", encoding="utf-8")
    (report_dir / "results.json").write_text(raw, encoding="utf-8")

    from docintel_eval.validate import cmd_validate  # type: ignore[import-not-found]

    exit_code = cmd_validate(report_dir)
    assert exit_code == 1, (
        f"EVAL-04: cmd_validate must return 1 when a float NaN is present; " f"got {exit_code}"
    )


# ---------------------------------------------------------------------------
# EVAL-04: validate exits 1 when n_questions != 32
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="run/validate CLI lands in Wave 1-2",
)
def test_validate_fails_wrong_n(tmp_path: Path) -> None:
    """EVAL-04: validate exits 1 when manifest.n_questions != 32.

    Substitutes n_questions=31 (one short) and asserts validate returns 1.
    This guards against partial runs producing an incomplete report that
    looks valid but covers fewer questions (T-10-01).
    """
    from docintel_eval.validate import cmd_validate  # type: ignore[import-not-found]

    data = _make_valid_results()
    data["manifest"]["n_questions"] = 31  # one short — invalid

    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "report.md").write_text("# docintel Eval Report\n", encoding="utf-8")
    (report_dir / "results.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    exit_code = cmd_validate(report_dir)
    assert exit_code == 1, (
        f"EVAL-04: cmd_validate must return 1 when n_questions=31 (not 32); " f"got {exit_code}"
    )


# ---------------------------------------------------------------------------
# D-01: Hit@K rankings must come from retriever.search(k=10), not from
# GenerationResult.retrieved_chunks (which caps at k=5 by default)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="run/validate CLI lands in Wave 1-2",
)
def test_rankings_use_k10(tmp_path: Path) -> None:
    """D-01: per_question rows carry hit_at_10 key (rankings depth >= 10).

    Asserts that at least one per_question row contains an 'hit_at_10' key,
    confirming the runner calls retriever.search(k=10) separately from
    generator.generate(k=5). GenerationResult.retrieved_chunks is capped
    at k=5 and cannot populate Hit@10 (Pitfall 1).
    """
    import os

    env = {**os.environ, "DOCINTEL_LLM_PROVIDER": "stub", "HF_HUB_OFFLINE": "1"}
    before = set(_REPORTS_DIR.glob("*/")) if _REPORTS_DIR.exists() else set()

    result = subprocess.run(
        [sys.executable, "-m", "docintel_eval.cli", "run"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=env,
    )
    assert result.returncode == 0, f"run must exit 0; stderr={result.stderr!r}"

    after = set(_REPORTS_DIR.glob("*/"))
    new_dirs = after - before
    assert new_dirs, "run must create a report dir"
    report_dir = next(iter(new_dirs))

    data = json.loads((report_dir / "results.json").read_text(encoding="utf-8"))
    per_question = data.get("per_question", [])
    assert per_question, "run must produce per_question rows"
    assert all("hit_at_10" in row for row in per_question), (
        "D-01: every per_question row must carry 'hit_at_10'. "
        "The runner must call retriever.search(k=10) separately from "
        "generator.generate(k=5) — GenerationResult.retrieved_chunks "
        "is capped at k=5 and cannot populate Hit@10 (Pitfall 1)."
    )


# ---------------------------------------------------------------------------
# D-08: stub report must carry representative=False and the STUB banner
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="run/validate CLI lands in Wave 1-2",
)
def test_stub_representative_false(tmp_path: Path) -> None:
    """D-08: stub-mode manifest has representative=False and report.md has STUB banner.

    Asserts both the JSON manifest flag and the human-visible banner text.
    Stub latency/cost are non-representative ($0, CI-runner wall-clock) and
    must be clearly labeled — 'measure, don't fake' discipline.
    """
    import os

    env = {**os.environ, "DOCINTEL_LLM_PROVIDER": "stub", "HF_HUB_OFFLINE": "1"}
    before = set(_REPORTS_DIR.glob("*/")) if _REPORTS_DIR.exists() else set()

    result = subprocess.run(
        [sys.executable, "-m", "docintel_eval.cli", "run"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=env,
    )
    assert result.returncode == 0, f"run must exit 0; stderr={result.stderr!r}"

    after = set(_REPORTS_DIR.glob("*/"))
    new_dirs = after - before
    assert new_dirs, "run must create a report dir"
    report_dir = next(iter(new_dirs))

    data = json.loads((report_dir / "results.json").read_text(encoding="utf-8"))
    assert (
        data["manifest"]["representative"] is False
    ), "D-08: manifest.representative must be False in stub mode"

    report_text = (report_dir / "report.md").read_text(encoding="utf-8")
    assert "STUB" in report_text, (
        "D-08: report.md must contain a 'STUB' non-representative banner. "
        "Stub runs are non-representative — latency & $/query are $0 / CI-runner time."
    )
