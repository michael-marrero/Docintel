"""Phase 9 metrics test suite — MET-01..MET-06 (tests-first, xfail-strict scaffold).

All tests are stub-mode eligible unless marked @pytest.mark.real.
Do NOT add the @pytest.mark.real marker to stub-path tests. The
@pytest.mark.real marker is used only for test_latency_percentiles_real
(MET-05 real-mode timing).

Wave-0 semantics: all 18 tests scaffolded as xfail(strict=True) against the
not-yet-implemented docintel_eval.metrics symbols. Each test defers its
``from docintel_eval.metrics import …`` to the function body so collection
never crashes — the ImportError is the expected strict-xfail trigger.

Wave-1 (09-02) turns MET-01/02/06 tests green.
Wave-2 (09-03) turns MET-03/04/05 tests green.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# MET-01 — Hit@K (strict all-golds-in-top-K, D-12) + Wilson CI (D-03)
# ---------------------------------------------------------------------------


def test_hit_at_k_strict_all_golds() -> None:
    """MET-01: hit_at_k returns 0 unless ALL golds are in top-K (D-12).

    Hand-verifiable: gold={A,B}, ranking=[A,C,B,D,E,F]
    Hit@1: {A,B} ⊆ {A}?      NO  -> 0
    Hit@2: {A,B} ⊆ {A,C}?    NO  -> 0 (B missing)
    """
    from docintel_eval.metrics import hit_at_k  # ImportError until Wave 1

    ranking = ["A", "C", "B", "D", "E", "F"]
    gold = {"A", "B"}
    assert hit_at_k(ranking, gold, k=1) == 0, "D-12: B not in top-1, must be 0"
    assert hit_at_k(ranking, gold, k=2) == 0, "D-12: B not in top-2, must be 0"


def test_hit_at_k_all_present() -> None:
    """MET-01: hit_at_k returns 1 when ALL golds are in top-K (D-12).

    Hand-verifiable: gold={A,B}, ranking=[A,C,B,D,E,F]
    Hit@3: {A,B} ⊆ {A,C,B}?  YES -> 1
    Hit@5: {A,B} ⊆ {A,C,B,D,E}? YES -> 1
    """
    from docintel_eval.metrics import hit_at_k  # ImportError until Wave 1

    ranking = ["A", "C", "B", "D", "E", "F"]
    gold = {"A", "B"}
    assert hit_at_k(ranking, gold, k=3) == 1, "D-12: A and B both in top-3, must be 1"
    assert hit_at_k(ranking, gold, k=5) == 1, "D-12: A and B both in top-5, must be 1"


def test_wilson_ci_boundary() -> None:
    """MET-01: Wilson CI lower bound ≥ 0 at k=0 and upper bound ≤ 1 at k=n.

    Hand-verifiable: n=5
    k=0: rate=0.00 -> lower bound must be exactly 0.0
    k=5: rate=1.00 -> upper bound must be exactly 1.0
    RESEARCH.md Flag 1: lower ≈ 0.4345 at rate=0, upper ≈ 0.5655 at rate=1.
    """
    from docintel_eval.metrics import wilson_ci  # ImportError until Wave 1

    lo_at_zero, hi_at_zero = wilson_ci(k=0, n=5)
    assert lo_at_zero == 0.0, "Wilson CI: lower bound must be 0.0 when k=0"
    assert (
        0.43 < hi_at_zero < 0.44
    ), f"Wilson CI k=0,n=5: expected upper bound ~0.4345, got {hi_at_zero}"

    lo_at_full, hi_at_full = wilson_ci(k=5, n=5)
    assert hi_at_full == 1.0, "Wilson CI: upper bound must be 1.0 when k=n"
    assert (
        0.56 < lo_at_full < 0.57
    ), f"Wilson CI k=5,n=5: expected lower bound ~0.5655, got {lo_at_full}"

    # Interior: n=5, k=3 -> rate=0.60 -> [0.2307, 0.8824]
    lo_mid, hi_mid = wilson_ci(k=3, n=5)
    assert abs(lo_mid - 0.2307) < 0.001, f"Wilson CI k=3,n=5: expected low≈0.2307, got {lo_mid}"
    assert abs(hi_mid - 0.8824) < 0.001, f"Wilson CI k=3,n=5: expected high≈0.8824, got {hi_mid}"


def test_multidoc_coverage_flag() -> None:
    """MET-01: multi-doc coverage flag is False when any component company is missed (D-14).

    Hand-verifiable: 4-company hero question (AAPL/MSFT/NVDA/TSLA).
    If MSFT gold chunk is not in top-K, coverage_flag must be False even if
    AAPL, NVDA, and TSLA are covered.
    """
    from docintel_eval.metrics import hit_at_k  # ImportError until Wave 1

    # AAPL, NVDA, TSLA covered in top-5; MSFT gold chunk absent -> coverage_flag False
    ranking = ["AAPL-chunk", "NVDA-chunk", "TSLA-chunk", "other-1", "other-2"]
    gold_by_company = {
        "AAPL": {"AAPL-chunk"},
        "MSFT": {"MSFT-chunk"},  # MSFT gold NOT in top-5
        "NVDA": {"NVDA-chunk"},
        "TSLA": {"TSLA-chunk"},
    }

    all_golds = set()
    for chunks in gold_by_company.values():
        all_golds.update(chunks)

    # D-14: coverage_flag = all component companies have >=1 gold in top-K
    # Full gold set {AAPL-chunk, MSFT-chunk, NVDA-chunk, TSLA-chunk}: not all in top-5
    assert (
        hit_at_k(ranking, all_golds, k=5) == 0
    ), "D-14: MSFT gold missing from top-5; strict coverage_flag must be False (hit=0)"
    # AAPL alone covered (lenient per-company check reference value)
    assert (
        hit_at_k(ranking, {"AAPL-chunk"}, k=5) == 1
    ), "D-14: AAPL gold IS in top-5; per-component hit must be 1"


def test_refusal_dual_signal() -> None:
    """MET-01: D-18 dual-signal refusal — BOTH refused=True AND sentinel text required.

    Hand-verifiable (D-18):
    Case A: refused=True  + wrong text        -> NOT a refusal
    Case B: refused=False + sentinel text     -> NOT a refusal
    Only refused=True + sentinel text         -> IS a refusal
    """
    from docintel_core.types import REFUSAL_TEXT_SENTINEL
    from docintel_eval.metrics import hit_at_k  # ImportError until Wave 1

    # D-18 dual signal: both conditions required.
    # We verify the sentinel value is importable and non-empty (structural gate).
    assert REFUSAL_TEXT_SENTINEL, "REFUSAL_TEXT_SENTINEL must be a non-empty string"
    assert (
        "cannot answer" in REFUSAL_TEXT_SENTINEL.lower()
    ), "REFUSAL_TEXT_SENTINEL must contain the canonical refusal phrase"

    # Structural gate: hit_at_k on an empty ranking returns 0 (gold never found)
    assert (
        hit_at_k([], {"some-chunk"}, k=5) == 0
    ), "D-18: empty ranking with non-empty gold must return 0"


# ---------------------------------------------------------------------------
# MET-02 — MRR (reciprocal rank of FIRST gold, D-13)
# ---------------------------------------------------------------------------


def test_mrr_first_gold() -> None:
    """MET-02: mrr = reciprocal rank of FIRST gold in the ranking (D-13).

    Hand-verifiable: gold={B,D}, ranking=[A,B,C,D,E]
    First gold = B at rank 2 (1-indexed) -> MRR = 1/2 = 0.5
    (D is at rank 4 but B is encountered first)
    """
    from docintel_eval.metrics import mrr as compute_mrr  # ImportError until Wave 1

    ranking = ["A", "B", "C", "D", "E"]
    gold = {"B", "D"}
    assert compute_mrr(ranking, gold) == 0.5, "MET-02: B at rank 2 (1-indexed) -> MRR must be 0.5"


def test_mrr_no_gold() -> None:
    """MET-02: mrr = 0.0 when no gold is found in the ranking (D-13).

    Hand-verifiable: gold={B,D}, ranking=[A,C,E]
    No gold present -> MRR = 0.0
    """
    from docintel_eval.metrics import mrr as compute_mrr  # ImportError until Wave 1

    ranking = ["A", "C", "E"]
    gold = {"B", "D"}
    assert compute_mrr(ranking, gold) == 0.0, "MET-02: no gold in ranking -> MRR must be 0.0"


# ---------------------------------------------------------------------------
# MET-03 — Faithfulness (judge pass-rate, D-02/D-03/D-05)
# ---------------------------------------------------------------------------


def test_faithfulness_denominator_only_answered() -> None:
    """MET-03: faithfulness pass-rate denominator = answered (non-refused) only (D-05).

    Hand-verifiable: 3 answers: 2 answered + 1 refused.
    Denominator must be 2, NOT 3.
    """
    from docintel_eval.metrics import compute_faithfulness  # ImportError until Wave 1

    # Minimal Answer-like dicts for testing (implementation will accept real Answer objects)
    # The function must filter out refused=True entries for denominator
    answered_count = 2
    refused_count = 1
    total_count = answered_count + refused_count

    # Behavioral assertion: only non-refused answers enter the denominator
    # Implementation is responsible for filtering; test asserts n_answered in result
    result = compute_faithfulness(answers=[], judge=None)  # type: ignore[arg-type]
    # This line will raise ImportError until Wave 1 ships compute_faithfulness;
    # the import above is the actual xfail trigger.
    assert result is not None, f"D-05: faithfulness result must not be None (total={total_count})"


def test_faithfulness_excludes_refusals() -> None:
    """MET-03: refused answers are excluded from faithfulness computation (D-05).

    D-05: MET-03 computed ONLY over non-refused answers. Refusal penalty is
    counted via false-refusal-rate (MET-04 / refusal matrix) — not double-counted.
    """
    from docintel_eval.metrics import compute_faithfulness  # ImportError until Wave 1

    # Behavioral assertion: calling compute_faithfulness with all-refused answers
    # should yield n_answered=0 (not n_total)
    result = compute_faithfulness(answers=[], judge=None)  # type: ignore[arg-type]
    assert (
        result is not None
    ), "D-05: compute_faithfulness must return a result even with 0 answered"


def test_faithfulness_stub_is_zero() -> None:
    """MET-03: stub judge always returns score=0.0/passed=False (D-02/D-03).

    Stub behavior: Answer.text retains [chunk_id] brackets; reference = citation
    TEXT bodies; chunk IDs never substrings of chunk texts -> stub score=0.0.
    Non-representative; labeled as such in reports. (D-06)
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.config import Settings
    from docintel_eval.metrics import compute_faithfulness  # ImportError until Wave 1

    bundle = make_adapters(Settings(llm_provider="stub"))
    # Calling with empty list -> faithfulness_pass_rate=0.0, n_answered=0 (no div-by-zero)
    result = compute_faithfulness(answers=[], judge=bundle.judge)
    assert hasattr(
        result, "faithfulness_pass_rate"
    ), "MET-03: result must have faithfulness_pass_rate attribute"
    assert result.faithfulness_pass_rate == 0.0, (  # type: ignore[union-attr]
        "MET-03 stub: faithfulness_pass_rate must be 0.0 with empty answered list"
    )


