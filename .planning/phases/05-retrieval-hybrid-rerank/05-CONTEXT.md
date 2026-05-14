# Phase 5: retrieval-hybrid-rerank - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship the query-time retrieval pipeline that takes a user question and returns the top-K most relevant chunks from the corpus, ready for Phase 6's generator. The pipeline is hybrid + reranked: BM25 (lexical) and dense (semantic) each return top-N candidates from the Phase 4 indices, Reciprocal Rank Fusion combines them into a single ranking, and the BGE cross-encoder reranks the top-M of that fused set into the final top-K. Phase 5 also carries the **silent-truncation canary** (RET-03) as a STRUCTURAL ACCEPTANCE GATE: ≥5 hand-written cases where the rerank pipeline measurably out-hits dense-only at top-3. Phase 6 generation, Phase 9 metrics, Phase 10 eval harness, Phase 11 ablations, and Phase 13 API all import through Phase 5's `Retriever.search()` seam.

Closes: RET-01..RET-04.

**Out of scope (do not invent here):**
- Generation, prompt module, refusal path — Phase 6 (GEN-01..04). Phase 5 returns retrieved chunks; Phase 6 turns them into an answer.
- `Answer` / `Citation` Pydantic schema — Phase 7 (ANS-01..03). Phase 5 carries the raw citation anchor fields (`ticker`, `fiscal_year`, `item_code`, `char_span_in_section`) on each `RetrievedChunk`; Phase 7 wraps them into a `Citation`.
- Ground-truth eval set — Phase 8 (GT-01..03). The 5+ canary cases (RET-03) are NOT the eval set — they are a Phase 5 acceptance gate. Phase 8 ships a broader ≥30-question set with three question types.
- Hit@K / MRR / faithfulness / latency / $/query metrics — Phase 9 (MET-01..06). Phase 5 emits per-stage `structlog` timings (`bm25_ms`, `dense_ms`, `fuse_ms`, `rerank_ms`); Phase 9 aggregates them into MET-05.
- Eval harness CLI + report writer — Phase 10 (EVAL-01..04). The canary test runs under `pytest`; Phase 10's eval harness reuses the same `Retriever` via `make_retriever(cfg)`.
- Ablation experiments (no-rerank, dense-only, chunk-size sweep) — Phase 11 (ABL-01..02). Phase 5 lays the SEAM (null adapter swap; see D-08) so Phase 11 can construct an ablated `Retriever` without touching `Retriever.search()`.
- `trace_id` propagation via `structlog.contextvars` — Phase 12 (OBS-01). Phase 5 emits structured log lines so Phase 12 only needs to bind `trace_id` upstream — no instrumentation retrofit required.
- HTTP `/query` endpoint, Streamlit UI tab — Phase 13 (UI-01..06). Phase 13's API consumes `Retriever.search()`.
- Streaming retrieval / async API — Phase 2 D-08 locked sync-only for v1.
- Multi-modal / table-aware retrieval — V2-01 / V2-02 in REQUIREMENTS.md.
- Query rewriting / HyDE — V2-03 in REQUIREMENTS.md.

</domain>

<decisions>
## Implementation Decisions

### Retrieval API surface + code home

