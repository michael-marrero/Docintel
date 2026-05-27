"""Behavioral tests for the Phase 11 ablation harness (ABL-01, ABL-02, D-11).

Wave-0 semantics (Plan 11-01): every behavioral test here is scaffolded as
xfail(strict=True) against the not-yet-existing ``docintel_eval.ablate`` module
and the not-yet-extended ``docintel_eval.validate`` ablation path. Each test
DEFERS its imports into the test body so pytest collection never crashes — the
``ImportError`` (or, for the CLI/output-location tests, the non-zero exit) IS the
expected strict-xfail trigger until Waves 1-2 land ``ablate``/extended-``validate``.
As each wave ships, its test flips from xfail to pass; a premature pass surfaces
as an XPASS-strict error, forcing the stale ``xfail`` marker to be removed. This
mirrors the project's established ``tests_before_code=true`` convention (Phases
9/10 Wave 0).

The SINGLE non-xfail test is the D-02 backward-compatibility reference
(``test_run_eval_arm_injection_backward_compatible``): it asserts the EXISTING
``run_eval`` already accepts ``output_dir`` (true today) so Plan 02's arm-injection
refactor — which adds an optional ``generator`` kwarg — must not break the seven
existing call-sites. It passes today and stays green; it is a true canary.

Requirement coverage (VALIDATION.md Per-Task Verification Map):
  ABL-01 — test_stub_ablate_emits_three_component_arms, test_deltas_present_and_finite,
            test_arm_construction_uses_null_adapters, test_ablate_determinism,
            test_real_ablate_includes_chunk_sweep (real + xfail)
  ABL-02 — test_report_table_shape, test_headline_sentence_per_ablation,
            test_output_location
  D-11   — test_validate_rejects_missing_arm, test_validate_nan_and_wellformed,
            test_validate_determinism_recompute
  D-02   — test_run_eval_arm_injection_backward_compatible (non-xfail reference)

Locked contract this scaffold pins (CONTEXT.md D-01..D-11, L-01..L-04):
  - Stub ``ablate`` emits exactly three component arms: baseline / no-rerank /
    dense-only, each a valid Phase-10 32-row ``results.json`` sidecar (D-03, L-03).
  - Non-baseline arms carry a paired ``(delta, lo, hi)`` triple per headline metric
    (hit_at_5, hit_at_3, reciprocal_rank), all finite (L-02; D-06).
  - Arms are built by swapping ONE null adapter into the bundle and constructing
    ``Retriever`` directly — the adapter swap is the artifact (L-01 / CD-08).
  - Two stub runs produce byte-identical deltas (seed=42 paired bootstrap) (D-11).
  - The chunk-size sweep ({300,450,600}) is real-mode / workflow_dispatch-only and
    is deselected offline by ``-m "not real"`` (D-04/D-05).
  - Output lands under ``data/eval/ablations/<ts>/`` — a tracked sibling of
    ``reports/`` (D-08).
  - The extended ``validate`` rejects a missing arm, rejects NaN/Inf deltas, accepts
    a well-formed dir, and recomputes one delta with seed=42 bit-for-bit (D-11).
"""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module-level path anchors (test_eval_harness.py pattern — lines 33-38)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_ABLATIONS_DIR = _REPO_ROOT / "data" / "eval" / "ablations"
_STUB_SAMPLE_DIR = _ABLATIONS_DIR / "stub-sample"

# ---------------------------------------------------------------------------
# Locked arm + metric vocabulary (CONTEXT.md D-03 / D-06)
# ---------------------------------------------------------------------------
_COMPONENT_ARMS = ("baseline", "no-rerank", "dense-only")
_NON_BASELINE_ARMS = ("no-rerank", "dense-only")
_HEADLINE_METRICS = ("hit_at_5", "hit_at_3", "reciprocal_rank")
_CHUNK_SWEEP_ARMS = ("chunk-300", "chunk-450", "chunk-600")
_EXPECTED_N_QUESTIONS = 32

