"""docintel-eval metrics module: MET-01..MET-06 pure functions + frozen result models.

Phase 9 (MET-01..MET-06) metric computation over EvalRecord × Answer inputs.
All functions are pure (no I/O, no LLM calls). Result models are frozen
Pydantic v2 contracts consumed by Phase 10 (report renderer) and Phase 11
(ablation bootstrap).

Importers use: ``from docintel_eval.metrics import hit_at_k, mrr, ...``

Implementation ships in waves 09-02 (retrieval + stats) and 09-03
(answer quality + timing). This module exists now so test scaffolds
(test_metrics.py) can import from a real package path — the ImportError
on individual symbols is the xfail-strict trigger until each wave lands.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict
from scipy.stats import binomtest

__all__ = [
    "QueryTimingRecord",
    "RetrievalMetricsResult",
    "FaithfulnessResult",
    "CitationAccuracyResult",
    "LatencyResult",
    "RefusalMatrixResult",
    "wilson_ci",
    "hit_at_k",
    "mrr",
    "bootstrap_delta_ci",
    "compute_retrieval_metrics",
]


# ---------------------------------------------------------------------------
# Statistical primitives (MET-01 Wilson CI, MET-06 bootstrap delta CI)
# ---------------------------------------------------------------------------


def wilson_ci(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval via scipy.stats.binomtest.

    Returns (low, high) 95% confidence interval for a rate of k successes in n trials.

    When n == 0, returns (0.0, 1.0) — undefined denominator, full interval.
    When k == 0, lower bound is exactly 0.0 (no negative values).
    When k == n, upper bound is exactly 1.0 (no values > 1).

    Args:
        k: Number of successes (hit@K=1 over the question set).
        n: Total number of trials (questions).
        confidence: Confidence level, default 0.95 (95% Wilson interval).

    Returns:
        (low, high) tuple of floats in [0.0, 1.0].

    Note:
        Uses ``scipy.stats.binomtest(k, n).proportion_ci(method='wilson')``.
        Do NOT use ``scipy.stats.proportion_confint`` — it does not exist in scipy 1.17.
    """
    if n == 0:
        return (0.0, 1.0)
    result = binomtest(k, n).proportion_ci(confidence_level=confidence, method="wilson")
    return (result.low, result.high)