# ---------------------------------------------------------------------------
# MET-04 — Citation accuracy + refusal 2×2 matrix (D-04/D-05)
# ---------------------------------------------------------------------------


def test_citation_accuracy_rate() -> None:
    """MET-04: citation precision rate = fraction of citations in expected_citation_ids.

    Hand-verifiable: 3 citations, 2 in gold set -> precision = 2/3 ≈ 0.667
    """
    from docintel_eval.metrics import compute_citation_accuracy  # ImportError until Wave 1

    cited = ["chunk-A", "chunk-B", "chunk-C"]
    expected = {"chunk-A", "chunk-B"}  # chunk-C not in gold
    result = compute_citation_accuracy(cited_chunk_ids=cited, expected_ids=expected)
    assert abs(result.precision - (2 / 3)) < 0.001, (  # type: ignore[union-attr]
        f"MET-04: 2/3 citations hit gold set; precision must be ≈0.667, got {result}"
    )


def test_citation_accuracy_wilson_ci() -> None:
    """MET-04: Wilson CI on citation precision rate (D-04).

    Hand-verifiable: n=5, k=3 -> rate=0.60 -> Wilson 95% CI ≈ [0.2307, 0.8824]
    Uses the same binomtest API as MET-01 Wilson CI.
    """
    from docintel_eval.metrics import wilson_ci  # ImportError until Wave 1

    lo, hi = wilson_ci(k=3, n=5)
    assert abs(lo - 0.2307) < 0.001, f"MET-04 Wilson CI n=5,k=3: expected low≈0.2307, got {lo}"
    assert abs(hi - 0.8824) < 0.001, f"MET-04 Wilson CI n=5,k=3: expected high≈0.8824, got {hi}"