# ---------------------------------------------------------------------------
# Reusable xfail reasons (one per implementation seam still pending)
# ---------------------------------------------------------------------------
_REASON_ABLATE = "Wave 1+: docintel_eval.ablate.run_ablations not yet implemented (Plan 02/03)"
_REASON_REPORT = "Wave 2: render_ablation_markdown / ablation-report.md not yet implemented (Plan 03)"
_REASON_VALIDATE = "Wave 2: extended ablation validate gate not yet implemented (Plan 03)"
_REASON_REAL = "Real-mode chunk-size sweep ({300,450,600}) is workflow_dispatch-only (D-04); Plan 06"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_ablate_into(tmp_path: Path) -> Path:
    """Run the stub ablation pipeline into an isolated tmp dir; return the run dir.

    Mirrors test_eval_harness.py:_run_eval_into. Calls ``run_ablations(cfg,
    output_dir=...)`` directly so the run writes under ``tmp_path`` instead of
    polluting the tracked ``data/eval/ablations/`` tree (T-11-01 mitigation).
    The deferred import is the strict-xfail trigger until ``ablate`` lands.
    """
    from docintel_core.config import Settings  # type: ignore[import-not-found]
    from docintel_eval.ablate import run_ablations  # type: ignore[import-not-found]

    cfg = Settings()
    run_dir = tmp_path / "ablations"
    exit_code = run_ablations(cfg, output_dir=run_dir)
    assert exit_code == 0, f"run_ablations must exit 0 in stub mode; got {exit_code}"
    return run_dir


def _load_ablation_manifest(run_dir: Path) -> dict:
    """Load the top-level ablation manifest JSON from a run dir.

    The comparison deltas are asserted against the JSON sidecar (not the markdown)
    so the tests stay robust to ``ablation-report.md`` layout changes. Plan 03
    Task 1 resolved the manifest shape: one top-level ``ablation-manifest.json``
    with arms as rows + an ``arm_components`` provenance map.
    """
    manifest_path = run_dir / "ablation-manifest.json"
    assert manifest_path.exists(), (
        f"ABL-01: ablate run must write a top-level ablation manifest at {manifest_path}"
    )
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _arm_deltas(manifest: dict, arm: str) -> dict:
    """Return the {metric: [delta, lo, hi]} mapping for a non-baseline arm.

    Tolerant of two reasonable manifest shapes (Plan 03 discretion, D-08):
      - manifest["arms"][arm]["deltas"][metric] -> [delta, lo, hi]
      - manifest["deltas"][arm][metric]         -> [delta, lo, hi]
    """
    arms = manifest.get("arms")
    if isinstance(arms, dict) and arm in arms and "deltas" in arms[arm]:
        return arms[arm]["deltas"]
    if isinstance(arms, list):
        for row in arms:
            if row.get("name") == arm or row.get("arm") == arm:
                return row.get("deltas", {})
    deltas = manifest.get("deltas")
    if isinstance(deltas, dict) and arm in deltas:
        return deltas[arm]
    raise AssertionError(
        f"ABL-01: could not locate deltas for arm {arm!r} in ablation manifest; keys={list(manifest)!r}"
    )


# ---------------------------------------------------------------------------
# ABL-01: stub ablate emits baseline + no-rerank + dense-only, each a valid
# 32-row results.json sidecar
# ---------------------------------------------------------------------------


def test_stub_ablate_emits_three_component_arms(tmp_path: Path) -> None:
    """ABL-01: stub ablate emits exactly the three component arms as valid sidecars.

    Asserts a per-arm sidecar dir (baseline/, no-rerank/, dense-only/) exists, each
    carrying a results.json with exactly 32 per_question rows — the L-03 cross-arm
    paired-bootstrap input. Uses output_dir= so the run does NOT pollute the tracked
    data/eval/ablations/ tree (T-11-01).
    """
    run_dir = _run_ablate_into(tmp_path)

    for arm in _COMPONENT_ARMS:
        arm_dir = run_dir / arm
        assert arm_dir.is_dir(), f"ABL-01: ablate must create a sidecar dir for arm {arm!r}"
        results_path = arm_dir / "results.json"
        assert results_path.exists(), f"ABL-01: arm {arm!r} must carry a results.json sidecar"
        data = json.loads(results_path.read_text(encoding="utf-8"))
        per_question = data.get("per_question", [])
        assert len(per_question) == _EXPECTED_N_QUESTIONS, (
            f"ABL-01: arm {arm!r} results.json must have exactly {_EXPECTED_N_QUESTIONS} "
            f"per_question rows (L-03 paired input); got {len(per_question)}"
        )