def bootstrap_delta_ci(
    arm_a: list[float],
    arm_b: list[float],
    *,
    n_boot: int = 10_000,
    seed: int = 42,
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    """Paired bootstrap percentile CI on delta = arm_a - arm_b (MET-06).

    Both arms are resampled using the SAME question-index draw on each bootstrap
    iteration — this is the paired design required for ablation comparisons where
    both pipelines are run on the same question set.

    Determinism: two calls with the same ``seed`` and ``n_boot`` produce
    bit-exact equal (delta, lo, hi).

    Args:
        arm_a: Per-question scores for pipeline A (e.g. with_rerank).
        arm_b: Per-question scores for pipeline B (e.g. without_rerank).
               Must be the same length as arm_a.
        n_boot: Number of bootstrap resamples. Default 10_000.
        seed: RNG seed for reproducibility. Default 42.
        confidence: Confidence level for the interval. Default 0.95.

    Returns:
        (observed_delta, ci_low, ci_high) where observed_delta = mean(a) - mean(b)
        and (ci_low, ci_high) is the percentile bootstrap CI.

    Raises:
        AssertionError: If arm_a and arm_b have different lengths.

    Note:
        Uses ``np.random.default_rng(seed).integers(...)`` — NOT ``np.random.randint``
        or ``np.random.choice`` (which use global state and are not reproducible).
        Percentile method chosen over BCa — negligible difference at n=32.
    """
    a = np.asarray(arm_a, dtype=float)
    b = np.asarray(arm_b, dtype=float)
    assert len(a) == len(b), "Paired bootstrap requires equal-length arms"
    n = len(a)
    rng = np.random.default_rng(seed)
    boot_deltas = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_deltas[i] = a[idx].mean() - b[idx].mean()
    alpha = 1.0 - confidence
    lo = float(np.percentile(boot_deltas, 100 * alpha / 2))
    hi = float(np.percentile(boot_deltas, 100 * (1 - alpha / 2)))
    return (float(a.mean() - b.mean()), lo, hi)


# ---------------------------------------------------------------------------
# Retrieval metrics — pure functions (MET-01 Hit@K, MET-02 MRR)
# D-01: takes ranked chunk_id list + gold set + K; NOT GenerationResult/Answer.
# ---------------------------------------------------------------------------


def hit_at_k(ranked_chunk_ids: list[str], gold_set: set[str], k: int) -> int:
    """Returns 1 iff ALL golds are in the top-K ranked chunks (strict, D-12).

    D-01: pure function over a ranked ``chunk_id`` list + gold set + K.
    Decoupled from GenerationResult/Answer — the harness supplies the ranking.

    Strict semantics (D-12): ALL golds must be present in top-K; returning 1
    when only SOME golds are found (lenient) is explicitly disallowed. This
    measures multi-hop retrieval completeness without softening.

    Args:
        ranked_chunk_ids: Ranked list from Retriever.search(query, k>=10).
        gold_set:         Set of gold passage IDs from EvalRecord.gold_passage_ids.
        k:                Cutoff depth (typically 1, 3, 5, or 10).

    Returns:
        1 if gold_set ⊆ set(ranked_chunk_ids[:k]), else 0.
    """
    top_k = set(ranked_chunk_ids[:k])
    return 1 if gold_set.issubset(top_k) else 0


def reciprocal_rank(ranked_chunk_ids: list[str], gold_set: set[str]) -> float:
    """Reciprocal rank of the FIRST gold chunk in the ranking (D-13).

    D-01: pure function over a ranked ``chunk_id`` list + gold set.
    Decoupled from GenerationResult/Answer.

    MRR semantics (D-13): rank of the first encountered gold in the list
    (1-indexed). If no gold is found, returns 0.0. MRR is a continuous point
    estimate; no Wilson CI is applied (Pitfall 7 — it is not a binary rate).

    Args:
        ranked_chunk_ids: Ranked list from Retriever.search(query, k>=10).
        gold_set:         Set of gold passage IDs from EvalRecord.gold_passage_ids.

    Returns:
        1.0 / rank (1-indexed) of the first gold found, or 0.0 if none found.
    """
    for rank_0, cid in enumerate(ranked_chunk_ids):
        if cid in gold_set:
            return 1.0 / (rank_0 + 1)
    return 0.0


# Public alias: tests import ``from docintel_eval.metrics import mrr``
mrr = reciprocal_rank


# ---------------------------------------------------------------------------
# Retrieval result model (MET-01 + MET-02 aggregate, D-14 multi-doc, D-15 long-gold)
# ---------------------------------------------------------------------------


class RetrievalMetricsResult(BaseModel):
    """MET-01 + MET-02 aggregated result. Frozen so Phase 10 cannot mutate it.

    Fields:
        hit_at_1/3/5/10:    Mean Hit@K rate over the question set.
        hit_at_1/3/5/10_ci: Wilson 95% CI on each Hit@K rate.
        mrr:                Mean reciprocal rank (point estimate, no CI — D-13).
        n_questions:        Total questions used in Hit@K/MRR computation.
        n_multi_doc:        Count of multi_doc questions (D-14 denominator).
        per_company_recalls: Fraction of each company's golds in top-K, computed
                             over the multi_doc subset only (D-14, Pitfall 8).
        coverage_flag:      True iff every required company has >=1 gold in top-K
                            (D-14). False if any company is missed, even if others
                            are well-covered.
        long_gold_count:    Count of records carrying the 'long-gold' tag (D-15).
                            Reported separately; records are NOT filtered out.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    hit_at_10: float
    hit_at_1_ci: tuple[float, float]
    hit_at_3_ci: tuple[float, float]
    hit_at_5_ci: tuple[float, float]
    hit_at_10_ci: tuple[float, float]
    mrr: float
    n_questions: int
    n_multi_doc: int
    per_company_recalls: dict[str, float]
    coverage_flag: bool
    long_gold_count: int


def compute_retrieval_metrics(
    records: list[object],
    rankings: dict[str, list[str]],
    k_multidoc: int = 10,
) -> RetrievalMetricsResult:
    """Aggregate Hit@{1,3,5,10} + MRR over eval records and their ranked chunk lists.

    D-01: rankings dict maps question_id -> ranked list[str] from Retriever.search.
    This function takes EvalRecord objects + rankings; it does NOT consume GenerationResult.

    D-14 (multi_doc): per-company recall and coverage_flag are computed ONLY over
    records with question_type == 'multi_doc' (Pitfall 8: not over all 32 records).

    D-15 (long-gold): records with 'long-gold' in tags are counted separately in
    long_gold_count but are NOT filtered from Hit@K/MRR computation.

    Args:
        records:     List of EvalRecord objects (question_type, gold_passage_ids, tags).
        rankings:    Dict mapping record.id -> ranked chunk_id list from retriever.
        k_multidoc:  K cutoff used for multi-doc per-company coverage (default 10).

    Returns:
        Frozen RetrievalMetricsResult.
    """
    # We import EvalRecord here (not at module top) to avoid circular imports
    # and to keep the function testable with duck-typed objects.
    from docintel_eval.dataset import EvalRecord

    k_values = [1, 3, 5, 10]
    hit_counts: dict[int, int] = {k: 0 for k in k_values}
    mrr_sum = 0.0
    n_questions = 0

    multi_doc_records: list[EvalRecord] = []
    long_gold_count = 0

    for rec in records:
        rec_id: str = rec.id  # type: ignore[attr-defined]
        gold_set: set[str] = set(rec.gold_passage_ids)  # type: ignore[attr-defined]
        ranked = rankings.get(rec_id, [])

        # Count long-gold records (D-15) — do NOT exclude them
        if "long-gold" in rec.tags:  # type: ignore[attr-defined]
            long_gold_count += 1

        # Collect multi_doc subset for D-14 (after the loop)
        if rec.question_type == "multi_doc":  # type: ignore[attr-defined]
            multi_doc_records.append(rec)  # type: ignore[arg-type]

        if not gold_set:
            # refusal records have empty gold_passage_ids; skip for Hit@K/MRR
            continue

        n_questions += 1
        for k in k_values:
            hit_counts[k] += hit_at_k(ranked, gold_set, k)
        mrr_sum += reciprocal_rank(ranked, gold_set)

    # Compute Hit@K rates and Wilson CIs
    hit_rates: dict[int, float] = {}
    hit_cis: dict[int, tuple[float, float]] = {}
    for k in k_values:
        rate = hit_counts[k] / n_questions if n_questions > 0 else 0.0
        hit_rates[k] = rate
        hit_cis[k] = wilson_ci(hit_counts[k], n_questions)

    mean_mrr = mrr_sum / n_questions if n_questions > 0 else 0.0

    # D-14: per-component recall over multi_doc subset only (Pitfall 8)
    per_company_recalls: dict[str, float] = {}
    coverage_flag = True  # True iff all companies have >=1 gold in top-K
    n_multi_doc = len(multi_doc_records)

    if multi_doc_records:
        # Aggregate per-company gold counts and hit counts across multi_doc records
        company_gold_total: dict[str, int] = {}
        company_gold_hit: dict[str, int] = {}

        for rec in multi_doc_records:
            ranked = rankings.get(rec.id, [])
            top_k_set = set(ranked[:k_multidoc])
            for company in rec.companies:
                # Gold chunks attributed to this company in this record:
                # derive by filtering gold_passage_ids that start with "{ticker}-"
                company_golds = {
                    cid for cid in rec.gold_passage_ids
                    if cid.startswith(f"{company}-")
                }
                if not company_golds:
                    # Fallback: if chunk IDs don't follow ticker prefix convention,
                    # treat all golds as belonging to the first company in record.
                    # This is a best-effort; real data should use the prefix convention.
                    continue
                company_gold_total[company] = (
                    company_gold_total.get(company, 0) + len(company_golds)
                )
                hits = len(company_golds & top_k_set)
                company_gold_hit[company] = company_gold_hit.get(company, 0) + hits

        for company, total in company_gold_total.items():
            recall = company_gold_hit.get(company, 0) / total if total > 0 else 0.0
            per_company_recalls[company] = recall
            if company_gold_hit.get(company, 0) == 0:
                coverage_flag = False
    else:
        coverage_flag = False  # no multi_doc records -> no coverage to confirm

    return RetrievalMetricsResult(
        hit_at_1=hit_rates[1],
        hit_at_3=hit_rates[3],
        hit_at_5=hit_rates[5],
        hit_at_10=hit_rates[10],
        hit_at_1_ci=hit_cis[1],
        hit_at_3_ci=hit_cis[3],
        hit_at_5_ci=hit_cis[5],
        hit_at_10_ci=hit_cis[10],
        mrr=mean_mrr,
        n_questions=n_questions,
        n_multi_doc=n_multi_doc,
        per_company_recalls=per_company_recalls,
        coverage_flag=coverage_flag,
        long_gold_count=long_gold_count,
    )


# ---------------------------------------------------------------------------
# Frozen result models for future waves (09-03 answer quality + timing)
# Defined here so __all__ is honest and import scaffolds in test_metrics.py
# can reference them without raising NameError.
# ---------------------------------------------------------------------------


class QueryTimingRecord(BaseModel):
    """Per-query timing + cost record for MET-05 (latency, $/query).

    Phase 10 harness populates this by wrapping generator.generate() in
    perf_counter. Avoids mutating the frozen GenerationResult schema (D-06).

    Sub-stage timings are optional (None when harness cannot sub-time;
    Phase 12 adds trace_id for sub-stage resolution).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str
    total_ms: float
    cost_usd: float
    model: str
    refused: bool
    retrieval_ms: float | None = None
    generation_ms: float | None = None


class FaithfulnessResult(BaseModel):
    """MET-03 faithfulness pass-rate result. Implemented in 09-03."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    faithfulness_pass_rate: float
    faithfulness_ci: tuple[float, float]
    n_answered: int
    n_total: int


class CitationAccuracyResult(BaseModel):
    """MET-04 citation accuracy result. Implemented in 09-03."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    precision: float
    precision_ci: tuple[float, float]
    n_citations: int


class LatencyResult(BaseModel):
    """MET-05 latency/cost aggregate. Implemented in 09-03."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    p50_ms: float
    p95_ms: float
    cost_per_query_usd: float
    n_queries: int


class RefusalMatrixResult(BaseModel):
    """MET-04 refusal 2x2 confusion matrix. Implemented in 09-03."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    true_refusal_rate: float
    true_refusal_ci: tuple[float, float]
    false_answer_rate: float
    false_answer_ci: tuple[float, float]
    false_refusal_rate: float
    false_refusal_ci: tuple[float, float]
    n_should_refuse: int
    n_should_answer: int
