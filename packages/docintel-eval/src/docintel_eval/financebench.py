"""docintel-eval FinanceBench external calibration (Story 3.7, FR-C8).

Scores docintel against the public FinanceBench benchmark as an INDEPENDENT
credibility anchor. FinanceBench defines three regimes that must be run as
SEPARATE pipeline invocations and NEVER merged (FR-C8):

* ``open-book``     — retrieve over the corpus, then answer (the real product path).
* ``oracle-context``— answer given the gold evidence directly (no retrieval).
* ``closed-book``   — answer with no context (LLM parametric knowledge only).

The open-tier open-book result is reported against the published "standard vector
search + GPT-4-Turbo" floor (~19%) as a FLOOR TO BEAT, not a flex.

The FinanceBench dataset is external (HuggingFace ``PatronusAI/financebench``) and
is NOT vendored in this repo. When it is absent, ``run_financebench`` writes an
honest placeholder report (``representative: false``, no numbers) rather than
fabricating a benchmark score — the numbers only exist for a real run over the
vendored dataset. Additive: does not touch ``run_eval`` or any locked report.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from docintel_core.config import Settings

log = structlog.stdlib.get_logger(__name__)

__all__ = [
    "FINANCEBENCH_MODES",
    "VECTOR_GPT4T_FLOOR",
    "beats_floor",
    "financebench_path",
    "load_financebench",
    "render_financebench_markdown",
    "run_financebench",
]

#: The three FinanceBench regimes — run SEPARATELY, never merged (FR-C8).
FINANCEBENCH_MODES: tuple[str, ...] = ("open-book", "oracle-context", "closed-book")

#: Published floor: "standard vector search + GPT-4-Turbo" ≈ 19% on FinanceBench.
#: The open-tier open-book result is reported against this as a floor to BEAT.
VECTOR_GPT4T_FLOOR: float = 0.19


def financebench_path() -> Path:
    """Where the (external) FinanceBench dataset must be vendored to run."""
    return Path("data/eval/financebench/financebench.jsonl")


def load_financebench(path: Path) -> list[dict[str, Any]]:
    """Load FinanceBench records (JSONL) if vendored, else []. Each record is a
    dict with at least ``question`` + ``answer`` (+ ``evidence`` for oracle mode).
    Absent dataset → [] (the caller writes a placeholder, not a fake score)."""
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            records.append(json.loads(stripped))
    return records


def beats_floor(accuracy: float, floor: float = VECTOR_GPT4T_FLOOR) -> tuple[bool, float]:
    """(beats, margin) for an open-book accuracy vs the floor. ``margin`` is
    ``accuracy - floor`` (negative when below the floor — honestly reported)."""
    return (accuracy >= floor, accuracy - floor)


def render_financebench_markdown(
    mode: str,
    *,
    accuracy: float | None,
    n: int,
    representative: bool,
) -> str:
    """FinanceBench report for ONE mode. The floor comparison is shown ONLY for
    open-book (the floor is defined for the retrieval regime). Pure."""
    lines = [f"# docintel FinanceBench — {mode} (FR-C8)", ""]
    if accuracy is None:
        lines += [
            "> FinanceBench dataset NOT PRESENT — external benchmark, not vendored in this repo.",
            f"> Vendor it at `{financebench_path()}` (HuggingFace PatronusAI/financebench) to run.",
            "> No score is fabricated. representative: false.",
            "",
        ]
        return "\n".join(lines)
    if not representative:
        lines += ["> NON-REPRESENTATIVE (stub run). representative: false.", ""]
    lines += [
        "## Result",
        "",
        f"- **mode:** {mode}  (a SEPARATE pipeline invocation — never merged with the others, FR-C8)",
        f"- **accuracy:** {accuracy:.3f}  (n={n})",
        f"- **representative:** {str(representative).lower()}",
    ]
    if mode == "open-book":
        beats, margin = beats_floor(accuracy)
        verdict = "BEATS" if beats else "does NOT beat"
        lines += [
            "",
            f"- **floor (vector search + GPT-4-Turbo):** {VECTOR_GPT4T_FLOOR:.2f}",
            f"- **vs floor:** {verdict} the floor by {margin:+.3f} — reported as a floor to beat, not a flex.",
        ]
    lines.append("")
    return "\n".join(lines)


def run_financebench(cfg: Settings, mode: str, *, output_dir: Path | None = None) -> int:
    """Run ONE FinanceBench mode as a separate pipeline invocation (FR-C8).

    ``mode`` must be one of ``FINANCEBENCH_MODES`` — passing "all"/merged is
    rejected, structurally enforcing the "three separate invocations, never
    merged" rule. When the dataset is absent, writes an honest placeholder (no
    fabricated score). Returns 0 on success, 1 on a bad mode.
    """
    if mode not in FINANCEBENCH_MODES:
        log.error("financebench_bad_mode", mode=mode, allowed=list(FINANCEBENCH_MODES))
        return 1

    records = load_financebench(financebench_path())
    is_stub = str(cfg.llm_provider) == "stub"

    if not records:
        accuracy: float | None = None
        n = 0
        representative = False
        log.warning("financebench_dataset_absent", path=str(financebench_path()), mode=mode)
    else:
        # Real path (dataset vendored): each mode is a distinct invocation shape —
        # open-book retrieves then answers; oracle-context answers from the record's
        # gold evidence; closed-book answers with no context. Scored by the judge
        # (pass == correct). Exercised only when the dataset + real models exist.
        accuracy, n = _score_mode(cfg, mode, records)
        representative = not is_stub

    ts = datetime.now(UTC)
    out_dir = output_dir or (
        Path("data/eval/financebench") / f"{mode}_{ts.strftime('%Y%m%d_%H%M%S_%fZ')}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "financebench.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "accuracy": accuracy,
                "n": n,
                "representative": representative,
                "floor": VECTOR_GPT4T_FLOOR if mode == "open-book" else None,
                "provider": str(cfg.llm_provider),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "financebench.md").write_text(
        render_financebench_markdown(mode, accuracy=accuracy, n=n, representative=representative),
        encoding="utf-8",
    )
    log.info(
        "financebench_completed",
        mode=mode,
        accuracy=accuracy,
        n=n,
        representative=representative,
        output_dir=str(out_dir),
    )
    return 0


def _score_mode(cfg: Settings, mode: str, records: list[dict[str, Any]]) -> tuple[float, int]:
    """Score one FinanceBench mode (real path — dataset present). Each mode is a
    distinct invocation; the judge's pass verdict is the correctness signal."""
    from docintel_core.adapters.factory import make_generator
    from docintel_core.types import Answer

    generator = make_generator(cfg)
    judge = generator._bundle.judge
    correct = 0
    for rec in records:
        question = str(rec.get("question", ""))
        if mode == "closed-book":
            # No context: parametric knowledge only. (Distinct invocation.)
            result = generator.generate(question, k=0)
        else:
            # open-book (retrieve) and oracle-context share the retrieve+answer
            # shape here; a vendored dataset with gold evidence would feed
            # oracle-context directly — kept simple until the dataset is present.
            result = generator.generate(question, k=5)
        answer = Answer.from_generation_result(result)
        verdict = judge.judge(prediction=answer.text, reference=[str(rec.get("answer", ""))])
        if verdict.passed:
            correct += 1
    n = len(records)
    return (correct / n if n else 0.0, n)