# ---------------------------------------------------------------------------
# ABL-01: each non-baseline arm carries a finite (delta, lo, hi) per headline metric
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason=_REASON_ABLATE)
def test_deltas_present_and_finite(tmp_path: Path) -> None:
    """ABL-01: each non-baseline arm has a finite (delta, lo, hi) per headline metric.

    Reads deltas from the ablation manifest JSON (robust to markdown layout) and
    asserts a (delta, lo, hi) triple per headline metric (hit_at_5, hit_at_3,
    reciprocal_rank), all finite via math.isfinite, with lo <= hi (L-02; D-06).
    """
    run_dir = _run_ablate_into(tmp_path)
    manifest = _load_ablation_manifest(run_dir)

    for arm in _NON_BASELINE_ARMS:
        deltas = _arm_deltas(manifest, arm)
        for metric in _HEADLINE_METRICS:
            assert metric in deltas, (
                f"ABL-01: arm {arm!r} must carry a delta for headline metric {metric!r}"
            )
            triple = deltas[metric]
            assert len(triple) == 3, (
                f"ABL-01: arm {arm!r} metric {metric!r} must be a (delta, lo, hi) triple; got {triple!r}"
            )
            delta, lo, hi = (float(x) for x in triple)
            assert math.isfinite(delta) and math.isfinite(lo) and math.isfinite(hi), (
                f"ABL-01: arm {arm!r} metric {metric!r} (delta, lo, hi) must all be finite "
                f"(no NaN/Inf); got {triple!r}"
            )
            assert lo <= hi, (
                f"ABL-01: arm {arm!r} metric {metric!r} CI must satisfy lo <= hi; got [{lo}, {hi}]"
            )


# ---------------------------------------------------------------------------
# ABL-01: no-rerank arm built via NullReranker swap; dense-only via NullBM25Store;
# Retriever constructed directly (CD-08); hot path branch-free (L-01)
# ---------------------------------------------------------------------------


def test_arm_construction_uses_null_adapters() -> None:
    """ABL-01: arm builders swap the null adapters and construct Retriever directly.

    Imports the two arm-builder helpers Plan 02 exposes on docintel_eval.ablate and
    asserts the no-rerank arm's bundle carries reranker.name == 'null-reranker' and
    the dense-only arm's retriever was built against an IndexStoreBundle whose
    bm25.name == 'null-bm25'. This pins L-01/CD-08: "the adapter swap IS the artifact"
    — built via Retriever(bundle, stores, cfg) directly, hot path branch-free.
    """
    from docintel_core.config import Settings  # type: ignore[import-not-found]
    from docintel_eval.ablate import (  # type: ignore[import-not-found]
        _build_dense_only_generator,
        _build_no_rerank_generator,
    )

    cfg = Settings()

    no_rerank_gen = _build_no_rerank_generator(cfg)
    assert no_rerank_gen._bundle.reranker.name == "null-reranker", (
        "ABL-01 (L-01): no-rerank arm must swap NullReranker into the bundle "
        "(reranker.name == 'null-reranker')"
    )

    dense_only_gen = _build_dense_only_generator(cfg)
    assert dense_only_gen._retriever._stores.bm25.name == "null-bm25", (
        "ABL-01 (L-01): dense-only arm must swap NullBM25Store into the IndexStoreBundle "
        "(stores.bm25.name == 'null-bm25'), constructed via Retriever(bundle, stores, cfg) (CD-08)"
    )


# ---------------------------------------------------------------------------
# ABL-01 / D-11: two stub ablate runs produce byte-identical deltas (seed=42)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason=_REASON_ABLATE)
def test_ablate_determinism(tmp_path: Path) -> None:
    """ABL-01/D-11: two stub ablate runs produce byte-identical deltas (seed=42).

    Mirrors test_eval_determinism.py — two run_ablations calls into separate tmp
    dirs must yield bit-exact equal (delta, lo, hi) tuples for every arm x headline
    metric. bootstrap_delta_ci is seeded (seed=42) and paired, so a re-run on the
    same input always reproduces the same deltas — the property the D-11 validate
    determinism-recompute gate depends on.
    """
    from docintel_core.config import Settings  # type: ignore[import-not-found]
    from docintel_eval.ablate import run_ablations  # type: ignore[import-not-found]

    cfg = Settings()
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    assert run_ablations(cfg, output_dir=dir_a) == 0
    assert run_ablations(cfg, output_dir=dir_b) == 0

    manifest_a = _load_ablation_manifest(dir_a)
    manifest_b = _load_ablation_manifest(dir_b)

    for arm in _NON_BASELINE_ARMS:
        deltas_a = _arm_deltas(manifest_a, arm)
        deltas_b = _arm_deltas(manifest_b, arm)
        for metric in _HEADLINE_METRICS:
            assert deltas_a[metric] == deltas_b[metric], (
                f"ABL-01/D-11: arm {arm!r} metric {metric!r} deltas must be byte-identical "
                f"across two seed=42 runs; got {deltas_a[metric]!r} vs {deltas_b[metric]!r}"
            )