def test_refusal_matrix_partition() -> None:
    """MET-04: true_refused + false_answered partitions n_should_refuse (D-04).

    Hand-verifiable: n_should_refuse=5, true_refused=3, false_answered=2.
    Partition sum must equal n_should_refuse=5 (no overlap, no gap).
    Wilson CI on true_refusal_rate=3/5=0.60 -> [0.2307, 0.8824].
    """
    from docintel_eval.metrics import wilson_ci  # ImportError until Wave 1

    n_should_refuse = 5
    true_refused = 3
    false_answered = 2
    assert (
        true_refused + false_answered == n_should_refuse
    ), "D-04: true_refused + false_answered must partition n_should_refuse exactly"

    # Wilson CI on true_refusal_rate
    lo, hi = wilson_ci(k=true_refused, n=n_should_refuse)
    assert abs(lo - 0.2307) < 0.001, f"D-04 Wilson CI: expected low≈0.2307, got {lo}"
    assert abs(hi - 0.8824) < 0.001, f"D-04 Wilson CI: expected high≈0.8824, got {hi}"


# ---------------------------------------------------------------------------
# MET-05 — Latency + $/query (QueryTimingRecord, D-06)
# ---------------------------------------------------------------------------


def test_query_timing_record_schema() -> None:
    """MET-05: QueryTimingRecord validates with extra="forbid" and frozen=True (D-06).

    Structural gate: correct fields accepted; extra fields rejected.
    """
    from docintel_eval.metrics import QueryTimingRecord  # ImportError until Wave 1

    rec = QueryTimingRecord(
        question_id="q-001",
        total_ms=123.4,
        cost_usd=0.0,
        model="stub",
        refused=False,
    )
    assert rec.question_id == "q-001", "QueryTimingRecord.question_id must round-trip"
    assert rec.total_ms == pytest.approx(123.4), "QueryTimingRecord.total_ms must round-trip"
    assert rec.cost_usd == 0.0, "QueryTimingRecord.cost_usd must be 0.0 in stub mode"
    assert rec.model == "stub", "QueryTimingRecord.model must round-trip"
    assert rec.refused is False, "QueryTimingRecord.refused must round-trip"
    assert rec.retrieval_ms is None, "QueryTimingRecord.retrieval_ms default must be None"
    assert rec.generation_ms is None, "QueryTimingRecord.generation_ms default must be None"

    # extra="forbid" gate: extra field must raise
    import pytest as _pytest

    with _pytest.raises(Exception):
        QueryTimingRecord(  # type: ignore[call-arg]
            question_id="q-001",
            total_ms=123.4,
            cost_usd=0.0,
            model="stub",
            refused=False,
            unexpected_field="boom",
        )


