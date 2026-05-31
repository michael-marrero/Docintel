"""docintel-eval runner module: orchestration loop, manifest assembly, report write.

Phase 10 eval harness orchestration (EVAL-01 / EVAL-02 / D-01..D-08).

run_eval(cfg, *, k, k_gen, output_dir) -> int:
  - Loads all 32 ground-truth questions via load_questions().
  - Calls retriever.search(question, k=k) per question for Hit@K rankings (D-01).
  - Calls generator.generate(question, k=k_gen) wrapped in perf_counter for timing.
  - Computes the 5 Phase-9 metric results (no new math — import and call).
  - Assembles the 13-field manifest (D-07).
  - Writes report.md + results.json to data/eval/reports/<UTC-timestamp>/ (D-04).
  - Returns 0 on success.

Pitfall 2: reuse generator._retriever — do NOT call make_retriever again.
Pitfall 3: lazy-import PROMPT_VERSION_HASH inside run_eval (not at module top).
"""

from __future__ import annotations

import hashlib
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog
from docintel_core.adapters.factory import make_generator
from docintel_core.config import Settings
from docintel_core.trace import TraceSpanCollector

if TYPE_CHECKING:
    # Phase 11 arm injection (D-02): the optional `generator` parameter is typed
    # via this TYPE_CHECKING-only import so no heavy docintel-generate import is
    # hoisted to module top (mirrors the lazy-import discipline already used for
    # PROMPT_VERSION_HASH + render functions inside run_eval). At runtime the
    # injected generator is built by the caller (ablate.py); when absent, run_eval
    # builds its own via make_generator(cfg) exactly as before.
    from docintel_generate.generator import Generator

from docintel_eval.dataset import EvalRecord, load_questions
from docintel_eval.metrics import (
    QueryTimingRecord,
    _is_refusal,
    compute_citation_accuracy,
    compute_faithfulness,
    compute_latency_stats,
    compute_refusal_matrix,
    compute_retrieval_metrics,
    hit_at_k,
    reciprocal_rank,
    wilson_ci,
)

log = structlog.stdlib.get_logger(__name__)

__all__ = ["run_eval"]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


# Deterministic stub-mode provenance sentinels (D-08 / D-11 / D-12). In stub mode
# the run is non-representative and the committed stub-sample artifacts must be
# byte-reproducible: a live git SHA (which carries "-dirty" on any working-tree
# change AND changes on every commit) and a wall-clock timestamp / duration are
# run-dependent, so two stub runs would not be byte-identical and the committed
# sample would attest to an untracked source commit. These sentinels are zeroed
# the same way total_ms is zeroed in stub mode (runner Step 4) so two stub runs
# produce identical manifest bytes end-to-end. Real mode records the true SHA /
# timestamp / wall-clock as before.
_STUB_GIT_SHA: str = "stub-deterministic"
_STUB_RUN_TIMESTAMP_UTC: str = "1970-01-01T00:00:00Z"
_STUB_WALL_CLOCK_SECONDS: float = 0.0


def _git_sha() -> str:
    """Return HEAD SHA with -dirty suffix if working tree has uncommitted changes."""
    sha_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    sha: str = sha_result.stdout.strip() or "unknown"
    dirty_result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if dirty_result.stdout.strip():
        sha = f"{sha}-dirty"
    return sha


