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
  - L-04: stub deltas are honest (≈0; stubs are component-insensitive). The
    deltas are computed from real per-arm sidecars, never fabricated; the stub
    combined manifest carries representative:false.

After the per-arm run_eval loop (Plan 02 spine), this module (Plan 03):
  - L-02/L-03: aligns each non-baseline arm's per_question[] to the baseline by
    id and calls the frozen bootstrap_delta_ci(arm, baseline, n_boot=10_000,
    seed=42) per headline metric (hit_at_5, hit_at_3, reciprocal_rank). NO new
    metric math — the bootstrap is reused verbatim.
  - D-08: writes ONE top-level ablation-manifest.json (shared git_sha /
    dataset_hash / seed, arm list, an arm_components provenance map, and the
    deltas dict) serialized with sort_keys=True + trailing newline so two stub
    runs are byte-identical (the D-11 determinism gate).
  - D-06/D-07: calls the pure render_ablation_markdown and writes the top-level
    ablation-report.md comparison table.

The per-arm results.json sidecars stay EXACTLY as render_results_json wrote them
(unchanged Phase-10 schema — L-03 composability; the arm_components provenance
lives ONLY in the top-level ablation manifest, never forked into a sidecar; W#2).

Pitfall 2: each arm builds its generator ONCE and run_eval reuses
generator._retriever — the factory retriever helper is never called per question.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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

from docintel_eval.metrics import bootstrap_delta_ci
from docintel_eval.report import render_ablation_markdown
from docintel_eval.runner import _STUB_GIT_SHA, _dataset_hash, _git_sha, run_eval

log = structlog.stdlib.get_logger(__name__)

__all__ = ["provider_is_real", "run_ablations"]

# Headline retrieval metrics that carry a paired-bootstrap (delta, lo, hi) per
# non-baseline arm (D-06). Hit@3 ties the no-rerank arm to Phase 5's reranker
# canary. These three are computed from rankings and are honest (≈0) in stub.
_HEADLINE_METRICS: tuple[str, ...] = ("hit_at_5", "hit_at_3", "reciprocal_rank")

# Locked paired-bootstrap parameters (L-02). seed=42 is the determinism contract
# the D-11 validate recompute depends on.
_N_BOOT: int = 10_000
_SEED: int = 42

# Ground-truth eval set file — the shared dataset whose sha256 stamps every arm
# (D-01 single-process identity; reuse runner._dataset_hash).
_EVAL_SET_PATH: Path = Path("data/eval/ground_truth/eval_set.jsonl")

# ---------------------------------------------------------------------------
# Chunk-size sweep (D-04 / D-05) — the third ABL-01 ablation. Unlike no-rerank /
# dense-only there is NO adapter to swap: a smaller/larger chunk size forces a
# re-chunk -> re-embed -> re-index, so each swept size has its OWN pre-built
# index. `make ablate-chunk-sweep` builds those size-specific indices under
# data/indices/chunk-<S>/ (gitignored, A3) BEFORE the real ablation run; this
# module only CONSUMES them (it never re-chunks/re-indexes itself). The sweep is
# real-mode / workflow_dispatch-ONLY (D-04): in stub mode no chunk arms are
# appended and `chunk_sizes` stays empty (the committed stub sample is the
# 3-arm baseline+no-rerank+dense-only set, unchanged).
# ---------------------------------------------------------------------------

# Swept greedy-split sizes (D-05; ±~33% around the production 450). 450 is the
# production baseline and reuses the production corpus/index (the Makefile's
# `ablate-chunk-sweep` short-circuits 450 — no rebuild), so its arm points at the
# unmodified cfg roots. 300/600 point at their size-specific build roots.
_CHUNK_SWEEP_SIZES: tuple[int, ...] = (300, 450, 600)

# The production greedy-split size (docintel_ingest.chunk.TARGET_TOKENS). The 450
# chunk arm reuses the production corpus/index rather than a size-specific root.
_PRODUCTION_TARGET_TOKENS: int = 450

# Per-size build root produced by `make ablate-chunk-sweep` (Makefile:125-141).
# The size data root holds corpus/chunks + a size-S corpus MANIFEST; the size
# index root holds dense/bm25 + MANIFEST.json. The Retriever reads cfg.data_dir
# (corpus/chunks + chunk map) and cfg.index_dir (MANIFEST.json + stores), so a
# chunk arm is simply make_generator() against a Settings whose two path fields
# point at this size root.
_CHUNK_INDEX_ROOT: Path = Path("data/indices")


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
# Chunk-size sweep arm builders (D-04 / D-05) — NOT an adapter swap; each arm
# points at a DISTINCT pre-built size-specific index.
# ---------------------------------------------------------------------------


def provider_is_real(cfg: Settings) -> bool:
    """True iff the chunk-size sweep arms must be appended (real mode, D-04).

    The sweep is real-mode / workflow_dispatch-ONLY: in stub mode the arm set
    stays baseline+no-rerank+dense-only and `chunk_sizes` stays empty (stubs are
    chunk-insensitive, so a sweep would be a non-representative no-op — the same
    real-only stance D-04 takes on latency/$). Centralised so the real-mode gate
    is a single named predicate the wiring test can force.
    """
    return str(cfg.llm_provider) != "stub"


def _chunk_arm_data_dir(cfg: Settings, size: int) -> Path:
    """Return the data root a chunk arm reads (corpus/chunks + corpus MANIFEST).

    The production size (450) reuses the production corpus (cfg.data_dir) — the
    Makefile sweep target short-circuits 450 and never builds a chunk-450 root.
    Other sizes read the size-specific root `data/indices/chunk-<S>/data` that
    `make ablate-chunk-sweep` writes (re-chunked at <S>, symlinked raw/normalized).
    """
    if size == _PRODUCTION_TARGET_TOKENS:
        return Path(cfg.data_dir)
    return _CHUNK_INDEX_ROOT / f"chunk-{size}" / "data"


def _chunk_arm_index_dir(cfg: Settings, size: int) -> Path:
    """Return the index root a chunk arm reads (MANIFEST.json + dense/bm25 stores).

    The production size (450) reuses the production index (cfg.index_dir). Other
    sizes read `data/indices/chunk-<S>/index` (built by `make ablate-chunk-sweep`).
    """
    if size == _PRODUCTION_TARGET_TOKENS:
        return Path(cfg.index_dir)
    return _CHUNK_INDEX_ROOT / f"chunk-{size}" / "index"


def _require_chunk_index(index_dir: Path, size: int) -> Path:
    """Assert a size-specific index exists; fail LOUDLY otherwise (no silent skip).

    A missing size index almost always means `make ablate-chunk-sweep` was not
    run before `docintel-eval ablate` (the workflow_dispatch real-ablation job
    runs them in that order). Silently dropping the arm would re-introduce the
    exact masked gap the verifier flagged (a real run that quietly produces a
    chunk-less report), so this raises with the missing dir + the build step.

    Returns:
        The index MANIFEST.json path (existence-checked) for identity hashing.

    Raises:
        FileNotFoundError: the size index dir or its MANIFEST.json is absent.
    """
    manifest_path = index_dir / "MANIFEST.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"chunk-{size} ablation arm requires a pre-built size-specific index at "
            f"{index_dir} (MANIFEST.json missing). Run `make ablate-chunk-sweep` "
            f"(real-mode only) to re-chunk -> re-embed -> re-index at "
            f"{_CHUNK_SWEEP_SIZES} BEFORE `docintel-eval ablate`. The chunk-size "
            f"sweep is workflow_dispatch-only (D-04); it is never built on a PR."
        )
    return manifest_path


