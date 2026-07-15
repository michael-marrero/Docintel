"""docintel-eval confidence calibration (Story 3.6, FR-C5).

Proves whether the runtime confidence signal (``Answer.confidence`` — the LLM's
categorical high/medium/low self-report, surfaced in the UI by Story 2.7)
actually predicts correctness. Runs the generator over the frozen ground-truth
set, pairs each non-refused answer's confidence with a correctness label (the
faithfulness judge's pass verdict — the same grounding signal MET-03 uses), and
computes Brier score, ECE, and a reliability curve via the pure metrics in
``metrics.py``.

Additive + non-invasive: this is a SEPARATE ``docintel-eval calibrate`` command.
It does NOT modify ``run_eval`` or its committed report bytes (the locked
stub-sample / baseline contract stays intact). Stub mode is honestly
non-representative — the stub judge fails every answer, so ``correct`` is
all-False; the result carries ``representative: false`` (AD-11).

AD-11: the calibration report is the SOLE basis on which the product may claim
the FR-B6 confidence signal is "calibrated". Until a representative run exists,
no such claim is licensed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from docintel_core.adapters.factory import make_generator
from docintel_core.config import Settings

from docintel_eval.dataset import load_questions
from docintel_eval.metrics import CalibrationResult, _is_refusal, compute_calibration

if TYPE_CHECKING:
    from docintel_generate.generator import Generator

log = structlog.stdlib.get_logger(__name__)

__all__ = ["render_calibration_json", "render_calibration_markdown", "run_calibration"]

_EVAL_SET_PATH = Path("data/eval/ground_truth/eval_set.jsonl")


def run_calibration(
    cfg: Settings,
    *,
    output_dir: Path | None = None,
    generator: Generator | None = None,
) -> int:
    """Generate answers over the GT set, calibrate confidence vs correctness,
    write calibration.json + calibration.md. Returns 0 on success.

    Correctness = the faithfulness judge's ``passed`` verdict over cited chunk
    texts (D-02; the MET-03 signal), evaluated only on non-refused answers (a
    refusal is not a graded confidence claim).
    """
    from docintel_core.types import Answer

    if generator is None:
        generator = make_generator(cfg)
    judge = generator._bundle.judge

    records = load_questions(_EVAL_SET_PATH)
    confidences: list[str] = []
    correct: list[bool] = []
    for record in records:
        result = generator.generate(record.question, k=5)
        answer = Answer.from_generation_result(result)
        if _is_refusal(answer):
            continue  # a refusal carries no graded confidence claim
        reference = [cit.text for cit in answer.citations]
        verdict = judge.judge(prediction=answer.text, reference=reference)
        confidences.append(answer.confidence)
        correct.append(bool(verdict.passed))

    is_representative = str(cfg.llm_provider) != "stub"
    calibration = compute_calibration(confidences, correct, representative=is_representative)

    ts = datetime.now(UTC)
    if output_dir is not None:
        out_dir = output_dir
    else:
        out_dir = Path("data/eval/calibration") / ts.strftime("%Y%m%d_%H%M%S_%fZ")
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "calibration.json").write_text(
        render_calibration_json(calibration, provider=str(cfg.llm_provider)), encoding="utf-8"
    )
    (out_dir / "calibration.md").write_text(
        render_calibration_markdown(calibration, provider=str(cfg.llm_provider)), encoding="utf-8"
    )

    log.info(
        "calibration_run_completed",
        n_graded=calibration.n,
        brier=calibration.brier,
        ece=calibration.ece,
        representative=calibration.representative,
        output_dir=str(out_dir),
    )
    return 0


def render_calibration_json(calibration: CalibrationResult, *, provider: str) -> str:
    """Deterministic calibration.json (sort_keys — byte-stable for equal input)."""
    payload: dict[str, Any] = {
        "provider": provider,
        "brier": calibration.brier,
        "ece": calibration.ece,
        "n": calibration.n,
        "n_bins": calibration.n_bins,
        "reliability": calibration.reliability,
        "representative": calibration.representative,
        "confidence_prob_map": calibration.confidence_prob_map,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_calibration_markdown(calibration: CalibrationResult, *, provider: str) -> str:
    """Human-readable calibration report (FR-C5)."""
    lines: list[str] = ["# docintel Confidence Calibration (FR-C5)", ""]
    if not calibration.representative:
        lines += [
            "> NON-REPRESENTATIVE — stub mode. The stub judge fails every answer, so "
            "correctness is degenerate. representative: false.",
            "> Run with DOCINTEL_LLM_PROVIDER=real for a publishable calibration.",
            "",
        ]
    lines += [
        "## Headline",
        "",
        f"- **Brier score:** {calibration.brier:.4f}  _(0 = perfect; lower is better)_",
        f"- **ECE:** {calibration.ece:.4f}  _(expected calibration error; 0 = perfectly calibrated)_",
        f"- **n graded answers:** {calibration.n}",
        f"- **representative:** {str(calibration.representative).lower()}",
        "",
        "## Confidence → probability prior",
        "",
        "The runtime signal is categorical (high/medium/low); the declared prior mapped for scoring:",
        "",
    ]
    for label, prob in calibration.confidence_prob_map.items():
        lines.append(f"- `{label}` → {prob}")
    lines += ["", "## Reliability curve", ""]
    if calibration.reliability:
        lines.append("| bin | mean confidence | accuracy | n |")
        lines.append("|-----|-----------------|----------|---|")
        for b in calibration.reliability:
            lines.append(
                f"| [{b['bin_lo']:.1f}, {b['bin_hi']:.1f}] | "
                f"{b['mean_confidence']:.3f} | {b['accuracy']:.3f} | {int(b['count'])} |"
            )
    else:
        lines.append("_No graded answers — reliability curve is empty._")
    lines += [
        "",
        "## Claim boundary (AD-11)",
        "",
        "This report is the SOLE basis on which the product may call the FR-B6 confidence "
        "signal 'calibrated'. A `representative: false` run licenses NO such claim.",
        "",
    ]
    return "\n".join(lines)