- **D-01:** **New 7th workspace package `docintel-retrieve`** at `packages/docintel-retrieve/`. Mirrors the Phase 3 (`docintel-ingest`) and Phase 4 (`docintel-index`) precedents — every phase that ships a query-time or build-time domain owns its own workspace package. Module layout (planner refines):
  - `packages/docintel-retrieve/pyproject.toml` — pins `docintel-core` workspace dep (transitive `bm25s`/`qdrant-client`/`sentence-transformers` via core's adapter deps) + `numpy` (explicit re-pin).
  - `packages/docintel-retrieve/src/docintel_retrieve/__init__.py`
  - `packages/docintel-retrieve/src/docintel_retrieve/retriever.py` — `Retriever` class with `.search(query, k) -> list[RetrievedChunk]`.
  - `packages/docintel-retrieve/src/docintel_retrieve/types.py` — `RetrievedChunk` Pydantic model (CD-02 below covers a possible move to `docintel_core.types`).
  - `packages/docintel-retrieve/src/docintel_retrieve/fuse.py` — RRF implementation (`rrf_fuse(bm25_ranks, dense_ranks, k=60) -> list[(chunk_id, rrf_score)]`).
  - `packages/docintel-retrieve/src/docintel_retrieve/null_adapters.py` — `NullReranker` + `NullBM25Store` for Phase 11 ablation swaps (D-08 below).
  - `packages/docintel-retrieve/src/docintel_retrieve/py.typed` (PEP 561).
  - Workspace pyproject's `packages/*` glob picks it up automatically.

- **D-02:** **Single seam: `Retriever.search(query: str, k: int) -> list[RetrievedChunk]`.** One callable, end-to-end (BM25 → dense → RRF → rerank → top-K). Phase 6 calls `.search()`; Phase 10 wraps it; Phase 13 awaits it (sync-wrapped per Phase 2 D-08); Phase 11 swaps the `Retriever` instance for ablations. NOT a two-stage `.candidates()` + `.rerank()` public surface — every caller having to glue two calls together is a footgun (someone WILL forget the second call and ship dense-only by accident). Per-stage telemetry is emitted via `structlog` from inside `search()` (D-11), not by giving callers staged hooks. Internal staged methods (`_bm25_candidates`, `_dense_candidates`, `_fuse`, `_rerank`) are still testable as private methods.

- **D-03:** **`RetrievedChunk` is minimal:**
  ```python
  class RetrievedChunk(BaseModel):
      chunk_id: str
      text: str
      score: float                          # final reranker score (or RRF score in no-rerank ablation)
      ticker: str
      fiscal_year: int
      item_code: str                        # e.g., "Item 1A"
      char_span_in_section: tuple[int, int] # citation anchor (Phase 3 D-16)
  ```
  Exactly what Phase 6 needs to build a prompt and what Phase 7's `Citation` will consume. NO per-stage debug fields (`bm25_rank`, `dense_rank`, `rrf_score`, `rerank_score`) on the public shape — keeps the API JSON in Phase 13 clean and stops Phase 6 from reading past fields it doesn't need. Per-stage debug data is emitted via `structlog` (D-11) and Phase 11 ablation reports source it from the log stream, not from the result objects.

- **D-04:** **`make_retriever(cfg) -> Retriever` factory in `docintel_core.adapters.factory`** — third sibling factory alongside `make_adapters(cfg)` (Phase 2 D-13) and `make_index_stores(cfg)` (Phase 4 D-03). Reads `cfg.llm_provider` for the lazy-import discipline (D-12 in Phase 2), internally calls `make_adapters(cfg)` for the embedder + reranker and `make_index_stores(cfg)` for the dense + BM25 stores, then constructs `Retriever(bundle=adapters, stores=stores)`. Phase 6 / 9 / 10 / 13 all use the factory; tests + Phase 11 ablations use the public `Retriever(bundle, stores)` constructor directly so they can inject null adapters (D-08). Factory lives in `docintel_core.adapters.factory` (NOT in `docintel-retrieve`) so the import direction matches every prior phase: `docintel-retrieve` imports from `docintel-core`, never the reverse.

### Pipeline parameters

- **D-05:** **Per-retriever top-N = 100** (BM25 returns top-100, Dense returns top-100). RRF then fuses up to 200 ranked entries (with overlap typical in hybrid retrieval, the unique-chunk set is usually 120–180). Cost on 6,053 chunks: BM25 sub-50ms, NumPy dense sub-10ms — well within the per-query budget. The recall payoff at 100 vs 50 is meaningful when the corpus has near-duplicate prose (10-K boilerplate); 200 was rejected as diminishing returns at 6k chunks.

- **D-06:** **Reranker top-M = 20, final top-K = 5.** The top-20 RRF-fused candidates go into `Reranker.rerank(query, [chunk.text for chunk in candidates])`; the top-5 reranked chunks are returned to the caller. Bottlenecks:
  - bge-reranker-base on CPU ≈ 20 ms per (query, chunk) pair → 20 pairs ≈ 0.4 s. Predictable; OK for both stub-mode CI and real-mode eval runs.
  - K=5 is enough headroom over the canary's "top-3 hit" criterion (RET-03) — gives generation a 5-chunk context block without diluting the prompt past the demo question's needs.
  Both M and K are pinned as module-level constants in `retriever.py` (`TOP_N_PER_RETRIEVER = 100`, `TOP_M_RERANK = 20`, `TOP_K_FINAL = 5`). NOT Settings fields — ablation seams use null adapters / direct construction (D-08), not env-var sweeps.

- **D-07:** **RRF constant k = 60, pinned module constant in `fuse.py`** (`RRF_K = 60`). Cormack et al. 2009 default. This is the value the literature compares against, and the value Phase 13's `DECISIONS.md` ADR will defend. Grep-able from a code review. NOT exposed as a Settings field — if Phase 11 ever wants to sweep k, it constructs a `Retriever` with a custom `_rrf_fuse` injection, same pattern as the null-adapter ablations (D-08).

- **D-08:** **Ablation seams via null adapter classes** in `docintel_retrieve.null_adapters`:
  - `NullReranker` — satisfies `Reranker` protocol; `rerank(query, docs)` returns `docs` wrapped as `RerankedDoc` with `score = original_rank * -1.0` (preserves input order). Phase 11's no-rerank ablation builds `AdapterBundle(reranker=NullReranker(), ...)` and constructs `Retriever(bundle=..., stores=...)`.
  - `NullBM25Store` — satisfies `BM25Store` protocol; `query(text, k)` returns `[]`. Phase 11's dense-only ablation builds `IndexStoreBundle(bm25=NullBM25Store(), ...)`.
  - These two classes ship in `docintel-retrieve` alongside `Retriever` because they're tools for the same downstream phase. NO conditional flags in `Retriever.search` — zero branching in the hot path; ablations are an "adapter swap" not a "behavior toggle".

### Reranker input + silent-truncation defenses (canary preconditions)

- **D-09:** **Reranker input = raw `chunk.text` verbatim.** No prefix (`item_title`-prepending breaks the 12-token safety margin), no truncation, no preprocessing. The chain of custody is: Phase 3 D-11 capped chunks at 500 BGE tokens (hard cap, build-fails-if-exceeded), and bge-reranker-base shares vocab with bge-small-en-v1.5 so the token count is identical → 12-token margin under reranker's 512 cap → no truncation possible if Phase 3's invariant holds. The canary's whole job (RET-03) is to surface a regression in that invariant.

- **D-10:** **Pre-rerank assertion: `assert chunk.n_tokens <= 500`** for every candidate in the rerank loop. `Chunk.n_tokens` is populated by Phase 3 (D-15 schema); it's a zero-cost integer comparison. If a chunk ever exceeds 500, `AssertionError` fires in the rerank loop with a message that names the offending `chunk_id` AND quotes CLAUDE.md's "BGE 512-token truncation FIRST" rule. This is the canary's structural defense at the rerank seam — Phase 3's chunker enforces the invariant at chunk-build time; Phase 5 re-verifies it at retrieval time. (Defense in depth across phase boundaries.)

- **D-11:** **Hard cap on query at 64 BGE tokens with explicit truncation + structlog warning.** Real user queries are sub-50 tokens typically. The cap is defensive: a long query (accidentally pasted prose, abuse) would itself consume the reranker's 512-token budget, forcing the chunk side into truncation that LOOKS like a Phase 3 bug. Truncating at 64 tokens with a structlog line (`retriever_query_truncated`, `original_tokens=N`, `truncated_to=64`) means:
  - The truncation is visible (loud, not silent).
  - The chunk side keeps its full 500-token budget.
  - The canary stays sensitive to Phase 3 regressions specifically, not to query-length abuse.
  Truncation is applied in `Retriever.search` BEFORE calling `embedder.embed([query])` so the dense path also sees the capped form (consistent query across BM25 and dense).

- **D-12:** **Per-stage structlog telemetry on every search.** Emit a `retriever_search_completed` log line at the end of `Retriever.search()`:
  ```python
  log.info(
      "retriever_search_completed",
      query_tokens=q_tokens,
      query_truncated=truncated_bool,
      bm25_candidates=n_bm25,
      dense_candidates=n_dense,
      rrf_unique=n_fused,
      rerank_input=n_rerank_in,
      results_returned=n_out,
      bm25_ms=ms_bm25,
      dense_ms=ms_dense,
      fuse_ms=ms_fuse,
      rerank_ms=ms_rerank,
      total_ms=ms_total,
  )
  ```
  Phase 9 MET-05 (per-stage latency p50/p95) sources directly from this line. Phase 11 ablation reports diff the same fields across runs. Phase 12 binds `trace_id` upstream — no Phase 5 retrofit required when OBS-01 lands.

### Canary test (RET-03 — STRUCTURAL ACCEPTANCE GATE)

- **D-13:** **Canary cases file at `data/eval/canary/cases.jsonl`** (committed). One JSON object per line:
  ```json
  {
    "case_id": "C-01-aapl-supply-chain",
    "question": "What supply-chain risks did Apple highlight in its FY2024 10-K?",
    "gold_chunk_ids": ["AAPL-FY2024-Item-1A-018", "AAPL-FY2024-Item-1A-019"],
    "ticker": "AAPL",
    "fiscal_year": 2024,
    "rationale": "Item 1A risk factor specifically discussing supplier concentration in China + Taiwan."
  }
  ```
  Lives in `data/eval/canary/` (a new sibling to Phase 8's eventual `data/eval/ground_truth/`); committed because it IS part of the artifact (a recruiter / engineer cloning the repo sees the structural acceptance criterion in plain text). The test driver at `tests/test_reranker_canary.py` reads the JSONL, runs both pipelines, asserts the aggregate criterion (D-14). The file format will dovetail into Phase 10's eval-report manifest (canary cases can be auto-folded into Phase 8 if useful — tracked as a deferred idea).

- **D-14:** **Aggregate pass criterion**: across the ≥5 cases,
  ```
  rerank_top3_hits = sum(1 for case in cases if any(gold_id in top3_rerank(case) for gold_id in case.gold_chunk_ids))
  dense_only_top3_hits = sum(1 for case in cases if any(gold_id in top3_dense_only(case) for gold_id in case.gold_chunk_ids))
  assert rerank_top3_hits > dense_only_top3_hits, "Reranker did not measurably improve top-3 hit rate"
  assert rerank_top3_hits >= 5, "Rerank pipeline did not hit gold in top-3 on at least 5 cases"
  ```
  Matches the REQ language in RET-03 + ROADMAP.md verbatim ("measurably improve top-3 hit rate vs. dense-only on ≥5 hand-written cases"). Boolean PASS/FAIL — no statistical-CI machinery (Phase 9 has the bootstrap CIs for delta reporting; the canary is a structural gate). Both pipelines run against the SAME case set (same query, same gold) so the comparison is apples-to-apples.

- **D-15:** **Stub-mode is the mandatory CI gate; real-mode is `workflow_dispatch`-only.** Mirrors EVAL-04 + Phase 4 D-20. The stub-mode canary uses `StubEmbedder` + `StubReranker` + `NumpyDenseStore` + `Bm25sStore` — every PR runs it; the stub reranker (cosine over hash-based embeddings) MUST out-hit stub-dense-only on the same hand-written cases. The real-mode test is marked `@pytest.mark.real` and triggered only by manual workflow dispatch (the bge-reranker-base model is ~250 MB and CPU inference is ~5–15 s for the full canary set — too expensive per PR). The two modes share the SAME JSONL case file; case selection has to satisfy both regimes (see D-17 on curation).

- **D-16:** **Failure protocol — CI fails LOUD with CLAUDE.md text quoted in the failure message.** The pytest assertion message includes the verbatim CLAUDE.md hard-gate quote:
  ```
  Reranker canary failed: rerank top-3 hits (4) did not exceed dense-only top-3 hits (5).
  
  Per CLAUDE.md: "If that gate fails, look at BGE 512-token truncation FIRST
  before suspecting hybrid retrieval, RRF, or chunk size. This is the most common
  subtle failure mode and the canary exists specifically to catch it."
  
  Debug order:
    1. Run `make verify-chunks` — confirm every chunk_id has n_tokens < 500.
    2. Confirm bge-reranker-base SDK pin hasn't drifted (tokenizer revision).
    3. THEN investigate RRF / chunk-size / hybrid retrieval changes.
  ```
  When this fires (likely weeks later in another phase's branch), the debugger may not remember CLAUDE.md says this — the failure message keeps the canary self-documenting.

- **D-17:** **Curate canary cases by hand from real 10-K text.** For each case: read a specific section in the corpus (e.g., AAPL FY2024 Item 1A on supplier concentration; NVDA FY2024 Item 7 on AI accelerator revenue concentration), construct a query a user might plausibly ask, and record the gold `chunk_id`(s). Each case lives in the JSONL with a one-line `rationale` field documenting why this case stresses the reranker over dense-only (typically: dense retrieves a topical-but-wrong-section chunk; reranker correctly reorders the gold chunk to top-3). The curated set must satisfy BOTH stub-mode (where the stub reranker's cosine-over-hash-embeddings has to beat stub dense-only on the same cases) AND real-mode. Cases that pass real but fail stub get reworked; cases that pass stub but fail real get a `@pytest.mark.real`-only override. Initial author target: 7–10 cases (margin above the ≥5 minimum). NO templated generation (synthetic feel hurts portfolio defensibility); NO third-party eval sets (FinanceBench / BizBench) for v1 — licensing + corpus-mismatch risks.

**Amendment (2026-05-14 — empirical resolution per Plan 05-06 Task 1 curation checkpoint):**

D-14 + D-15 are amended after empirical discovery that the **stub reranker is structurally incapable of beating stub dense-only**. Both `StubReranker.rerank` and `NumpyDenseStore.query` reduce to cosine similarity over the same `_text_to_vector` hash function in `adapters/stub/embedder.py:22-54` — the reranker cannot introduce NEW information, only LOSE the BM25-side contribution that RRF blended in. Phase 2 D-15's "non-degenerate" claim was design intent, not empirical fact. RESEARCH §8 flagged this MEDIUM-confidence with a fallback at line 1402. Brute-force sweep run by Plan 05-06 Task 1: 0 rerank-only wins / 60 dense-only wins / 234 neither out of 307 auto-generated cases.

**Resolution (Option D from the checkpoint):**

- Every case in `data/eval/canary/cases.jsonl` carries `"mode": "real"` indicating it is REAL-MODE-ELIGIBLE only. The original D-13 6-field schema is extended with this 7th `mode: Literal["real", "stub"]` field.
- The strict D-14 aggregate criterion (`rerank_top3_hits > dense_only_top3_hits AND rerank_top3_hits >= 5`) is enforced **ONLY in real-mode** (`@pytest.mark.real`-gated; runs under `workflow_dispatch` per Phase 4 D-20 precedent).
- Stub-mode `test_reranker_canary_stub_mode` becomes a **SCHEMA-ONLY** assertion: cases load, the 7-field shape (`case_id`, `question`, `gold_chunk_ids`, `ticker`, `fiscal_year`, `rationale`, `mode`) is valid on every record, `len(cases) >= 5`. Stub mode no longer runs rerank-vs-dense-only differential — it only verifies the cases.jsonl is well-formed and the canary infrastructure compiles.
- The Phase 13 README narrative acknowledges the canary's strict bite criterion fires under `workflow_dispatch`, not on every PR. The stub-mode "every PR" enforcement degrades to a schema gate.
- Pitfall 6 defenses remain intact: `_CLAUDE_MD_HARD_GATE` (in retriever.py) + `_CLAUDE_MD_QUOTE` (in test_reranker_canary.py) both grep-asserted; D-16 failure message verbatim CLAUDE.md 3-substring quote preserved.
- **Deferred ticket** captured in `05-06-SUMMARY.md`: "Stub-reranker discriminative-power redesign" — target Phase 11 or v2 / Phase 14. The fix is architectural (Phase 2 D-15 amendment): replace `StubReranker.rerank`'s cosine-over-hash-vectors with a function that disagrees with `StubEmbedder._text_to_vector` (candidates: bigram overlap with stopword removal, TF-IDF-weighted token scoring, substring containment).

### Claude's Discretion

These are intentionally left to the researcher/planner:

- **CD-01:** **Lazy-load on first `.search()` vs eager in factory.** `make_retriever(cfg)` could either (a) construct empty `Retriever` and load indices on first call, or (b) load indices in `__init__`. Recommend (b) eager — the load is sub-second for NumPy dense + bm25s, and "first query is slow" is a worse property than a known startup cost. Qdrant real mode pays its connection cost in `QdrantDenseStore.__init__` anyway.

- **CD-02:** **`RetrievedChunk` model home.** D-03 puts it in `docintel_retrieve.types`. Alternative: move to `docintel_core.types` (sibling of `Chunk`, `IndexManifest`, etc.) so Phase 6 / 7 / 13 import it without depending on the retrieve package. Recommend `docintel_core.types` for consistency — the schema is a shared contract.

- **CD-03:** **`Retriever` lazy-load vs holding bundles.** Recommend holding `AdapterBundle` + `IndexStoreBundle` as instance attributes (the way `Retriever(bundle, stores)` already implies). The bundles themselves carry the lazy-loading discipline.

- **CD-04:** **Tenacity retry on `embedder.embed([query])` call.** The embedder is wrapped at the adapter level (Phase 2 D-18). Phase 5 does NOT add a second retry layer — that would double-count failures. Same applies to `reranker.rerank()` and `*.query()`. Phase 5's `Retriever` does NOT add tenacity wraps; it composes already-wrapped adapter calls.

- **CD-05:** **Tie-breaking in RRF.** Cormack's formula is `1/(k + rank)`. Two chunks with identical RRF scores (rare but possible — both BM25 and dense returned them at the same rank): break ties by BM25 rank (lexical match is more interpretable for citations). Planner verifies during implementation that the bm25s + NumPy / Qdrant rank orderings are deterministic across re-runs (they should be — bm25s is deterministic post-build, NumPy `argpartition` is stable for distinct scores).

- **CD-06:** **Reranker batch size.** `CrossEncoder.predict(pairs, convert_to_numpy=True)` accepts the full pair list. For 20 pairs the default batch size (typically 32) handles it in one call. Planner may pass `batch_size=8` for memory safety on smaller CI runners. Stub reranker has no batching — it loops in Python.

- **CD-07:** **What `Retriever.search` does when both adapter calls return zero candidates** (cold-start vocab, empty index). Recommend: return `[]` with a structlog warning. Phase 6 will need to handle this anyway (GEN-04 refusal path). Logging surface: `retriever_search_zero_candidates`.

- **CD-08:** **Should `make_retriever(cfg)` cache the constructed `Retriever`?** FastAPI in Phase 13 will lru-cache it. Phase 10 eval harness constructs once per run. Recommend: NO factory-level cache — let callers cache. Mirrors `make_adapters(cfg)` precedent.

- **CD-09:** **Canary `tests/test_reranker_canary.py` test runtime.** Stub-mode case set should run in <2 s per PR; real-mode case set runs in <30 s under workflow_dispatch (model download dominates the first run; subsequent runs hit the HuggingFace cache). Planner verifies CI timing during execution.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher + planner) MUST read these before planning or implementing.**

### Project-level (always)
- `CLAUDE.md` — Operating rules: offline-first, single env reader, no silent retries, eval-in-CI, adapters/protocols for swappable components. The hard-gate paragraph on Phase 5 ("If that gate fails, look at BGE 512-token truncation FIRST...") is verbatim in D-16's failure-message text.
- `.planning/PROJECT.md` — Constraints section. "Adapters/protocols for swappable components" applies directly to D-08 (null adapter ablation seams). Key Decisions row "Cross-encoder reranker is gated by a hand-written hit-rate canary (Phase 5)" — D-13..D-17 are the realization of that decision.
- `.planning/REQUIREMENTS.md` §"Retrieval (Phase 5)" — RET-01..RET-04 verbatim; the success-criteria language is what `gsd-verifier` will grep for. §"Ground Truth (Phase 8)" GT-01..03 — the canary cases (D-13) are a SEPARATE artifact from Phase 8's eval set; the JSONL format dovetails but they are not the same file. §"Metrics (Phase 9)" MET-05 — per-stage latency p50/p95 sources from D-12 telemetry. §"Eval Harness (Phase 10)" EVAL-04 — the stub-mandatory/real-gated split in D-15 mirrors EVAL-04's pattern. §"Ablation (Phase 11)" ABL-01 — the no-rerank + dense-only ablations consume Phase 5's null adapter seam (D-08).
- `.planning/ROADMAP.md` §"Phase 5: retrieval-hybrid-rerank" — STRUCTURAL ACCEPTANCE GATE box (the canary rule). Success criteria language is what verification will grep for. §"Phase 11: ablation-studies" — ABL-01 consumes D-08's null adapter swap.
- `.planning/STATE.md` §"Hard Gates To Remember" — Phase 5 canary cross-reference; Phase 3's BGE 500-token chunker cap is the upstream invariant D-10 re-verifies.

### Phase 1 + 2 + 3 + 4 ground truth (existing code surface)

- `packages/docintel-core/src/docintel_core/config.py` — Phase 1 Settings (Phase 2/3/4 amendments). Phase 5 does NOT add new fields — the entire pipeline is parameterised via module constants (D-05/D-06/D-07) and adapter swaps (D-08), not env vars. FND-11 single-env-reader rule is preserved.
- `packages/docintel-core/src/docintel_core/types.py` — `Chunk` (Phase 3 D-15) is the input contract for the rerank assertion (D-10 reads `chunk.n_tokens`). `RetrievedChunk` MAY move here per CD-02 — Phase 7's `Citation` will consume the same `ticker`/`fiscal_year`/`item_code`/`char_span_in_section` fields.
- `packages/docintel-core/src/docintel_core/adapters/protocols.py` — Four content Protocols (`Embedder`, `Reranker`, `LLMClient`, `LLMJudge`) + two index Protocols (`DenseStore`, `BM25Store`). `Retriever.search()` composes them in order: `embedder.embed([query])` → `bm25.query(q_text, 100)` + `dense.query(q_vec, 100)` → `_rrf_fuse(...)` → `reranker.rerank(query, [chunk.text for chunk in top20])`.
- `packages/docintel-core/src/docintel_core/adapters/types.py` — `RerankedDoc` (the reranker's return type) is what `Retriever._rerank` post-processes into `RetrievedChunk`. `AdapterBundle` + `IndexStoreBundle` are the `Retriever.__init__` inputs.
- `packages/docintel-core/src/docintel_core/adapters/factory.py` — `make_adapters(cfg)` + `make_index_stores(cfg)`. Phase 5 adds `make_retriever(cfg)` as the THIRD sibling factory here (NOT in `docintel-retrieve`) per D-04. Lazy-import discipline applies (`from docintel_retrieve.retriever import Retriever` lives inside the function body, not at module top, so `import docintel_core.adapters.factory` stays cheap).
- `packages/docintel-core/src/docintel_core/adapters/real/reranker_bge.py` — `BGEReranker.rerank(query, docs)` is what `Retriever._rerank` calls in real mode. Already tenacity-wrapped (D-18 Phase 2) — Phase 5 does NOT add a second retry layer (CD-04).
- `packages/docintel-core/src/docintel_core/adapters/stub/reranker.py` — `StubReranker.rerank(query, docs)` is what stub-mode CI uses. Cosine-over-hash-embeddings → non-degenerate vs stub dense-only on the canary cases.
- `packages/docintel-core/src/docintel_core/adapters/real/numpy_dense.py` + `qdrant_dense.py` — `DenseStore.query(q_vec, k)` returns `list[(chunk_id, rank, score)]`. Phase 5 calls with `k=100` per D-05.
- `packages/docintel-core/src/docintel_core/adapters/real/bm25s_store.py` — `Bm25sStore.query(query_text, k)` returns `list[(chunk_id, rank, score)]`. Phase 5 calls with `k=100`. Note: BM25Store takes raw query text and tokenises internally (D-08 Phase 4) — Phase 5 passes the truncated query text (not pre-tokenised).
- `packages/docintel-core/src/docintel_core/log.py` — `configure_logging` + `merge_contextvars`. Phase 5 emits `retriever_search_completed` (D-12). Phase 12's `trace_id` binding via `contextvars` is OBS-01 — Phase 5's log line will gain a `trace_id` field automatically when Phase 12 lands; no Phase 5 retrofit.
- `data/indices/MANIFEST.json` — Phase 4's manifest. Phase 5 does NOT read this file at runtime — `Retriever` uses the stores via `IndexStoreBundle`, not by inspecting MANIFEST. The MANIFEST is consumed by `docintel-index verify` (Phase 4) and Phase 10's eval-report manifest header.
- `data/indices/dense/*` + `data/indices/bm25/*` — committed-style indices (currently gitignored per Phase 4 D-04). Phase 5's `Retriever` lazily reads them via the store adapters' `_lazy_load_from_disk()` paths.
- `data/corpus/chunks/**/*.jsonl` — 6,053 chunks. Phase 5 does NOT read these at runtime — the chunk text is already in the BM25 index (as tokenised vectors) and the dense embeddings index. BUT — `RetrievedChunk.text` (D-03) needs the raw text. Decision: store the text inline in `chunk_ids.json` is NOT viable (bloats the index). Recommend: `Retriever` lazy-loads a `chunk_id → Chunk` map from the chunks JSONL on first `.search()` call (CD-01) — a single pass over 6053 lines is ~50ms. Planner refines: this map is the source of truth for `RetrievedChunk` fields beyond `chunk_id` + `score`. Memory cost ~12 MB for the full Chunk set.
- `.planning/phases/02-adapters-protocols/02-CONTEXT.md` — D-01 (BGE-small / 384-dim) drives D-09 token-margin reasoning; D-02 (bge-reranker-base 512-cap) drives D-10's `n_tokens <= 500` assertion; D-15 (stub reranker cosine over hash embeddings) drives D-15's stub-mode canary feasibility.
- `.planning/phases/03-corpus-ingestion/03-CONTEXT.md` — D-11 (chunker hard cap 500 tokens) is the upstream invariant D-10's assertion re-verifies; D-14/D-15 (chunk_id format, JSONL layout) drives `RetrievedChunk.text` sourcing; D-16 (`char_span_in_section`) is the citation anchor D-03 carries forward.
- `.planning/phases/04-embedding-indexing/04-CONTEXT.md` — D-01 (tiered dense backend) means `Retriever` is backend-agnostic via `IndexStoreBundle.dense`; D-07 (single bm25s implementation) means BM25 is unified across stub + real; D-11 (rank-emission for RRF) is the input contract for D-07's `rrf_fuse`; D-13 (IndexManifest schema) is reference only — Phase 5 does not read MANIFEST at runtime.

### External docs (for the researcher)

- **Reciprocal Rank Fusion** (Cormack, Clarke, Büttcher 2009) — original paper. The `1/(k + rank)` formula and `k=60` default; the basis for D-07. Searchable: "Reciprocal Rank Fusion outperforms Condorcet and individual rank learning methods".
- **bm25s** PyPI + GitHub (`xhluca/bm25s`) — `BM25.retrieve(query_tokens, k)` API; tokenize semantics. Phase 4 already shipped the integration; Phase 5 calls it via `BM25Store.query()`.
- **sentence-transformers** 5.4.1 `CrossEncoder.predict(pairs, convert_to_numpy=True)` — the call inside `BGEReranker.rerank`. Phase 5 doesn't call directly; goes through the adapter.
- **Qdrant Python client** `query_points(collection_name, query, limit)` — Phase 4's `QdrantDenseStore.query()` already wraps it. Phase 5 calls via `DenseStore.query()`.
- **BGE-small-en-v1.5** model card on HuggingFace (`BAAI/bge-small-en-v1.5`) — 384-dim, 512-token cap, normalized embeddings. Phase 2 D-01 already pinned.
- **bge-reranker-base** model card (`BAAI/bge-reranker-base`) — 278M params, 512-token cap, raw-logit scoring. Phase 2 D-02 already pinned.
- **structlog `merge_contextvars`** docs — Phase 12 will bind `trace_id` here; Phase 5's log lines automatically inherit it. Already wired in Phase 1's `configure_logging`.
- **pytest** marker docs — `@pytest.mark.real` is already defined in Phase 4's conftest. Phase 5's `tests/test_reranker_canary.py` uses it for the real-mode case set per D-15.

[No spec/ADR files were referenced by the user during discussion — canonical refs derived from PROJECT.md, REQUIREMENTS.md, ROADMAP.md, the Phase 1/2/3/4 summaries and CONTEXT.md files, and external library docs.]

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`AdapterBundle`** (`docintel_core.adapters.types`): Phase 2 container with `embedder`, `reranker`, `llm`, `judge`. Phase 5's `Retriever(bundle, stores)` takes this verbatim. The `reranker` field is what `_rerank` calls. The `embedder` field is what query embedding goes through.
- **`IndexStoreBundle`** (`docintel_core.adapters.types`): Phase 4 container with `dense`, `bm25`. Phase 5's `Retriever(bundle, stores)` takes this verbatim. Both stores expose `.query(...) -> list[(chunk_id, rank, score)]` — same 3-tuple contract, RRF-compatible.
- **`make_adapters(cfg)` + `make_index_stores(cfg)`** (`docintel_core.adapters.factory`): Phase 5's `make_retriever(cfg)` is the THIRD sibling factory here per D-04. Lazy-import discipline (Phase 2 D-12) extends naturally: `from docintel_retrieve.retriever import Retriever` lives inside the function body.
- **`Chunk` Pydantic model** (`docintel_core.types`): Phase 3-defined. `Retriever` reads `chunk.text` for `RetrievedChunk.text` and reranker input; `chunk.n_tokens` for D-10 assertion; `chunk.ticker`/`fiscal_year`/`item_code`/`char_span_in_section` for `RetrievedChunk` citation fields.
- **`BGEReranker`** (`adapters/real/reranker_bge.py`): real-mode reranker, already tenacity-wrapped. Phase 5 calls `.rerank(query, [chunk.text for chunk in top_m])`.
- **`StubReranker`** (`adapters/stub/reranker.py`): stub-mode reranker. Cosine over hash-based unit vectors — non-degenerate against stub dense-only (Phase 2 D-15) which is what makes the stub-mode canary feasible (D-15 above).
- **`NumpyDenseStore` + `QdrantDenseStore`** (`adapters/real/*_dense.py`): both expose `query(q_vec, k) -> list[(chunk_id, rank, score)]`. Phase 5 doesn't care which one is in the bundle.
- **`Bm25sStore`** (`adapters/real/bm25s_store.py`): exposes `query(query_text, k) -> list[(chunk_id, rank, score)]`. Phase 5 passes the truncated query text directly; the store tokenises internally.
- **`RerankedDoc`** (`adapters/types`): Pydantic model with `doc_id`, `text`, `score`, `original_rank`. The reranker's return type. Phase 5's `_rerank` post-processes a `list[RerankedDoc]` into `list[RetrievedChunk]` by mapping `doc_id` (index into top-M candidates) back to the candidate's `chunk_id`.
- **`configure_logging`** (`docintel_core.log`): Phase 5 emits `retriever_search_completed` (D-12). `log = structlog.stdlib.get_logger(__name__)` pattern from every other module.
- **`docintel-index` package layout** (Phase 4): the model for `docintel-retrieve`'s pyproject + module structure. `pyproject.toml` pins `docintel-core` workspace dep, exposes `docintel-retrieve` as a script (NOT required for v1 — Phase 5's retrieval is library-only; CLI lives in Phase 10 / 13), `src/docintel_retrieve/__init__.py`, `py.typed`.

### Established Patterns

- **One package per workspace concern** — `docintel-retrieve` is the 7th package (core / api / ui / eval / ingest / index / retrieve). Workspace pyproject's `packages/*` glob picks it up automatically.
- **Lazy imports for heavy deps in the `real` branch** (Phase 2 D-12) — `Retriever` itself has no heavy imports (it imports `np`, `structlog`, types from core), so the entire `docintel_retrieve.retriever` module is cheap. The heavy deps (torch via reranker, qdrant_client via dense store) ride inside the bundles, which the caller already constructed.
- **Single env reader (FND-11)** — Phase 5 adds NO new Settings fields. Everything is module constants (D-05/D-06/D-07) or adapter-swap parameters (D-08).
- **`.name` property on every adapter** — Phase 5's `Retriever` itself doesn't need a `.name` (it's not stored in the manifest; the manifest sources from `bundle.embedder.name`, `bundle.reranker.name`, `stores.dense.name`, `stores.bm25.name`). Phase 10's eval manifest reads from those.
- **Per-package Dockerfile target** (Phase 1) — `docintel-retrieve` is a library imported by `docintel-api` (Phase 13) and `docintel-eval` (Phase 10). No new Dockerfile target needed.
- **`pinned deps + uv.lock regen + uv lock --check CI gate`** (FND-09) — `docintel-retrieve/pyproject.toml` pins `docintel-core` workspace dep + `numpy` (re-pin). uv.lock regenerated as part of Phase 5.
- **Tenacity wrap discipline** — Phase 5's `Retriever` does NOT add tenacity wraps. The wrapped calls live in the adapters (Phase 2 D-18, Phase 4 D-21). `scripts/check_index_wraps.sh` + `scripts/check_adapter_wraps.sh` do NOT need extension for Phase 5 — there are no new SDK call sites in `docintel-retrieve`.
- **JSONL fixture / data layout** (Phase 3 D-15) — `data/eval/canary/cases.jsonl` follows the same JSONL-per-record pattern as the chunks JSONLs. Grep-friendly + diff-readable.

### Integration Points

- **`Settings.llm_provider`** → `make_retriever(cfg)` factory dispatch (the seam). Already wired in `make_adapters(cfg)` + `make_index_stores(cfg)` — `make_retriever` composes both.
- **`AdapterBundle.embedder.embed([query]) -> np.ndarray(1, 384)`** → Phase 5's query embedding path. The `[0]` row is the query vector.
- **`AdapterBundle.reranker.rerank(query, list[str]) -> list[RerankedDoc]`** → Phase 5's top-M post-processing.
- **`IndexStoreBundle.bm25.query(query_text, 100) -> list[(chunk_id, rank, score)]`** → Phase 5's BM25 candidates (D-05).
- **`IndexStoreBundle.dense.query(q_vec, 100) -> list[(chunk_id, rank, score)]`** → Phase 5's dense candidates (D-05).
- **`Chunk` model from JSONL** → Phase 5 lazy-loads a `chunk_id → Chunk` map on first `.search()` call (CD-01); the map is the source of truth for `RetrievedChunk` text + citation fields beyond `chunk_id`.
- **`data/eval/canary/cases.jsonl`** → committed; consumed by `tests/test_reranker_canary.py`. Format dovetails with Phase 8's `data/eval/ground_truth/` (Phase 8 may absorb the canary cases later — deferred idea).
- **`structlog` `retriever_search_completed` log line** → Phase 9 MET-05 sources per-stage latency from here; Phase 11 ablation reports diff fields across runs; Phase 12 binds `trace_id` via `contextvars`.
- **`tests/test_reranker_canary.py`** → CI's structural acceptance gate. Stub-mode runs every PR; real-mode `@pytest.mark.real` gated by workflow_dispatch (D-15).

</code_context>

<specifics>
## Specific Ideas

- **The canary's preconditions ARE the chain of custody from Phase 3 → Phase 5.** Phase 3 D-11 capped chunks at 500 BGE tokens at chunk-build time (hard cap, build-fails-if-exceeded). Phase 5 D-10 re-verifies that invariant at the rerank seam via a `assert chunk.n_tokens <= 500` check. If the canary ever trips, D-16's failure message tells the debugger to check that invariant FIRST — because the most likely root cause is upstream (chunker regression or BGE-tokenizer pin drift), not the hybrid retrieval logic itself. This is what CLAUDE.md's "BGE 512-token truncation FIRST" rule is actually defending.
- **The two-mode canary (D-15) is the eval-in-CI gate's bite point.** EVAL-04 says "Stub-mode run completes in CI on every PR". For Phase 5's RET-03 to be enforced on every PR, the stub reranker must out-hit stub dense-only on the SAME ≥5 cases the real pipeline uses. Phase 2 D-15 designed the stub reranker (cosine over hash-based embeddings) specifically to be non-degenerate against stub dense-only — Phase 5 D-15 cashes that design choice. Hand-curating cases that satisfy BOTH regimes is real work (the curation rationale in each JSONL row documents why).
- **Null adapter ablation seams (D-08) cash Phase 11's design upfront.** Phase 11 ABL-01 will need `no-rerank` and `dense-only` ablations. By laying the seam now via null adapter classes (in `docintel-retrieve.null_adapters`), Phase 11 doesn't need to crack open `Retriever.search` — it just constructs an `AdapterBundle` with `NullReranker()` swapped in. The seam is testable (the `Retriever` shouldn't behave any differently with a null adapter than with the real one — same control flow, just degenerate scoring). This is the same "adapter swap is the artifact" framing Phase 2 D-03 used for Anthropic ↔ OpenAI.
- **Per-stage structlog telemetry (D-12) at Phase 5 is what makes Phase 9 / 12 cheap.** Phase 9 MET-05 needs per-stage latency p50/p95; Phase 12 OBS-01 needs `trace_id`-bound structured logs. By emitting the full per-stage payload from `Retriever.search` NOW, both phases can land without retrofitting Phase 5 code. Phase 12's `trace_id` rides on `contextvars` (Phase 1 already wired `merge_contextvars`) so the log line picks it up automatically when Phase 12 binds upstream.
- **`make_retriever(cfg)` lives in `docintel_core.adapters.factory`, NOT in `docintel-retrieve`.** D-04. The import direction matches every prior phase: `docintel-retrieve` imports from `docintel-core`, never the reverse. The factory is in core because `Settings` lives in core; the factory's job is the `Settings.llm_provider` dispatch. Phase 5's package (`docintel-retrieve`) ships the `Retriever` class itself, the `NullReranker`/`NullBM25Store`, the `RetrievedChunk` model, and the `_rrf_fuse` helper. The factory composes them.

</specifics>

<deferred>
## Deferred Ideas

- **Query embedding cache** — discussed implicitly when considering BGE embedder latency (~60ms CPU per call). For repeated queries (same string), an `lru_cache(maxsize=128)` on `Retriever._embed_query` would save ms per call. Not picked because eval-harness queries are typically unique (each ground-truth question runs once per eval), and Phase 13 API will lru-cache the whole `Retriever`. Tracked here so if Phase 9 latency reports show query embedding is a meaningful contributor on the demo question, this is the lever.
- **Statistical pass criterion for the canary (bootstrap CI)** — Considered as Option 3 for D-14. Not picked because at N=5–10 cases the CI is wide and Phase 9 already has the bootstrap-CI machinery for delta reporting. The structural gate stays binary; Phase 11's ablation reports are where the CI-based delta reporting lives.
- **Per-case strict canary criterion** — Considered as Option 2 for D-14. Not picked because some cases will be borderline; the aggregate criterion is more robust and matches the REQ wording verbatim. Tracked here in case a future stricter gate is wanted.
- **FinanceBench / BizBench external eval set** — Considered for D-17 case curation. Not picked because of licensing + corpus mismatch (their cases don't necessarily align with our 15-ticker S&P 500 snapshot). Tracked as a v2 expansion — could be folded into Phase 8 GT-01 as additional question types.
- **Templated canary case generation** — Considered for D-17. Not picked because templated cases feel synthetic and hurt portfolio defensibility. Hand-curation produces fewer but more defensible cases.
- **Cross-doc reranking strategy for the multi-hop demo question** — The locked demo ("Which of these companies grew R&D while margins shrank in 2023?") is multi-hop comparative. Phase 5's current design retrieves top-5 chunks per query — the demo may need top-K-per-company aggregation or a follow-up retrieval pass. Tracked as a Phase 13 concern; not a Phase 5 retrieval design issue. If Phase 13 reveals a need, Phase 5's `Retriever` can grow a `.search_per_ticker(query, k_per_ticker)` method without touching the existing `.search()`.
- **'Why this chunk?' debug endpoint** — Surfacing per-stage scores (bm25_rank, dense_rank, rrf_score, rerank_score) for a specific chunk in a query. Useful for Phase 13 UI debugging and Phase 11 ablation reports. Phase 5 D-03 deliberately keeps `RetrievedChunk` minimal; this debug data is in the structlog stream (D-12). Tracked here so Phase 13 can build an "expand citation → show per-stage scores" affordance if useful.
- **Reranker batch size as a Settings field** — Considered briefly during D-06. Not picked because the M=20 default fits one CrossEncoder.predict call cleanly. If Phase 9 reveals memory pressure on small CI runners, expose as Settings.
- **Boolean ablation flags on `Retriever.search`** — Considered as Option 2 for D-08. Not picked because adapter swaps are cleaner than conditional logic in the hot path. Tracked here so if a future caller needs runtime ablation without constructing a new `Retriever`, this is the alternative.
- **Tie-breaking strategy beyond BM25 rank** — CD-05 picked BM25 rank. Other options (recency, citation-priority weight) tracked here for v2 if Phase 11 ablations show tie-breaking is load-bearing.
- **Phase 5 reranker truncation `re-tokenize check`** — Considered as Option 2 for D-10. Not picked because n_tokens <= 500 assertion + Phase 3 hard cap is sufficient defense-in-depth. Tracked here if a future tokenizer disagreement (BGE-embedder ↔ BGE-reranker) ever surfaces.
- **Soft warning on n_tokens > 480 (near-cap)** — Considered as Option 3 for D-10. Not picked because soft warnings get ignored; the assertion is the contract. Tracked here as an observability improvement (structlog line `chunk_near_token_cap`) for Phase 12.

</deferred>

---

*Phase: 5-retrieval-hybrid-rerank*
*Context gathered: 2026-05-14*
</content>
</invoke>