def _chunk_index_identity(manifest_path: Path) -> str:
    """Read a size index's corpus-identity hash from its MANIFEST.json (D-05).

    Each swept size has a distinct `chunker.target_tokens` in its corpus
    MANIFEST -> a distinct `corpus_manifest_sha256` recorded in its index
    MANIFEST.json (docintel_index.build writes it). Recording that hash per
    chunk arm is the per-index provenance the ablation manifest carries so a real
    run is reproducible (mirrors how arm_components records the swapped-adapter
    identity for the no-rerank/dense-only arms — provenance as DATA, W#2).
    """
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    identity = payload.get("corpus_manifest_sha256")
    return str(identity) if identity is not None else ""


def _build_chunk_arm_generator(cfg: Settings, size: int) -> Generator:
    """Build a chunk-size arm generator pointed at that size's pre-built index.

    No adapter is swapped — the ablation IS the alternate chunking, so the arm is
    just ``make_generator`` against a Settings whose ``data_dir`` / ``index_dir``
    point at the size-specific build root (``model_copy`` keeps every other field
    — provider, keys, qdrant — identical so the ONLY difference vs baseline is the
    chunk size). The arm flows through the IDENTICAL run_eval path (D-02); its
    generator._retriever is reused per question (Pitfall 2), exactly like the
    component arms. For the production size (450) this reuses ``cfg`` unchanged.
    """
    data_dir = _chunk_arm_data_dir(cfg, size)
    index_dir = _chunk_arm_index_dir(cfg, size)
    _require_chunk_index(index_dir, size)
    arm_cfg = cfg.model_copy(update={"data_dir": str(data_dir), "index_dir": str(index_dir)})
    return make_generator(arm_cfg)