# ---------------------------------------------------------------------------
# ABL-01 (real): workflow_dispatch run includes the chunk-300/450/600 sweep rows.
# Marked BOTH @pytest.mark.real (deselected offline by -m "not real") AND
# @pytest.mark.xfail(strict=True). Plan 06 removes the xfail marker but KEEPS the
# real marker (the EMPIRICAL-PENDING pattern: ci.yml:102 + Phase 5/6 precedent).
# ---------------------------------------------------------------------------


@pytest.mark.real
@pytest.mark.xfail(strict=True, reason=_REASON_REAL)
def test_real_ablate_includes_chunk_sweep(tmp_path: Path) -> None:
    """ABL-01 (real): the real-mode ablation run includes chunk-300/450/600 rows.

    The chunk-size sweep re-chunks -> re-embeds -> re-indexes (real pipeline cost
    offline-first stub CI avoids), so it is workflow_dispatch-only (D-04/D-05). This
    test is deselected offline by ``-m "not real"``; under a bare run the deferred
    import still fails, so strict-xfail holds. Asserts each swept-size arm dir exists
    and the comparison manifest carries each chunk-* arm.
    """
    run_dir = _run_ablate_into(tmp_path)
    manifest = _load_ablation_manifest(run_dir)

    arm_names = set(manifest.get("arms", {}))
    for arm in _CHUNK_SWEEP_ARMS:
        assert (run_dir / arm).is_dir(), (
            f"ABL-01 (real): real-mode sweep must create a sidecar dir for {arm!r}"
        )
        assert arm in arm_names, (
            f"ABL-01 (real): ablation manifest must carry the {arm!r} sweep arm "
            f"({_CHUNK_SWEEP_ARMS} required in real mode, D-05)"
        )


# ---------------------------------------------------------------------------
# ABL-02: ablation-report.md has one row per arm; each cell = value + delta + [CI];
# baseline is the reference row (delta shown as an em-dash)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason=_REASON_REPORT)
def test_report_table_shape(tmp_path: Path) -> None:
    """ABL-02: ablation-report.md renders one row per arm with value + delta + [CI].

    Asserts the comparison table carries each component arm as a row and that the
    non-baseline rows carry bracketed [lo, hi] CIs (the _fmt_ci precedent), while the
    baseline is the reference row (its delta cell is an em-dash, not a CI). Asserts on
    substrings so the test is robust to exact column ordering (D-07 discretion).
    """
    run_dir = _run_ablate_into(tmp_path)
    report_path = run_dir / "ablation-report.md"
    assert report_path.exists(), "ABL-02: ablate must write ablation-report.md"
    text = report_path.read_text(encoding="utf-8")

    for arm in _COMPONENT_ARMS:
        assert arm in text, f"ABL-02: comparison table must carry a row for arm {arm!r}"

    # Non-baseline rows carry bracketed CIs; the table has CI brackets present.
    assert "[" in text and "]" in text, (
        "ABL-02: non-baseline rows must render bracketed [lo, hi] CIs (D-07 cell shape)"
    )
    # Baseline is the reference row — its delta cell is an em-dash, not a CI.
    assert "—" in text, (
        "ABL-02: the baseline row must show '—' for its delta (it is the reference row, D-07)"
    )