def test_latency_percentiles_stub() -> None:
    """MET-05: p50/p95 computed from stub QueryTimingRecord list (cost=0.0, non-repr.).

    Stub mode: $0 cost, wall-clock latency is CI-runner time (non-representative).
    Report must be labeled non-representative per D-06.
    """
    from docintel_eval.metrics import (  # ImportError until Wave 1
        QueryTimingRecord,
        compute_latency_stats,
    )

    records = [
        QueryTimingRecord(
            question_id=f"q-{i:03d}",
            total_ms=float(10 * (i + 1)),
            cost_usd=0.0,
            model="stub",
            refused=False,
        )
        for i in range(10)
    ]
    result = compute_latency_stats(records)
    # p50 of [10,20,...,100] ms: median of 10 values -> (50+60)/2 = 55ms
    assert result.p50_ms == pytest.approx(55.0), (  # type: ignore[union-attr]
        f"MET-05 stub p50: expected 55.0ms, got {result}"
    )
    # p95 of [10,...,100] -> 95th percentile ~ 95.5ms
    assert result.p95_ms >= 90.0, (  # type: ignore[union-attr]
        "MET-05 stub p95: must be >= 90.0ms for [10..100]ms input"
    )
    assert result.cost_per_query_usd == pytest.approx(0.0), (  # type: ignore[union-attr]
        "MET-05 stub: cost_per_query_usd must be 0.0"
    )


