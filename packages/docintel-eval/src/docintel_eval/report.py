"""docintel-eval report module: pure render functions for markdown + results.json.

Phase 10 report rendering (EVAL-02 / D-05 / D-06 / D-07 / D-08).
Both public functions are pure — no I/O, no Settings reads, no clock calls.
The caller (runner.py) passes in all computed values.

render_markdown  -> D-05 six-section markdown string.
render_results_json -> Phase-11-consumable results.json string.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from docintel_eval.dataset import EvalRecord
    from docintel_eval.metrics import (
        FaithfulnessResult,
        LatencyResult,
        RefusalMatrixResult,
        RetrievalMetricsResult,
    )

log = structlog.stdlib.get_logger(__name__)

__all__ = ["render_markdown", "render_results_json"]

# ---------------------------------------------------------------------------
# results.json schema (D-07 / Phase-11-consumable)
# ---------------------------------------------------------------------------


def render_results_json(
    manifest: dict[str, Any],
    retrieval: RetrievalMetricsResult,
    faithfulness: FaithfulnessResult,
    latency: LatencyResult,
    refusal_matrix: RefusalMatrixResult,
    per_question: list[dict[str, Any]],
) -> str:
    """Render the Phase-11-consumable results.json sidecar. Pure function, no I/O.

    The JSON is serialized with ``indent=2`` and ``sort_keys=True`` so two
    calls with equal inputs produce byte-identical output (determinism gate).

    Args:
        manifest:        Dict with exactly 13 keys (D-07). Built by runner.py.
        retrieval:       Frozen RetrievalMetricsResult from compute_retrieval_metrics.
        faithfulness:    Frozen FaithfulnessResult from compute_faithfulness.
        latency:         Frozen LatencyResult from compute_latency_stats.
        refusal_matrix:  Frozen RefusalMatrixResult from compute_refusal_matrix.
        per_question:    List of 32 per-question dicts (twelve keys each).

    Returns:
        JSON string with a trailing newline.
    """
    payload: dict[str, Any] = {
        "manifest": manifest,
        "retrieval": {
            "hit_at_1": retrieval.hit_at_1,
            "hit_at_1_ci": list(retrieval.hit_at_1_ci),
            "hit_at_3": retrieval.hit_at_3,
            "hit_at_3_ci": list(retrieval.hit_at_3_ci),
            "hit_at_5": retrieval.hit_at_5,
            "hit_at_5_ci": list(retrieval.hit_at_5_ci),
            "hit_at_10": retrieval.hit_at_10,
            "hit_at_10_ci": list(retrieval.hit_at_10_ci),
            "mrr": retrieval.mrr,
            "n_questions": retrieval.n_questions,
            "n_multi_doc": retrieval.n_multi_doc,
            "per_company_recalls": retrieval.per_company_recalls,
            "coverage_flag": retrieval.coverage_flag,
            "long_gold_count": retrieval.long_gold_count,
        },
        "faithfulness": {
            "faithfulness_pass_rate": faithfulness.faithfulness_pass_rate,
            "faithfulness_ci": list(faithfulness.faithfulness_ci),
            "n_answered": faithfulness.n_answered,
            "n_total": faithfulness.n_total,
            "mean_score": faithfulness.mean_score,
            "threshold": faithfulness.threshold,
        },
        "latency": {
            "p50_ms": latency.p50_ms,
            "p95_ms": latency.p95_ms,
            "cost_per_query_usd": latency.cost_per_query_usd,
            "n_queries": latency.n_queries,
            "representative": latency.representative,
        },
        "refusal_matrix": {
            "true_refusal_rate": refusal_matrix.true_refusal_rate,
            "true_refusal_ci": list(refusal_matrix.true_refusal_ci),
            "false_answer_rate": refusal_matrix.false_answer_rate,
            "false_answer_ci": list(refusal_matrix.false_answer_ci),
            "false_refusal_rate": refusal_matrix.false_refusal_rate,
            "false_refusal_ci": list(refusal_matrix.false_refusal_ci),
            "n_should_refuse": refusal_matrix.n_should_refuse,
            "n_should_answer": refusal_matrix.n_should_answer,
        },
        "per_question": per_question,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# D-05 six-section markdown report
# ---------------------------------------------------------------------------


def render_markdown(
    manifest: dict[str, Any],
    retrieval: RetrievalMetricsResult,
    faithfulness: FaithfulnessResult,
    citation_headline: float,
    latency: LatencyResult,
    refusal_matrix: RefusalMatrixResult,
    per_type_rows: list[dict[str, Any]],
    hero_record: EvalRecord,
    hero_answer: str,
    hero_ranking: list[str],
) -> str:
    """Render the D-05 six-section eval report. Pure function, no I/O.

    The six sections have these EXACT headers (D-05 locked):
      ## Manifest
      ## Headline Results
      ## Latency & Cost
      ## Per-Question-Type Breakdown
      ## Refusal 2x2 Confusion Matrix
      ## Hero: GT-comparative-001

    When manifest['provider'] == 'stub', prepends the D-08 STUB banner.

    Args:
        manifest:          13-field manifest dict assembled by runner.py.
        retrieval:         Frozen RetrievalMetricsResult.
        faithfulness:      Frozen FaithfulnessResult.
        citation_headline: Aggregate citation precision (mean over answered qs).
        latency:           Frozen LatencyResult.
        refusal_matrix:    Frozen RefusalMatrixResult.
        per_type_rows:     List of dicts with type breakdown rows.
        hero_record:       EvalRecord for GT-comparative-001.
        hero_answer:       System-generated answer text for the hero question.
        hero_ranking:      Ranked chunk_id list (k=10) for the hero question.

    Returns:
        Markdown string.
    """
    lines: list[str] = []

    # Title
    lines.append("# docintel Eval Report")
    lines.append("")

    # D-08 STUB banner — structurally derived from manifest.representative
    provider: str = str(manifest.get("provider", ""))
    if provider == "stub":
        lines.append(
            "> STUB RUN — latency & $/query are non-representative. " "representative: false"
        )
        lines.append("> Run with DOCINTEL_LLM_PROVIDER=real for published numbers.")
        lines.append("")

    # -----------------------------------------------------------------------
    # Section 1: ## Manifest
    # -----------------------------------------------------------------------
    lines.append("## Manifest")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| embedder | {manifest.get('embedder_name', '')} |")
    lines.append(f"| reranker | {manifest.get('reranker_name', '')} |")
    lines.append(f"| generator | {manifest.get('generator_name', '')} |")
    lines.append(f"| judge | {manifest.get('judge_name', '')} |")
    lines.append(f"| prompt_version_hash | {manifest.get('prompt_version_hash', '')} |")
    lines.append(f"| git_sha | {manifest.get('git_sha', '')} |")
    lines.append(f"| timestamp | {manifest.get('run_timestamp_utc', '')} |")
    lines.append(f"| provider | {manifest.get('provider', '')} |")
    lines.append(f"| n_questions | {manifest.get('n_questions', '')} |")
    dataset_hash: str = str(manifest.get("dataset_hash", ""))
    lines.append(f"| dataset_hash | sha256:{dataset_hash} |")
    total_cost: float = float(manifest.get("total_cost_usd", 0.0))
    lines.append(f"| total_cost_usd | ${total_cost:.6f} |")
    wall_clock: float = float(manifest.get("wall_clock_seconds", 0.0))
    lines.append(f"| wall_clock_s | {wall_clock:.2f} |")
    representative: bool = bool(manifest.get("representative", False))
    lines.append(f"| representative | {str(representative).lower()} |")
    lines.append("")

    # -----------------------------------------------------------------------
    # Section 2: ## Headline Results
    # -----------------------------------------------------------------------
    lines.append("## Headline Results")
    lines.append("")
    lines.append("| Metric | Value | 95% Wilson CI |")
    lines.append("|--------|-------|---------------|")

    def _fmt_ci(ci: tuple[float, float]) -> str:
        return f"[{ci[0]:.3f}, {ci[1]:.3f}]"

    lines.append(f"| Hit@1 | {retrieval.hit_at_1:.3f} | " f"{_fmt_ci(retrieval.hit_at_1_ci)} |")
    lines.append(f"| Hit@3 | {retrieval.hit_at_3:.3f} | " f"{_fmt_ci(retrieval.hit_at_3_ci)} |")
    lines.append(f"| Hit@5 | {retrieval.hit_at_5:.3f} | " f"{_fmt_ci(retrieval.hit_at_5_ci)} |")
    lines.append(f"| Hit@10 | {retrieval.hit_at_10:.3f} | " f"{_fmt_ci(retrieval.hit_at_10_ci)} |")
    lines.append(f"| MRR | {retrieval.mrr:.3f} | — |")
    lines.append(
        f"| Faithfulness (n={faithfulness.n_answered}) | "
        f"{faithfulness.faithfulness_pass_rate:.3f} | "
        f"{_fmt_ci(faithfulness.faithfulness_ci)} |"
    )
    lines.append(
        f"| Citation Accuracy (n={faithfulness.n_answered}) | " f"{citation_headline:.3f} | — |"
    )
    lines.append(
        f"| True Refusal Rate (n={refusal_matrix.n_should_refuse}) | "
        f"{refusal_matrix.true_refusal_rate:.3f} | "
        f"{_fmt_ci(refusal_matrix.true_refusal_ci)} |"
    )
    lines.append(
        f"| False Answer Rate (n={refusal_matrix.n_should_refuse}) | "
        f"{refusal_matrix.false_answer_rate:.3f} | "
        f"{_fmt_ci(refusal_matrix.false_answer_ci)} |"
    )
    lines.append(
        f"| False Refusal Rate (n={refusal_matrix.n_should_answer}) | "
        f"{refusal_matrix.false_refusal_rate:.3f} | "
        f"{_fmt_ci(refusal_matrix.false_refusal_ci)} |"
    )
    lines.append("")

    # -----------------------------------------------------------------------
    # Section 3: ## Latency & Cost
    # -----------------------------------------------------------------------
    lines.append("## Latency & Cost")
    lines.append("")
    if not latency.representative:
        lines.append("> Non-representative (stub mode). See manifest.representative.")
        lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| p50 latency | {latency.p50_ms:.1f} ms |")
    lines.append(f"| p95 latency | {latency.p95_ms:.1f} ms |")
    lines.append(f"| mean $/query | ${latency.cost_per_query_usd:.6f} |")
    lines.append(f"| n_queries | {latency.n_queries} |")
    lines.append("")

    # -----------------------------------------------------------------------
    # Section 4: ## Per-Question-Type Breakdown
    # -----------------------------------------------------------------------
    lines.append("## Per-Question-Type Breakdown")
    lines.append("")
    lines.append("| Type | n | Hit@5 | Faithfulness | False-Refusal |")
    lines.append("|------|---|-------|--------------|---------------|")
    for row in per_type_rows:
        qtype: str = str(row.get("type", ""))
        n_row: int = int(row.get("n", 0))
        if qtype == "refusal":
            hit5_str = "—"
            faith_str = "—"
            false_ref_val: float = float(row.get("false_refusal_rate", 0.0))
            false_ref_ci_raw: Any = row.get("false_refusal_ci", (0.0, 1.0))
            false_ref_str = (
                f"{false_ref_val:.3f} "
                f"[{float(false_ref_ci_raw[0]):.3f}, "
                f"{float(false_ref_ci_raw[1]):.3f}]"
            )
        else:
            hit5_val: float = float(row.get("hit5", 0.0))
            hit5_ci_raw: Any = row.get("hit5_ci", (0.0, 1.0))
            hit5_str = (
                f"{hit5_val:.3f} " f"[{float(hit5_ci_raw[0]):.3f}, {float(hit5_ci_raw[1]):.3f}]"
            )
            faith_rate_raw: Any = row.get("faithfulness_rate")
            if faith_rate_raw is None:
                # Real mode: per-type faithfulness not yet tracked (Phase 11 wires this)
                faith_str = "n/a (see headline)"
            else:
                faith_val: float = float(faith_rate_raw)
                faith_ci_raw: Any = row.get("faithfulness_ci", (0.0, 1.0))
                faith_str = (
                    f"{faith_val:.3f} "
                    f"[{float(faith_ci_raw[0]):.3f}, {float(faith_ci_raw[1]):.3f}]"
                )
            false_ref_str = "—"
        lines.append(f"| {qtype} | {n_row} | {hit5_str} | {faith_str} | {false_ref_str} |")
    lines.append("")

    # -----------------------------------------------------------------------
    # Section 5: ## Refusal 2x2 Confusion Matrix
    # -----------------------------------------------------------------------
    lines.append("## Refusal 2x2 Confusion Matrix")
    lines.append("")
    n_sr: int = refusal_matrix.n_should_refuse
    n_sa: int = refusal_matrix.n_should_answer
    tp_count: int = round(refusal_matrix.true_refusal_rate * n_sr)
    fn_count: int = n_sr - tp_count
    fp_count: int = round(refusal_matrix.false_refusal_rate * n_sa)
    tn_count: int = n_sa - fp_count
    lines.append("| | Actually Refused | Actually Answered |")
    lines.append("|-|-----------------|-------------------|")
    lines.append(f"| Should Refuse (n={n_sr}) | {tp_count} (TP) | {fn_count} (FN) |")
    lines.append(f"| Should Answer (n={n_sa}) | {fp_count} (FP) | {tn_count} (TN) |")
    lines.append("")
    lines.append(
        f"- True Refusal Rate: {refusal_matrix.true_refusal_rate:.3f} "
        f"[{refusal_matrix.true_refusal_ci[0]:.3f}, "
        f"{refusal_matrix.true_refusal_ci[1]:.3f}]"
    )
    lines.append(
        f"- False Answer Rate: {refusal_matrix.false_answer_rate:.3f} "
        f"[{refusal_matrix.false_answer_ci[0]:.3f}, "
        f"{refusal_matrix.false_answer_ci[1]:.3f}]"
    )
    lines.append(
        f"- False Refusal Rate: {refusal_matrix.false_refusal_rate:.3f} "
        f"[{refusal_matrix.false_refusal_ci[0]:.3f}, "
        f"{refusal_matrix.false_refusal_ci[1]:.3f}]"
    )
    lines.append("")

    # -----------------------------------------------------------------------
    # Section 6: ## Hero: GT-comparative-001 (Multi-hop Comparative)
    # -----------------------------------------------------------------------
    lines.append("## Hero: GT-comparative-001 (Multi-hop Comparative)")
    lines.append("")
    lines.append(f"**Question:** {hero_record.question}")
    lines.append("")
    lines.append(f"**Gold Answer:** {hero_record.gold_answer}")
    lines.append("")
    lines.append(f"**System Answer:** {hero_answer}")
    lines.append("")

    # Per-component coverage (D-14 / D-06)
    lines.append("**Per-Component Coverage (D-14):**")
    lines.append("| Company | Gold Chunks Required | Gold Chunks in Top-10 | Coverage |")
    lines.append("|---------|---------------------|----------------------|---------|")
    top10_set: set[str] = set(hero_ranking[:10])
    all_covered: bool = True
    for company in hero_record.companies:
        company_golds: list[str] = [
            cid for cid in hero_record.gold_passage_ids if cid.startswith(f"{company}-")
        ]
        if not company_golds:
            # No prefix-matched golds for this company — skip rather than
            # attributing the full gold list (which would produce misleading
            # N/N coverage for every company in non-prefixed datasets).
            lines.append(f"| {company} | (no prefix match) | — | — |")
            all_covered = False
            continue
        found_count: int = sum(1 for cid in company_golds if cid in top10_set)
        covered: bool = found_count == len(company_golds) and len(company_golds) > 0
        if not covered:
            all_covered = False
        gold_str: str = ", ".join(company_golds)
        found_marker: str = "✓" if covered else "✗"
        coverage_str: str = f"{found_count}/{len(company_golds)}"
        lines.append(f"| {company} | {gold_str} | {found_marker} | {coverage_str} |")
    lines.append("")
    covered_note: str = (
        "all companies covered"
        if all_covered
        else "stub retriever cannot find multi-hop golds — expected in stub mode"
    )
    lines.append(f"**Coverage Flag:** {all_covered} ({covered_note})")

    return "\n".join(lines)