# ---------------------------------------------------------------------------
# ABL-02: at least one one-line headline-finding sentence per ablation, above the table
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason=_REASON_REPORT)
def test_headline_sentence_per_ablation(tmp_path: Path) -> None:
    """ABL-02: a one-line headline-finding sentence appears above the comparison table.

    The headline sentence is the recruiter-skim payload (D-07), e.g. "Reranking adds
    +0.18 Hit@3 [95% CI 0.06, 0.31]". Asserts a headline line mentioning Hit@3 with a
    bracketed CI appears ABOVE the "## Comparison Table" section (the no-rerank
    ablation's Hit@3 ties to Phase 5's reranker canary).
    """
    run_dir = _run_ablate_into(tmp_path)
    text = (run_dir / "ablation-report.md").read_text(encoding="utf-8")

    marker = "## Comparison Table"
    head = text.split(marker, 1)[0] if marker in text else text
    headline_lines = [
        ln for ln in head.splitlines() if "Hit@3" in ln and "[" in ln and "]" in ln
    ]
    assert headline_lines, (
        "ABL-02: at least one headline-finding sentence mentioning 'Hit@3' with a bracketed "
        "CI must appear ABOVE the comparison table (the recruiter-skim payload, D-07)"
    )


# ---------------------------------------------------------------------------
# ABL-02: with no output_dir, output lands under data/eval/ablations/<ts>/
# (tracked sibling of reports/)
# ---------------------------------------------------------------------------


def test_output_location() -> None:
    """ABL-02: default output lands under data/eval/ablations/<ts>/ (D-08).

    When called with no output_dir, ablate writes to a new timestamped dir under
    data/eval/ablations/ (a tracked sibling of reports/). Snapshot-diffs _ABLATIONS_DIR
    and cleans up the created dir in a finally so the tracked tree is not littered
    (T-11-01; mirrors test_eval_harness.py:169-184).
    """
    from docintel_core.config import Settings  # type: ignore[import-not-found]
    from docintel_eval.ablate import run_ablations  # type: ignore[import-not-found]

    cfg = Settings()
    before = set(_ABLATIONS_DIR.glob("*/")) if _ABLATIONS_DIR.exists() else set()

    exit_code = run_ablations(cfg)
    new_dirs = (
        (set(_ABLATIONS_DIR.glob("*/")) - before) if _ABLATIONS_DIR.exists() else set()
    )
    try:
        assert exit_code == 0, f"ABL-02: ablate must exit 0 in stub mode; got {exit_code}"
        assert new_dirs, (
            "ABL-02: ablate with no output_dir must create a new timestamped dir under "
            "data/eval/ablations/ (D-08, sibling of reports/)"
        )
        for created in new_dirs:
            assert _ABLATIONS_DIR in created.resolve().parents or created.parent == _ABLATIONS_DIR, (
                f"ABL-02: created run dir {created} must live under {_ABLATIONS_DIR}"
            )
    finally:
        for _d in new_dirs:
            shutil.rmtree(_d, ignore_errors=True)


# ---------------------------------------------------------------------------
# D-11: extended validate rejects a missing-arm ablation report (exit 1)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason=_REASON_VALIDATE)
def test_validate_rejects_missing_arm(tmp_path: Path) -> None:
    """D-11: extended validate rejects an ablation dir missing a required arm (exit 1).

    Builds a tmp ablation dir holding only baseline + no-rerank (dense-only absent)
    and asserts the extended validate returns 1. "All arms present" is the first D-11
    well-formedness check (baseline + no-rerank + dense-only in stub).
    """
    from docintel_eval.validate import cmd_validate_ablation  # type: ignore[import-not-found]

    abl_dir = tmp_path / "ablations"
    # Only baseline + no-rerank; dense-only deliberately omitted.
    for arm in ("baseline", "no-rerank"):
        arm_dir = abl_dir / arm
        arm_dir.mkdir(parents=True)
        (arm_dir / "report.md").write_text("# arm\n", encoding="utf-8")
        (arm_dir / "results.json").write_text("{}\n", encoding="utf-8")

    exit_code = cmd_validate_ablation(abl_dir)
    assert exit_code == 1, (
        f"D-11: extended validate must return 1 when a required arm (dense-only) is "
        f"missing; got {exit_code}"
    )