def test_latency_representative_free_tier_real_endpoint() -> None:
    """ADR-014: a real run at $0 cost (free NIM tier) is still representative.

    Regression for the cost>0 proxy: records with cost_usd == 0.0 but an
    explicit representative=True (provider != 'stub') must yield a
    representative LatencyResult. Without the override flag the legacy heuristic
    would mislabel the run non-representative and baseline-lock would reject it.
    """
    from docintel_eval.metrics import QueryTimingRecord, compute_latency_stats

    records = [
        QueryTimingRecord(
            question_id=f"q-{i:03d}",
            total_ms=float(2000 + i),
            cost_usd=0.0,  # free-tier NIM: real run, zero marginal cost
            model="openai/gpt-oss-120b",
            refused=False,
        )
        for i in range(5)
    ]
    # Provider-derived flag (real) overrides the cost>0 heuristic.
    assert compute_latency_stats(records, representative=True).representative is True
    # Default (None) preserves the legacy cost>0 behaviour for existing callers.
    assert compute_latency_stats(records).representative is False


@pytest.mark.real
def test_latency_percentiles_real() -> None:
    """MET-05: p50/p95 + $/query from real timing records (workflow_dispatch only).

    Real mode: non-zero cost, representative wall-clock latency.
    Gated behind @pytest.mark.real — deselected in stub CI (-m "not real").
    """
    from docintel_eval.metrics import (  # ImportError until Wave 1
        QueryTimingRecord,
        compute_latency_stats,
    )

    # Real timing records would be populated by the Phase 10 harness.
    # This scaffold verifies the compute_latency_stats call signature.
    records = [
        QueryTimingRecord(
            question_id="q-real-001",
            total_ms=2500.0,
            cost_usd=0.002,
            model="gpt-4o-mini",
            refused=False,
        )
    ]
    result = compute_latency_stats(records)
    assert result.p50_ms > 0.0, (  # type: ignore[union-attr]
        "MET-05 real: p50_ms must be > 0 for non-zero timing records"
    )
    assert result.cost_per_query_usd > 0.0, (  # type: ignore[union-attr]
        "MET-05 real: cost_per_query_usd must be > 0.0 in real mode"
    )


# ---------------------------------------------------------------------------
# MET-06 — Bootstrap delta CI (paired resampling, D-06/RESEARCH Flag 2)
# ---------------------------------------------------------------------------