# ---------------------------------------------------------------------------
# Delta extraction + provenance helpers (L-02 / L-03 / W#2)
# ---------------------------------------------------------------------------


def _arm_component_identity(gen: Generator) -> dict[str, str]:
    """Read an arm's swapped-component identity from its generator (W#2).

    The degradation provenance is recorded as DATA — the reranker + bm25 adapter
    names read off the bundle/stores at arm-construction time — so the dense-only
    arm records bm25="null-bm25" and the no-rerank arm records
    reranker="null-reranker" without the validate/reader inferring it from the
    dir name. This lives ONLY in the top-level ablation manifest; the per-arm
    Phase-10 results.json sidecar is NOT forked to carry it (D-02 / L-03).
    """
    return {
        "reranker": gen._bundle.reranker.name,
        "bm25": gen._retriever._stores.bm25.name,
    }


def _read_per_question(arm_root: Path) -> dict[str, dict[str, Any]]:
    """Read an arm's results.json per_question[] and index it by id (L-03).

    Returns {id -> row}. The caller iterates a SINGLE sorted id order taken from
    the baseline arm so every arm's metric column is equal-length and aligned by
    id (Pitfall 5 — bootstrap_delta_ci raises on unequal-length arms).
    """
    payload = json.loads((arm_root / "results.json").read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = payload["per_question"]
    by_id: dict[str, dict[str, Any]] = {str(row["id"]): row for row in rows}
    # Assert id uniqueness. A duplicate id (corrupt/mis-generated ground truth)
    # would silently collapse rows here; because every arm collapses identically
    # the columns stay equal-length and bootstrap_delta_ci never raises — so the
    # ablation would silently compute deltas over a SUBSET of questions. GT-02
    # should prevent dup ids upstream, but eval-integrity infrastructure must not
    # silently subset the comparison set.
    if len(by_id) != len(rows):
        raise ValueError(
            f"duplicate question id in {arm_root / 'results.json'} "
            f"({len(rows)} rows, {len(by_id)} unique)"
        )
    return by_id


def _mean(values: list[float]) -> float:
    """Arithmetic mean of a non-empty column (the table value cell, not new math).

    This is the value column the comparison table renders for each headline
    metric; it equals mean(arm) so value_arm - value_baseline == observed_delta
    (bootstrap_delta_ci returns mean(a) - mean(b)). No metric is recomputed —
    Hit@K / MRR are already in per_question[]; this only averages that column.
    """
    return sum(values) / len(values)


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

    # Capture the per-arm swapped-component identity as DATA at construction time
    # (W#2 — read off the bundle/stores, NOT inferred from the dir name). This is
    # the degradation provenance recorded ONLY in the top-level manifest.
    arm_components: dict[str, dict[str, str]] = {
        name: _arm_component_identity(gen) for name, gen in arm_generators.items()
    }

    # (b2) Chunk-size sweep arms (D-04 / D-05) — REAL-MODE ONLY. The chunk sweep
    # has no adapter seam (a smaller chunk size forces a re-chunk -> re-embed ->
    # re-index), so each swept size is built ahead of time by
    # `make ablate-chunk-sweep` (workflow_dispatch-only) and CONSUMED here. In
    # stub mode this branch is skipped entirely: the arm set stays the three
    # component arms and `chunk_sizes` stays empty (the committed stub sample is
    # the 3-arm set, unchanged — stubs are chunk-insensitive so a chunk sweep
    # would be a non-representative no-op, mirroring D-04's real-only stance on
    # latency/$). Each chunk arm flows through the IDENTICAL run_eval path (D-02);
    # the only difference vs baseline is which size-specific index it reads.
    chunk_sizes: list[int] = []
    chunk_index_identity_hashes: dict[str, str] = {}
    if provider_is_real(cfg):
        for size in _CHUNK_SWEEP_SIZES:
            arm_name = f"chunk-{size}"
            gen = _build_chunk_arm_generator(cfg, size)
            arm_generators[arm_name] = gen
            chunk_sizes.append(size)
            # Per-index provenance (D-05): record the size + its corpus-identity
            # hash (read from the size index's MANIFEST.json). For the production
            # 450 arm this is the production index's hash; for 300/600 it is the
            # size-specific build's distinct hash.
            identity = _chunk_index_identity(_chunk_arm_index_dir(cfg, size) / "MANIFEST.json")
            chunk_index_identity_hashes[arm_name] = identity
            # The chunk arm's provenance IS its chunk size + index identity (no
            # adapter swap), recorded as DATA alongside the component arms (W#2).
            arm_components[arm_name] = {
                "target_tokens": str(size),
                "index_identity": identity,
            }

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

    # (d) Paired deltas (L-02 / L-03). Read each arm's per_question[] sidecar,
    # build ONE sorted id order from the baseline arm, and index every arm by it
    # so the metric columns are equal-length and id-aligned (Pitfall 5). For each
    # non-baseline arm x headline metric call the frozen bootstrap_delta_ci with
    # the locked (n_boot=10_000, seed=42) contract — convention delta = arm -
    # baseline. NO new metric math: Hit@K / MRR already live in per_question[].
    baseline_name: str = arm_names[0]
    arm_rows: dict[str, dict[str, dict[str, Any]]] = {
        name: _read_per_question(root / name) for name in arm_names
    }
    ids: list[str] = sorted(arm_rows[baseline_name])

    arm_metrics: dict[str, dict[str, float]] = {}
    for name in arm_names:
        rows_by_id = arm_rows[name]
        arm_metrics[name] = {
            metric: _mean([float(rows_by_id[i][metric]) for i in ids])
            for metric in _HEADLINE_METRICS
        }

    deltas: dict[str, dict[str, list[float]]] = {}
    for name in arm_names:
        if name == baseline_name:
            continue
        arm_by_id = arm_rows[name]
        deltas[name] = {}
        for metric in _HEADLINE_METRICS:
            arm_col: list[float] = [float(arm_by_id[i][metric]) for i in ids]
            base_col: list[float] = [float(arm_rows[baseline_name][i][metric]) for i in ids]
            observed_delta, ci_low, ci_high = bootstrap_delta_ci(
                arm_col, base_col, n_boot=_N_BOOT, seed=_SEED
            )
            deltas[name][metric] = [observed_delta, ci_low, ci_high]

    # (e) Top-level combined ablation manifest (D-08 — one manifest, arms as
    # rows). Shared git_sha + dataset_hash + seed (D-01 single-process identity;
    # reuse runner._git_sha / runner._dataset_hash). representative derived like
    # runner.py: stub arms have no cost, so stub is non-representative (L-04).
    # D-11: in stub mode the git SHA is replaced with the deterministic sentinel
    # (same one the per-arm sidecars use) so the top-level manifest is
    # byte-reproducible and never attests to a dirty/untracked source commit —
    # mirrors how run_eval normalizes stub-mode provenance.
    provider: str = str(cfg.llm_provider)
    representative: bool = provider != "stub"
    manifest: dict[str, Any] = {
        "git_sha": _STUB_GIT_SHA if provider == "stub" else _git_sha(),
        "dataset_hash": _dataset_hash(_EVAL_SET_PATH),
        "seed": _SEED,
        "n_boot": _N_BOOT,
        "provider": provider,
        "representative": representative,
        "baseline": baseline_name,
        "arm_names": arm_names,
        "headline_metrics": list(_HEADLINE_METRICS),
        "arm_components": arm_components,
        "arms": {
            name: {
                "components": arm_components[name],
                "metrics": arm_metrics[name],
                "deltas": deltas.get(name, {}),
            }
            for name in arm_names
        },
        "deltas": deltas,
        # Chunk-size sweep provenance (D-05). Real-mode only: `chunk_sizes` is the
        # list of swept greedy-split sizes actually run (e.g. [300, 450, 600]) and
        # `index_identity_hashes` maps each chunk arm to its size index's
        # corpus-identity hash. In stub mode both stay empty (no chunk arms — the
        # sweep is workflow_dispatch-only, D-04).
        "chunk_sizes": chunk_sizes,
        "index_identity_hashes": chunk_index_identity_hashes,
    }
    # Deterministic serialization: sort_keys + trailing newline so two stub runs
    # are byte-identical (the D-11 determinism gate).
    (root / "ablation-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # (f) Comparison table (D-06 / D-07). render_ablation_markdown is pure — it
    # only formats the (delta, lo, hi) tuples computed above (no bootstrap call
    # in report.py).
    report_md: str = render_ablation_markdown(
        arm_names, arm_metrics, deltas, provider=provider
    )
    (root / "ablation-report.md").write_text(report_md + "\n", encoding="utf-8")

    # (g) Structured completion log.
    log.info(
        "ablate_arms_completed",
        arms=arm_names,
        root=str(root),
        provider=provider,
        representative=representative,
    )
    return 0