def _dataset_hash(questions_path: Path) -> str:
    """SHA-256 of the raw questions JSONL bytes (deterministic provenance hash)."""
    return hashlib.sha256(questions_path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Main orchestration entry point
# ---------------------------------------------------------------------------


def run_eval(
    cfg: Settings,
    *,
    k: int = 10,
    k_gen: int = 5,
    output_dir: Path | None = None,
    generator: Generator | None = None,
) -> int:
    """Execute the full eval pipeline over all 32 ground-truth questions.

    Imports PROMPT_VERSION_HASH and render functions lazily inside the function
    body (Pitfall 3 — keeps cli --help fast by avoiding torch/generate imports
    at module top).

    Args:
        cfg:        Settings instance (FND-11 single env-read site).
        k:          Retrieval depth for Hit@K rankings (default 10; D-01).
        k_gen:      Generation context window — chunks passed to LLM (default 5).
        output_dir: Override output directory. When None, uses
                    data/eval/reports/<YYYYMMDD_HHMMSSZ>/ (timestamped).
        generator:  Optional pre-built Generator (Phase 11 arm injection, D-02).
                    When None (the default / every Phase 10 call-site), run_eval
                    builds its own via make_generator(cfg) exactly as before.
                    When provided — the ablation arms inject a generator whose
                    bundle/stores carry a swapped null adapter — run_eval reuses
                    it (and its warm generator._retriever, Pitfall 2) so the
                    measurement path is byte-identical across arms; the only
                    difference between arms is the injected component.

    Returns:
        0 on success.
    """
    # Lazy imports (Pitfall 3 — keep cli --help fast)
    from docintel_generate.prompts import PROMPT_VERSION_HASH

    from docintel_eval.report import render_markdown, render_results_json

    # ------------------------------------------------------------------
    # Step 1: start timer + timestamp
    # ------------------------------------------------------------------
    wall_start: float = time.perf_counter()
    ts: datetime = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Step 2: build generator once; reuse _retriever (Pitfall 2)
    # ------------------------------------------------------------------
    # D-02 arm injection: when no generator was injected (every Phase 10
    # call-site), build one here exactly as before. When an arm generator IS
    # injected (Phase 11 ablate), skip construction and reuse it — the
    # downstream loop, the six metric calls, the manifest assembly that reads
    # generator._bundle.*.name, and the artifact write are then automatically
    # identical per arm.
    if generator is None:
        generator = make_generator(cfg)
    retriever = generator._retriever  # reuse warm retriever (Pitfall 2 — never make_retriever again)

    # ------------------------------------------------------------------
    # Step 3: load ground-truth questions
    # ------------------------------------------------------------------
    eval_set_path = Path("data/eval/ground_truth/eval_set.jsonl")
    records: list[EvalRecord] = load_questions(eval_set_path)

    # ------------------------------------------------------------------
    # Step 4: per-question loop
    # ------------------------------------------------------------------
    from docintel_core.types import Answer  # lazy — avoid hoisting

    answers: list[Answer] = []
    rankings: dict[str, list[str]] = {}
    timings: list[QueryTimingRecord] = []

    # Hero stash (GT-comparative-001)
    hero_result_text: str = ""
    hero_ranking: list[str] = []
    hero_record: EvalRecord | None = None

    # Per-question citation accuracy accumulators
    citation_hits_total: int = 0
    citation_n_total: int = 0

    # Per-question raw rows for results.json + per-type breakdown
    per_question_rows: list[dict[str, Any]] = []

    for record in records:
        # D-02 + A3: bind a per-question trace_id (fresh UUID4) and write ONE
        # consolidated trace_completed record per question to cfg.trace_dir. This
        # is the only path exercising retriever+generator pre-Phase-13, so the
        # existing retriever_search_completed / generator_completed lines carry a
        # trace_id (via merge_contextvars), and the Phase 13 Traces tab gets real
        # stub-mode demo data before POST /query exists. The collector is purely
        # additive — every existing measurement (perf_counter, QueryTimingRecord,
        # the metric accumulators) is unchanged, so eval reports stay byte-identical.
        with TraceSpanCollector(cfg.trace_dir, source="eval") as tc:
            # D-01: call retriever.search separately at k>=10 for ranking metrics
            with tc.span("retrieval"):
                retrieved_for_metrics = retriever.search(record.question, k=k)
            rankings[record.id] = [c.chunk_id for c in retrieved_for_metrics]

            # Wrap generator.generate() in perf_counter (Option A — RESEARCH verdict)
            t0: float = time.perf_counter()
            with tc.span("generation"):
                result = generator.generate(record.question, k=k_gen)
            _elapsed_ms: float = (time.perf_counter() - t0) * 1000
            # D-08 / D-12: stub-mode latency is non-representative and
            # non-deterministic (wall clock varies per run). Zero it out in stub
            # mode so two successive stub runs produce bit-exact per_question rows.
            total_ms: float = 0.0 if str(cfg.llm_provider) == "stub" else _elapsed_ms

            answer = Answer.from_generation_result(result)
            answers.append(answer)

            cost_usd_val: float = (
                result.completion.cost_usd if result.completion is not None else 0.0
            )
            model_name: str = (
                result.completion.model if result.completion is not None else "stub-refusal"
            )

            # D-18 dual-signal refusal: consistent with compute_refusal_matrix
            refused_flag: bool = _is_refusal(answer)

            # A3 / T-12-07: attach metadata-only top-level fields to the trace
            # record — REUSE the values already computed above (never re-derive
            # the answer, never re-measure, never the completion object itself).
            tc.add_fields(
                question_id=record.id,
                cost_usd=cost_usd_val,
                model=model_name,
                refused=refused_flag,
            )

            timings.append(
                QueryTimingRecord(
                    question_id=record.id,
                    total_ms=total_ms,
                    cost_usd=cost_usd_val,
                    model=model_name,
                    refused=refused_flag,
                    retrieval_ms=None,  # Phase 12 wires sub-stage resolution
                    generation_ms=None,
                )
            )

            # Stash hero (GT-comparative-001) for Section 6 spotlight
            if record.id == "GT-comparative-001":
                hero_record = record
                hero_result_text = answer.text
                hero_ranking = rankings[record.id]

            # Per-question citation accuracy (Pitfall 5 — call per question)
            gold_set: set[str] = set(record.gold_passage_ids)
            if not refused_flag:
                cited_ids: list[str] = [cit.chunk_id for cit in answer.citations]
                cit_result = compute_citation_accuracy(
                    cited_ids, set(record.expected_citation_ids)
                )
                citation_hits_total += sum(
                    1 for cid in cited_ids if cid in set(record.expected_citation_ids)
                )
                citation_n_total += len(cited_ids)
                per_citation_precision: float = cit_result.precision
                per_n_citations: int = cit_result.n_citations
            else:
                per_citation_precision = 0.0
                per_n_citations = 0

            # Per-question hit@k values (from the k=10 ranking)
            ranked = rankings[record.id]
            if gold_set:
                q_hit1: int = hit_at_k(ranked, gold_set, 1)
                q_hit3: int = hit_at_k(ranked, gold_set, 3)
                q_hit5: int = hit_at_k(ranked, gold_set, 5)
                q_hit10: int = hit_at_k(ranked, gold_set, 10)
                q_rr: float = reciprocal_rank(ranked, gold_set)
            else:
                # Refusal records have no gold — report 0 for all
                q_hit1 = q_hit3 = q_hit5 = q_hit10 = 0
                q_rr = 0.0

            per_question_rows.append(
                {
                    "id": record.id,
                    "question_type": record.question_type,
                    "refused": refused_flag,
                    "hit_at_1": q_hit1,
                    "hit_at_3": q_hit3,
                    "hit_at_5": q_hit5,
                    "hit_at_10": q_hit10,
                    "reciprocal_rank": q_rr,
                    "citation_precision": per_citation_precision,
                    "n_citations": per_n_citations,
                    "total_ms": total_ms,
                    "cost_usd": cost_usd_val,
                }
            )

    # ------------------------------------------------------------------
    # Step 5: compute aggregate metrics
    # ------------------------------------------------------------------
    retrieval_result = compute_retrieval_metrics(
        cast(list[object], records), rankings, k_multidoc=k
    )
    faithfulness_result = compute_faithfulness(answers, generator._bundle.judge)
    refusal_result = compute_refusal_matrix(cast(list[object], records), answers)
    latency_result = compute_latency_stats(timings)

    # Headline citation precision: total hits / total citations across answered qs
    citation_headline: float = (
        citation_hits_total / citation_n_total if citation_n_total > 0 else 0.0
    )
    # ------------------------------------------------------------------
    # Step 6: build per-type breakdown rows for render_markdown
    # ------------------------------------------------------------------
    per_type_rows: list[dict[str, Any]] = _build_per_type_rows(
        records, per_question_rows, str(cfg.llm_provider) == "stub"
    )

    # ------------------------------------------------------------------
    # Step 7: assemble the 13-field manifest (D-07)
    # ------------------------------------------------------------------
    # D-08 / D-11 / D-12: in stub mode the git SHA, run timestamp and wall-clock
    # duration are run-dependent (the SHA additionally carries "-dirty" on any
    # working-tree change), so they are replaced with fixed sentinels — exactly
    # how total_ms is zeroed in stub mode (Step 4) — making two stub runs
    # byte-identical and the committed stub-sample artifact reproducible. Real
    # mode records the true values.
    is_stub: bool = str(cfg.llm_provider) == "stub"
    wall_clock_seconds: float = (
        _STUB_WALL_CLOCK_SECONDS if is_stub else time.perf_counter() - wall_start
    )
    total_cost_usd: float = sum(t.cost_usd for t in timings)
    is_representative: bool = any(t.cost_usd > 0.0 for t in timings)

    manifest: dict[str, Any] = {
        "embedder_name": generator._bundle.embedder.name,
        "reranker_name": generator._bundle.reranker.name,
        "generator_name": generator._bundle.llm.name,
        "judge_name": generator._bundle.judge.name,
        "prompt_version_hash": PROMPT_VERSION_HASH,
        "git_sha": _STUB_GIT_SHA if is_stub else _git_sha(),
        "run_timestamp_utc": (
            _STUB_RUN_TIMESTAMP_UTC if is_stub else ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        ),
        "provider": str(cfg.llm_provider),
        "n_questions": len(records),
        "dataset_hash": _dataset_hash(eval_set_path),
        "total_cost_usd": total_cost_usd,
        "wall_clock_seconds": wall_clock_seconds,
        "representative": is_representative,
    }

    # ------------------------------------------------------------------
    # Step 8: determine hero record (fallback to first record if absent)
    # ------------------------------------------------------------------
    if hero_record is None:
        if not records:
            log.error("eval_run_no_questions", eval_set_path=str(eval_set_path))
            return 1
        hero_record = records[0]
        hero_result_text = answers[0].text if answers else ""
        hero_ranking = rankings.get(records[0].id, [])

    # ------------------------------------------------------------------
    # Step 9: write artifacts to report_dir
    # ------------------------------------------------------------------
    if output_dir is not None:
        report_dir: Path = output_dir
    else:
        # Use microsecond precision to avoid collision when multiple runs start
        # within the same second (e.g. during pytest test sessions).
        report_dir = Path("data/eval/reports") / ts.strftime("%Y%m%d_%H%M%S_%fZ")
    report_dir.mkdir(parents=True, exist_ok=True)

    md_text: str = render_markdown(
        manifest=manifest,
        retrieval=retrieval_result,
        faithfulness=faithfulness_result,
        citation_headline=citation_headline,
        latency=latency_result,
        refusal_matrix=refusal_result,
        per_type_rows=per_type_rows,
        hero_record=hero_record,
        hero_answer=hero_result_text,
        hero_ranking=hero_ranking,
    )
    (report_dir / "report.md").write_text(md_text, encoding="utf-8")

    json_text: str = render_results_json(
        manifest=manifest,
        retrieval=retrieval_result,
        faithfulness=faithfulness_result,
        latency=latency_result,
        refusal_matrix=refusal_result,
        per_question=per_question_rows,
    )
    (report_dir / "results.json").write_text(json_text, encoding="utf-8")

    # ------------------------------------------------------------------
    # Step 10: structured completion log
    # ------------------------------------------------------------------
    log.info(
        "eval_run_completed",
        n_questions=len(records),
        provider=str(cfg.llm_provider),
        wall_clock_seconds=wall_clock_seconds,
        total_cost_usd=total_cost_usd,
        report_dir=str(report_dir),
    )

    return 0


# ---------------------------------------------------------------------------
# Per-type breakdown helper
# ---------------------------------------------------------------------------


def _build_per_type_rows(
    records: list[EvalRecord],
    per_question_rows: list[dict[str, Any]],
    is_stub: bool,
) -> list[dict[str, Any]]:
    """Build the per-question-type breakdown rows for render_markdown Section 4.

    Args:
        records:           Full list of EvalRecord objects.
        per_question_rows: Per-question metric dicts (same order as records).
        is_stub:           True iff running in stub mode (cfg.llm_provider == "stub").
                           Controls whether faithfulness_rate is 0.0 (stub, honest) or
                           None (real mode, not yet tracked per-type).

    Returns:
        List of row dicts for single_doc, multi_doc, refusal types.
    """
    type_stats: dict[str, dict[str, Any]] = {
        "single_doc": {"n": 0, "hit5_hits": 0},
        "multi_doc": {"n": 0, "hit5_hits": 0},
        "refusal": {"n": 0},
    }

    for record, row in zip(records, per_question_rows, strict=True):
        qtype: str = record.question_type

        if qtype in ("single_doc", "multi_doc"):
            type_stats[qtype]["n"] += 1
            type_stats[qtype]["hit5_hits"] += int(row.get("hit_at_5", 0))
        elif qtype == "refusal":
            type_stats["refusal"]["n"] += 1

    # Compute per-type metrics
    rows: list[dict[str, Any]] = []
    for qtype in ("single_doc", "multi_doc", "refusal"):
        stats = type_stats[qtype]
        n: int = int(stats["n"])
        if qtype == "refusal":
            # Count how many refusal questions were NOT refused (false-negative refusals)
            refusal_answered = sum(
                1
                for record, row in zip(records, per_question_rows, strict=True)
                if record.question_type == "refusal" and not bool(row.get("refused", False))
            )
            false_ref_rate: float = refusal_answered / n if n > 0 else 0.0
            false_ref_ci = wilson_ci(refusal_answered, n)
            rows.append(
                {
                    "type": qtype,
                    "n": n,
                    "false_refusal_rate": false_ref_rate,
                    "false_refusal_ci": false_ref_ci,
                }
            )
        else:
            hit5_hits: int = int(stats["hit5_hits"])
            hit5_rate: float = hit5_hits / n if n > 0 else 0.0
            hit5_ci = wilson_ci(hit5_hits, n)
            # Faithfulness rate per type: stub = 0.0 (honest — stub judge always
            # fails); real mode = None (per-question judge verdicts not yet plumbed
            # through per_question_rows; Phase 11 will wire this).
            faith_rate: float | None = 0.0 if is_stub else None
            faith_ci: tuple[float, float] | None = wilson_ci(0, max(n, 1)) if is_stub else None
            rows.append(
                {
                    "type": qtype,
                    "n": n,
                    "hit5": hit5_rate,
                    "hit5_ci": hit5_ci,
                    "faithfulness_rate": faith_rate,
                    "faithfulness_ci": faith_ci,
                }
            )

    return rows