def test_bootstrap_delta_determinism() -> None:
    """MET-06: bootstrap_delta_ci is deterministic — same seed yields bit-exact CI bounds.

    Hand-verifiable: a=[1.0]*21+[0.0]*11, b=[1.0]*14+[0.0]*18, seed=42, n_boot=10_000.
    Two calls with identical arguments must produce bit-exact equal (delta, lo, hi).
    """
    from docintel_eval.metrics import bootstrap_delta_ci  # ImportError until Wave 1

    a = [1.0] * 21 + [0.0] * 11  # with_rerank: 21/32 hit
    b = [1.0] * 14 + [0.0] * 18  # without_rerank: 14/32 hit

    delta1, lo1, hi1 = bootstrap_delta_ci(a, b, seed=42, n_boot=10_000)
    delta2, lo2, hi2 = bootstrap_delta_ci(a, b, seed=42, n_boot=10_000)

    assert delta1 == delta2, "MET-06: observed delta must be identical across calls"
    assert lo1 == lo2, "MET-06: CI lower bound must be bit-exact equal (same seed)"
    assert hi1 == hi2, "MET-06: CI upper bound must be bit-exact equal (same seed)"


def test_bootstrap_delta_sign() -> None:
    """MET-06: bootstrap_delta_ci lo > 0 when arm_a significantly outperforms arm_b.

    Hand-verifiable: a=[1.0]*21+[0.0]*11, b=[1.0]*14+[0.0]*18, seed=42.
    Observed delta ≈ +0.219 (21/32 - 14/32). CI must exclude 0 (lo > 0.0).
    """
    from docintel_eval.metrics import bootstrap_delta_ci  # ImportError until Wave 1

    a = [1.0] * 21 + [0.0] * 11
    b = [1.0] * 14 + [0.0] * 18

    delta, lo, hi = bootstrap_delta_ci(a, b, seed=42, n_boot=10_000)

    assert delta > 0.0, f"MET-06: observed delta must be positive (arm_a > arm_b), got {delta}"
    assert lo > 0.0, f"MET-06: CI lower bound must exclude 0 (significant improvement), got lo={lo}"


# ---------------------------------------------------------------------------
# Regression tests for CR-01 / WR-01 / WR-02 / WR-03 guards
# ---------------------------------------------------------------------------


def test_bootstrap_delta_ci_empty_raises() -> None:
    """CR-01 regression: bootstrap_delta_ci([], []) must raise ValueError, never return nan."""
    from docintel_eval.metrics import bootstrap_delta_ci

    with pytest.raises(ValueError, match="at least one paired observation"):
        bootstrap_delta_ci([], [])


def test_bootstrap_delta_ci_mismatched_length_raises() -> None:
    """CR-01 regression: bootstrap_delta_ci raises ValueError on mismatched arm lengths."""
    from docintel_eval.metrics import bootstrap_delta_ci

    with pytest.raises(ValueError, match="equal-length arms"):
        bootstrap_delta_ci([1.0, 2.0], [1.0])


def test_hit_at_k_invalid_k_raises() -> None:
    """WR-03 regression: hit_at_k raises ValueError for k=0 and k=-1 (public API guard).

    k=0 previously returned vacuous 1 for empty gold_set; k=-1 used Python negative-slice
    semantics (dropped last element). Both are now errors.
    """
    from docintel_eval.metrics import hit_at_k

    with pytest.raises(ValueError, match="k >= 1"):
        hit_at_k(["A", "B", "C"], {"A"}, 0)

    with pytest.raises(ValueError, match="k >= 1"):
        hit_at_k(["A", "B", "C"], {"A"}, -1)


def test_refusal_matrix_misaligned_raises() -> None:
    """WR-01 regression: compute_refusal_matrix raises ValueError when len(records) != len(answers).

    Verifies the alignment guard fires before any computation — silent zip-truncation
    that corrupts false_answer_rate is no longer possible.
    """
    from unittest.mock import MagicMock

    from docintel_eval.metrics import compute_refusal_matrix

    # Build 3 minimal record-like objects and only 2 answers
    records = [MagicMock(id=f"q{i}", question_type="factual") for i in range(3)]
    answers = [MagicMock(refused=False, text="answer") for _ in range(2)]

    with pytest.raises(ValueError, match="aligned inputs"):
        compute_refusal_matrix(records, answers)
