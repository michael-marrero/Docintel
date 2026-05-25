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
]