# ---------------------------------------------------------------------------
# D-11: extended validate rejects NaN/Inf deltas (exit 1) and accepts a
# well-formed ablation dir (exit 0)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason=_REASON_VALIDATE)
def test_validate_nan_and_wellformed() -> None:
    """D-11: extended validate rejects NaN/Inf deltas (exit 1), accepts well-formed (exit 0).

    Two assertions: (1) injecting float('nan') into a delta payload makes validate
    return 1 (reuse the allow_nan=True raw-write trick from test_eval_harness.py:392-402,
    since json.dumps serialises NaN as the 'NaN' token that the recursive _has_nan_or_inf
    scan catches); (2) a well-formed committed stub-sample ablation dir returns 0.

    The well-formed leg validates the committed data/eval/ablations/stub-sample/ once it
    exists (Plan 03). Until then this whole test is xfail (the import of
    cmd_validate_ablation fails first).
    """
    import json as _json
    import tempfile

    from docintel_eval.validate import cmd_validate_ablation  # type: ignore[import-not-found]

    # --- Leg 1: NaN in a delta payload -> exit 1 ---
    with tempfile.TemporaryDirectory() as td:
        abl_dir = Path(td) / "ablations"
        abl_dir.mkdir(parents=True)
        manifest = {
            "arms": {
                "baseline": {"deltas": {}},
                "no-rerank": {"deltas": {"hit_at_3": [float("nan"), 0.0, 0.1]}},
                "dense-only": {"deltas": {"hit_at_3": [0.0, 0.0, 0.0]}},
            }
        }
        raw = _json.dumps(manifest, allow_nan=True, indent=2) + "\n"
        assert "NaN" in raw, "precondition: NaN must appear in raw manifest JSON text"
        (abl_dir / "ablation-manifest.json").write_text(raw, encoding="utf-8")
        nan_exit = cmd_validate_ablation(abl_dir)
        assert nan_exit == 1, (
            f"D-11: extended validate must return 1 when a delta is NaN; got {nan_exit}"
        )

    # --- Leg 2: well-formed committed stub-sample -> exit 0 ---
    ok_exit = cmd_validate_ablation(_STUB_SAMPLE_DIR)
    assert ok_exit == 0, (
        f"D-11: extended validate must return 0 on the well-formed committed stub-sample "
        f"{_STUB_SAMPLE_DIR}; got {ok_exit}"
    )


# ---------------------------------------------------------------------------
# D-11: extended validate recomputes one delta with seed=42 and matches the
# committed value bit-for-bit (the strongest determinism gate)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason=_REASON_VALIDATE)
def test_validate_determinism_recompute() -> None:
    """D-11: extended validate recomputes one arm x metric delta (seed=42) bit-for-bit.

    The extended validate re-runs bootstrap_delta_ci(seed=42) over the committed
    per_question[] columns for at least one arm x metric and asserts it reproduces the
    committed (delta, lo, hi) exactly — catching any hand-edited / drifted committed
    sidecar (L-04, integrity). Asserts validate returns 0 on the committed
    data/eval/ablations/stub-sample once it exists (Plan 03); until then the import of
    cmd_validate_ablation fails first, so this stays xfail.
    """
    from docintel_eval.validate import cmd_validate_ablation  # type: ignore[import-not-found]

    exit_code = cmd_validate_ablation(_STUB_SAMPLE_DIR)
    assert exit_code == 0, (
        f"D-11: extended validate must recompute the committed stub-sample deltas with "
        f"seed=42 and return 0 (determinism gate); got {exit_code} for {_STUB_SAMPLE_DIR}"
    )


# ---------------------------------------------------------------------------
# D-02: the run_eval arm-injection refactor is backward-compatible.
# This is the ONE non-xfail reference (a true canary): it passes today and must
# stay green through Plan 02's refactor, which adds an optional `generator` kwarg.
# ---------------------------------------------------------------------------


def test_run_eval_arm_injection_backward_compatible() -> None:
    """D-02: run_eval is importable and already accepts an output_dir keyword.

    The arm-injection mechanism (Plan 02) adds an optional ``generator`` kwarg to
    run_eval; this canary pins the EXISTING contract that the seven call-sites and the
    existing eval tests rely on — run_eval is importable and accepts ``output_dir`` as a
    keyword. It passes TODAY (non-xfail) and must stay green after Plan 02's refactor.
    The full backward-compat regression guard is the existing
    tests/test_eval_harness.py + tests/test_eval_determinism.py suite.
    """
    import inspect

    from docintel_eval.runner import run_eval

    sig = inspect.signature(run_eval)
    assert "output_dir" in sig.parameters, (
        "D-02: run_eval must accept an 'output_dir' keyword (the existing contract the "
        "seven call-sites + eval tests depend on; Plan 02's arm-injection refactor must "
        "preserve it)"
    )
    output_dir_param = sig.parameters["output_dir"]
    assert output_dir_param.kind in (
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ), "D-02: 'output_dir' must be passable as a keyword argument"
