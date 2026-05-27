"""docintel-eval ablate module: single-process ablation orchestration.

Phase 11 ablation orchestration spine (ABL-01 component-arm half; D-01/D-02/D-03/L-01).

run_ablations(cfg, *, output_dir=None) -> int:
  - D-01: runs baseline + no-rerank + dense-only in ONE process so every arm
    shares one git SHA, one dataset hash, and one RNG seed (a valid paired
    bootstrap is computed by Plan 03 from the per-arm sidecars this emits).
  - D-02 (HARD): every arm calls the IDENTICAL Phase-10 measurement path via
    run_eval arm injection (the optional `generator` kwarg) — no forked
    per-question loop, no forked metric math, no second results.json schema.
  - D-03: fixed arm set, no --arms knob; the baseline arm is ALWAYS freshly
    re-built here (never a stale committed baseline).
  - L-01 / CD-08: the no-rerank arm swaps NullReranker into the AdapterBundle and
    the dense-only arm swaps NullBM25Store into the IndexStoreBundle; both then
    construct the Retriever directly (the CD-08 seam) instead of via the factory
    helper. The Retriever hot path stays branch-free — "the swap IS the artifact".
  - L-04: stub deltas are honest (≈0; stubs are component-insensitive). This
    module computes NO deltas — that is Plan 03 reading these per-arm sidecars.

Delta computation, the comparison table, and the extended validate gate are
Plan 03; this module stops at producing per-arm results.json/report.md sidecars
under data/eval/ablations/<one-shared-ts>/<arm>/.

Pitfall 2: each arm builds its generator ONCE and run_eval reuses
generator._retriever — the factory retriever helper is never called per question.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog
from docintel_core.adapters.factory import (
    make_adapters,
    make_generator,
    make_index_stores,
)
from docintel_core.adapters.types import AdapterBundle, IndexStoreBundle
from docintel_core.config import Settings
from docintel_generate.generator import Generator
from docintel_retrieve.null_adapters import NullBM25Store, NullReranker
from docintel_retrieve.retriever import Retriever

from docintel_eval.runner import run_eval

log = structlog.stdlib.get_logger(__name__)

__all__ = ["run_ablations"]


# ---------------------------------------------------------------------------
# Arm builders (L-01 / CD-08) — swap ONE null adapter, construct Retriever
# directly, wrap in a Generator carrying the SAME swapped bundle so the per-arm
# manifest reflects the swap. make_generator composes two adapter bundles
# internally (the factory builds a fresh bundle for the retriever) — so arms
# must NOT reuse a baseline generator's retriever; they build their own retriever
# against the swapped bundle/stores via the CD-08 direct-construction seam.
# ---------------------------------------------------------------------------


def _build_no_rerank_generator(cfg: Settings) -> Generator:
    """Build the no-rerank arm generator (NullReranker swapped into the bundle).

    Constructs a fresh AdapterBundle with reranker=NullReranker() (the other
    three adapters reused from make_adapters), builds the index stores normally,
    and constructs Retriever directly (CD-08). The returned Generator carries the
    swapped bundle so its manifest reranker_name is "null-reranker". NullReranker
    preserves RRF order, so top-K = top-M of the fused list (the no-rerank
    ablation semantics) with no branch in Retriever.search (L-01).
    """
    base = make_adapters(cfg)
    bundle = AdapterBundle(
        embedder=base.embedder,
        reranker=NullReranker(),
        llm=base.llm,
        judge=base.judge,
    )
    stores = make_index_stores(cfg)
    retriever = Retriever(bundle=bundle, stores=stores, cfg=cfg)
    return Generator(bundle=bundle, retriever=retriever)


def _build_dense_only_generator(cfg: Settings) -> Generator:
    """Build the dense-only arm generator (NullBM25Store swapped into the stores).

    Builds the AdapterBundle normally, then constructs a fresh IndexStoreBundle
    with bm25=NullBM25Store() (dense reused from make_index_stores) and a
    Retriever directly (CD-08). NullBM25Store.query returns [], so RRF degenerates
    to the single dense ranker's ordering (the dense-only ablation semantics) with
    no branch in Retriever.search (L-01).
    """
    bundle = make_adapters(cfg)
    base_stores = make_index_stores(cfg)
    stores = IndexStoreBundle(dense=base_stores.dense, bm25=NullBM25Store())
    retriever = Retriever(bundle=bundle, stores=stores, cfg=cfg)
    return Generator(bundle=bundle, retriever=retriever)


# ---------------------------------------------------------------------------
# Orchestrator (D-01 / D-02 / D-03)
# ---------------------------------------------------------------------------


def run_ablations(cfg: Settings, *, output_dir: Path | None = None) -> int:
    """Run baseline + component ablation arms in ONE process (D-01).

    Builds the fixed arm set (D-03 — no knobs) and calls run_eval once per arm
    with the arm's pre-built generator injected (D-02 identical path). Each arm
    writes a Phase-10 results.json/report.md sidecar under
    data/eval/ablations/<ts>/<arm>/. Delta computation + the comparison table +
    the top-level ablation manifest are Plan 03 (this leaves the per-arm sidecars
    for Plan 03 to read).

    Args:
        cfg:        Settings instance (FND-11 — the only env-read site; this
                    function never re-reads env).
        output_dir: Override root directory. When None, uses
                    data/eval/ablations/<YYYYMMDD_HHMMSS_%fZ>/ (D-08; a tracked
                    sibling of reports/). Tests pass a tmp_path here so the run
                    does not pollute the tracked tree (T-11-01).

    Returns:
        0 when every arm's run_eval returned 0; 1 if any arm failed.
    """
    # (a) ONE timestamp + ONE root shared by every arm (D-01 single-process
    # identity; Pitfall 6 — all arms land under one top-level run dir rather
    # than each run_eval minting its own timestamp).
    ts: str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%fZ")
    root: Path = output_dir if output_dir is not None else Path("data/eval/ablations") / ts
    root.mkdir(parents=True, exist_ok=True)

    # (b) Build the arm generators in fixed order (D-03 — no --arms knob). Each
    # generator is built ONCE here, before its run_eval (Pitfall 2). The baseline
    # is ALWAYS freshly built (D-03 — never a stale committed baseline).
    arm_generators: dict[str, Generator] = {
        "baseline": make_generator(cfg),
        "no-rerank": _build_no_rerank_generator(cfg),
        "dense-only": _build_dense_only_generator(cfg),
    }
    # Plan 04 extends: real-mode chunk-300/450/600 arms appended when
    # cfg.llm_provider == real (re-chunk -> re-embed -> re-index; D-04/D-05).

    # (c) Run the identical Phase-10 path once per arm (D-02). run_eval reuses
    # each arm's warm generator._retriever (Pitfall 2 — no per-question rebuild).
    arm_names: list[str] = list(arm_generators)
    for name, gen in arm_generators.items():
        exit_code: int = run_eval(cfg, generator=gen, output_dir=root / name)
        if exit_code != 0:
            log.error(
                "ablate_arm_failed",
                arm=name,
                exit_code=exit_code,
                root=str(root),
                provider=str(cfg.llm_provider),
            )
            return 1

    # (d) Structured completion log. Delta computation + comparison table +
    # top-level manifest are Plan 03.
    log.info(
        "ablate_arms_completed",
        arms=arm_names,
        root=str(root),
        provider=str(cfg.llm_provider),
    )
    return 0
