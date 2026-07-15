"""docintel-eval brief scoring (Story 3.1, FR-C1/FR-C6).

Scores generated four-section briefs — the headline product surface (Epic 2) —
not just single Q&A answers. For each brief case it generates the brief
(`generate_brief`), then reuses the Phase 9 metrics: Hit@K/MRR over the brief's
combined section retrieval, faithfulness per section (FR-C6 = per-claim
grounding), citation accuracy vs the expected set, and latency/$/query. A
fabricated or mis-cited claim lowers citation accuracy / faithfulness — it does
not silently pass (AC-2).

Additive `docintel-eval brief-eval` command: does NOT touch `run_eval` or the
locked Q&A report/baseline bytes.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from docintel_core.adapters.factory import make_generator
from docintel_core.config import Settings

from docintel_eval.brief_dataset import BriefEvalRecord, load_brief_questions
from docintel_eval.metrics import (
    QueryTimingRecord,
    compute_faithfulness,
    compute_latency_stats,
    hit_at_k,
    reciprocal_rank,
    wilson_ci,
)

if TYPE_CHECKING:
    from docintel_generate.generator import Generator

log = structlog.stdlib.get_logger(__name__)

__all__ = ["brief_citation_hits", "merge_rankings", "run_brief_eval", "score_brief"]

_BRIEF_SET_PATH = Path("data/eval/brief_ground_truth/brief_set.jsonl")


def merge_rankings(ranked_lists: list[list[str]]) -> list[str]:
    """Merge the four sections' retrieval rankings into ONE brief-level ranking by
    best (lowest) position across sections; dedup, ties broken by first section.
    Pure. This is the true retrieval quality (over the retriever's rankings) —
    NOT the LLM's citations, so Hit@K measures retrieval, not generation."""
    best_pos: dict[str, int] = {}
    for ranked in ranked_lists:
        for pos, cid in enumerate(ranked):
            if cid not in best_pos or pos < best_pos[cid]:
                best_pos[cid] = pos
    return [cid for cid, _ in sorted(best_pos.items(), key=lambda kv: kv[1])]


def brief_citation_hits(section_results: list[Any], expected: set[str]) -> tuple[int, int]:
    """(hits, n_citations) across all four sections vs the expected set. Pure."""
    hits = 0
    n = 0
    for sr in section_results:
        for cit in sr.answer.citations:
            n += 1
            if cit.chunk_id in expected:
                hits += 1
    return hits, n


def score_brief(
    ranking: list[str],
    section_results: list[Any],
    gold_passage_ids: list[str],
    expected_citation_ids: list[str],
) -> dict[str, Any]:
    """Pure per-brief scoring: Hit@K/MRR over the merged retrieval ``ranking`` +
    citation accuracy over the sections' citations. Faithfulness is scored
    separately (it needs the judge). AC-2: a fabricated/mis-cited citation lowers
    ``citation_precision`` here — it cannot silently pass."""
    gold_set = set(gold_passage_ids)
    hits, n_cit = brief_citation_hits(section_results, set(expected_citation_ids))

    def _recall(k: int) -> float:
        # Fraction of gold passages surfaced in the merged top-k. A brief has many
        # golds spanning items, so this per-gold RECALL is the meaningful retrieval
        # metric; strict Hit@K (ALL golds in top-K, D-12) is stringent for briefs
        # and reported alongside for continuity.
        if not gold_set:
            return 0.0
        return len(gold_set & set(ranking[:k])) / len(gold_set)

    return {
        "hit_at_1": hit_at_k(ranking, gold_set, 1) if gold_set else 0,
        "hit_at_3": hit_at_k(ranking, gold_set, 3) if gold_set else 0,
        "hit_at_5": hit_at_k(ranking, gold_set, 5) if gold_set else 0,
        "hit_at_10": hit_at_k(ranking, gold_set, 10) if gold_set else 0,
        "recall_at_5": _recall(5),
        "recall_at_10": _recall(10),
        "reciprocal_rank": reciprocal_rank(ranking, gold_set) if gold_set else 0.0,
        "citation_hits": hits,
        "n_citations": n_cit,
        "citation_precision": (hits / n_cit) if n_cit else 0.0,
    }


def run_brief_eval(
    cfg: Settings,
    *,
    output_dir: Path | None = None,
    generator: Generator | None = None,
) -> int:
    """Generate + score every brief case; write brief-report.md + brief-results.json."""
    from docintel_generate.brief import BRIEF_SECTIONS, generate_brief

    if generator is None:
        generator = make_generator(cfg)
    judge = generator._bundle.judge
    retriever = generator._retriever  # reuse the warm retriever (Pitfall 2)
    is_stub = str(cfg.llm_provider) == "stub"

    records: list[BriefEvalRecord] = load_brief_questions(_BRIEF_SET_PATH)
    all_section_answers: list[Any] = []
    per_brief: list[dict[str, Any]] = []
    timings: list[QueryTimingRecord] = []
    hit_counts = {1: 0, 3: 0, 5: 0, 10: 0}
    recall5_sum = 0.0
    recall10_sum = 0.0
    mrr_sum = 0.0
    cit_hits_total = 0
    cit_n_total = 0

    for rec in records:
        t0 = time.perf_counter()
        sections = list(generate_brief(generator, rec.ticker, rec.company))
        elapsed_ms = 0.0 if is_stub else (time.perf_counter() - t0) * 1000
        all_section_answers.extend(sr.answer for sr in sections)

        # True per-section retrieval ranking (ticker-scoped, k=10), merged into
        # one brief-level ranking — Hit@K/MRR measure retrieval, not the LLM's
        # citations (which the stub fakes). Retrieval is real even in stub mode.
        section_rankings = [
            [
                c.chunk_id
                for c in retriever.search(
                    s.query.format(company=rec.company), k=10, ticker=rec.ticker
                )
            ]
            for s in BRIEF_SECTIONS
        ]
        ranking = merge_rankings(section_rankings)
        scored = score_brief(ranking, sections, rec.gold_passage_ids, rec.expected_citation_ids)
        for k in (1, 3, 5, 10):
            hit_counts[k] += int(scored[f"hit_at_{k}"])
        recall5_sum += float(scored["recall_at_5"])
        recall10_sum += float(scored["recall_at_10"])
        mrr_sum += float(scored["reciprocal_rank"])
        cit_hits_total += int(scored["citation_hits"])
        cit_n_total += int(scored["n_citations"])

        timings.append(
            QueryTimingRecord(
                question_id=rec.ticker,
                total_ms=elapsed_ms,
                cost_usd=0.0,  # generate_brief does not surface per-section cost; stub=0 (real-mode follow-up)
                model="stub" if is_stub else str(cfg.llm_provider),
                refused=False,
            )
        )
        per_brief.append({"ticker": rec.ticker, "n_sections": len(sections), **scored})

    n = len(records)
    faithfulness = compute_faithfulness(all_section_answers, judge)
    latency = compute_latency_stats(timings, representative=not is_stub)

    retrieval = {f"hit_at_{k}": (hit_counts[k] / n if n else 0.0) for k in (1, 3, 5, 10)}
    retrieval_ci = {f"hit_at_{k}_ci": list(wilson_ci(hit_counts[k], n)) for k in (1, 3, 5, 10)}
    retrieval["recall_at_5"] = recall5_sum / n if n else 0.0
    retrieval["recall_at_10"] = recall10_sum / n if n else 0.0
    mrr = mrr_sum / n if n else 0.0
    citation_headline = cit_hits_total / cit_n_total if cit_n_total else 0.0

    manifest = {
        "embedder_name": generator._bundle.embedder.name,
        "reranker_name": generator._bundle.reranker.name,
        "generator_name": generator._bundle.llm.name,
        "judge_name": generator._bundle.judge.name,
        "prompt_version_hash": _prompt_hash(),
        "provider": str(cfg.llm_provider),
        "n_briefs": n,
        "brief_set_hash": _sha256(_BRIEF_SET_PATH),
        "representative": not is_stub,
    }

    payload: dict[str, Any] = {
        "manifest": manifest,
        "retrieval": {**retrieval, **retrieval_ci, "mrr": mrr, "n_briefs": n},
        "faithfulness": {
            "faithfulness_pass_rate": faithfulness.faithfulness_pass_rate,
            "faithfulness_ci": list(faithfulness.faithfulness_ci),
            "n_answered": faithfulness.n_answered,
            "n_total": faithfulness.n_total,
        },
        "citation_accuracy": {"precision": citation_headline, "n_citations": cit_n_total},
        "latency": {
            "p50_ms": latency.p50_ms,
            "p95_ms": latency.p95_ms,
            "cost_per_query_usd": latency.cost_per_query_usd,
            "representative": latency.representative,
        },
        "per_brief": per_brief,
    }

    ts = datetime.now(UTC)
    out_dir = output_dir or (Path("data/eval/brief_reports") / ts.strftime("%Y%m%d_%H%M%S_%fZ"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "brief-results.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "brief-report.md").write_text(_render_brief_markdown(payload), encoding="utf-8")

    log.info(
        "brief_eval_completed",
        n_briefs=n,
        hit_at_5=retrieval["hit_at_5"],
        citation_accuracy=citation_headline,
        faithfulness=faithfulness.faithfulness_pass_rate,
        representative=not is_stub,
        output_dir=str(out_dir),
    )
    return 0


def _render_brief_markdown(payload: dict[str, Any]) -> str:
    m = payload["manifest"]
    r = payload["retrieval"]
    f = payload["faithfulness"]
    c = payload["citation_accuracy"]
    lat = payload["latency"]
    lines = ["# docintel Brief Eval Report (FR-C1/FR-C6)", ""]
    if not m["representative"]:
        lines += [
            "> STUB RUN — latency/$ and the stub judge's faithfulness are "
            "non-representative. representative: false.",
            "",
        ]
    lines += [
        "## Headline (per-brief)",
        "",
        f"- **Recall@10:** {r['recall_at_10']:.3f}  (fraction of gold passages surfaced — the meaningful brief retrieval metric)",
        f"- **Recall@5:** {r['recall_at_5']:.3f}",
        f"- **Hit@5 (strict, all golds in top-5):** {r['hit_at_5']:.3f}  (CI {r['hit_at_5_ci'][0]:.3f} to {r['hit_at_5_ci'][1]:.3f})",
        f"- **MRR:** {r['mrr']:.3f}",
        f"- **Citation accuracy:** {c['precision']:.3f}  (n={c['n_citations']} citations)",
        f"- **Faithfulness:** {f['faithfulness_pass_rate']:.3f}  "
        f"(CI {f['faithfulness_ci'][0]:.3f} to {f['faithfulness_ci'][1]:.3f}, per section/claim, FR-C6)",
        f"- **Latency p50/p95:** {lat['p50_ms']:.1f} / {lat['p95_ms']:.1f} ms",
        f"- **$/brief:** {lat['cost_per_query_usd']:.4f}",
        f"- **n briefs:** {r['n_briefs']}",
        "",
        "## Manifest",
        "",
    ]
    for k, v in m.items():
        lines.append(f"- `{k}`: {v}")
    lines += [
        "",
        "## Per-brief",
        "",
        "| ticker | Hit@5 | RR | citation precision | n cites |",
        "|---|---|---|---|---|",
    ]
    for b in payload["per_brief"]:
        lines.append(
            f"| {b['ticker']} | {b['hit_at_5']} | {b['reciprocal_rank']:.3f} "
            f"| {b['citation_precision']:.3f} | {b['n_citations']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _prompt_hash() -> str:
    from docintel_generate.prompts import PROMPT_VERSION_HASH

    return PROMPT_VERSION_HASH


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
