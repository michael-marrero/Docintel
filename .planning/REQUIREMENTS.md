# Requirements: docintel

**Defined:** 2026-04-28 (original)
**Reconstructed:** 2026-05-11 from CLAUDE.md + Phase 1 SUMMARYs (`projectspec.md` not recoverable in this clone)
**Core Value:** Eval harness reports real numbers (Hit@5, MRR, faithfulness, citation accuracy, latency, $/query) with Wilson + bootstrap CIs, re-run by CI on every PR.

## v1 Requirements

### Foundation (Phase 1 — complete)

- [x] **FND-01**: uv 0.11.8 workspace at repo root with `packages/*` members; `.python-version` pinned to 3.11
- [x] **FND-02**: `docintel_core` package exposes `Settings` (Pydantic v2 + `pydantic-settings`, `env_prefix="DOCINTEL_"`), `configure_logging` (structlog JSON + `merge_contextvars`), `__version__`, `types`
- [x] **FND-03**: Four sub-packages — `docintel-core`, `docintel-api`, `docintel-ui`, `docintel-eval` — with their own pinned `pyproject.toml` and PEP 561 `py.typed` markers
- [x] **FND-04**: FastAPI app skeleton with `/health` consuming `docintel_core.__version__` and `Settings.llm_provider`
- [x] **FND-05**: Streamlit UI skeleton calling `Settings.api_url` (compose service name `api` by default)
- [x] **FND-06**: Pre-commit + pre-push hooks: ruff (lint + format), black 24.10, gitleaks v8.21.2 with shared `.gitleaks.toml` (also reused by CI)
- [x] **FND-07**: `docker-compose.yml` brings up `api` + `ui` + (later) `qdrant`; per-service Docker images
- [x] **FND-08**: `LLM_PROVIDER=stub` is the offline-first default — set in `.env.example`, CI workflow `env:`, and docker-compose env passthrough (triple-redundant)
- [x] **FND-09**: GitHub Actions CI runs `uv lock --check` + ruff + black + mypy + pytest + gitleaks on every PR; uses same `.gitleaks.toml` as pre-commit
- [x] **FND-10**: `.env.example` template at repo root with `DOCINTEL_`-prefixed variables and blank API-key placeholders
- [x] **FND-11**: Single env reader — `os.environ`/`os.getenv` calls absent from every module except `config.py` (CI grep gate)

### Adapters & Protocols (Phase 2)

- [x] **ADP-01**: `Embedder` protocol with `embed(texts: list[str]) -> np.ndarray` (or equivalent), ≥1 real adapter (`bge` or `text-embedding-3`) and 1 stub adapter
- [x] **ADP-02**: `Reranker` protocol with `rerank(query, docs) -> list[(doc, score)]`, ≥1 real adapter (cross-encoder) and 1 stub adapter
- [x] **ADP-03**: `LLMClient` protocol with `complete(prompt, ...) -> str | AnswerObj`, ≥1 real adapter (Anthropic or OpenAI) and 1 stub adapter
- [x] **ADP-04**: `LLMJudge` protocol with `judge(prediction, reference, rubric) -> Score`, ≥1 real adapter and 1 stub adapter
- [x] **ADP-05**: `make_adapters(cfg)` factory reads `Settings.llm_provider` and returns matching set; only seam between code and providers
- [x] **ADP-06**: Every LLM/embedding/judge call wrapped in `tenacity` retry with `before_sleep_log`; no silent retries
- [x] **ADP-07**: Stubs are deterministic — same input → same output, no randomness, no clock reads — so eval-in-CI is reproducible

### Ingestion (Phase 3)

- [ ] **ING-01**: `make fetch-corpus` downloads 10–20 companies × 3 years of SEC 10-K filings into `data/corpus/` (gitignored)
- [ ] **ING-02**: Filings are normalized to a chunkable form (HTML/text) with stable section boundaries
- [ ] **ING-03**: Chunker produces deterministic chunks with metadata (`company`, `fiscal_year`, `section`, `chunk_id`, source-page or section anchor for citation)
- [ ] **ING-04**: Corpus build is idempotent — re-running produces byte-identical output (so the index doesn't churn between runs)

### Indexing (Phase 4 — depends on ADP-01)

- [ ] **IDX-01**: Embedding index built over chunked corpus using the `Embedder` adapter from Phase 2
- [ ] **IDX-02**: BM25 index built alongside, keyed by the same `chunk_id`s
- [ ] **IDX-03**: Index build is reproducible from the corpus (stub embedder included) and writes a manifest with `embedder.name`, chunk count, build timestamp
- [ ] **IDX-04**: Indices stored under `data/indices/` (gitignored); not committed

### Retrieval (Phase 5 — depends on IDX-01..03)

- [ ] **RET-01**: Hybrid retrieval combines BM25 + dense via Reciprocal Rank Fusion
- [ ] **RET-02**: Cross-encoder reranker post-processes top-N RRF candidates
- [ ] **RET-03**: **Reranker silent-truncation canary**: ≥5 hand-written cases where reranking measurably improves top-3 hit rate vs. dense-only. If this fails, look at BGE 512-token truncation FIRST before suspecting hybrid retrieval, RRF, or chunk size.
- [ ] **RET-04**: Retrieval returns `chunk_id` + score + the metadata needed to render citations

### Generation (Phase 6)

- [ ] **GEN-01**: All prompts live in `packages/docintel-generate/src/docintel_generate/prompts.py`; grep for inline string-literal prompts outside this file returns zero matches (CI gate via `scripts/check_prompt_locality.sh`)
- [ ] **GEN-02**: Each prompt has a deterministic version hash exposed as `PROMPT_VERSION_HASH`; included in every eval report manifest
- [ ] **GEN-03**: Generator is gated by `LLM_PROVIDER` and uses the `LLMClient` adapter; stub generator returns deterministic placeholder answers covering the full schema
- [ ] **GEN-04**: Refusal path — generator returns an explicit refusal when retrieved evidence is insufficient (used in the demo's out-of-corpus question)

### Answer Schema (Phase 7)

- [ ] **ANS-01**: `Answer` schema (Pydantic) with fields: `text`, `citations: list[Citation]`, `confidence`, `refused: bool`, `prompt_version_hash`
- [ ] **ANS-02**: `Citation` carries `chunk_id`, `company`, `fiscal_year`, `section`, and a quote span the UI can highlight
- [ ] **ANS-03**: Every claim in `Answer.text` is anchored to ≥1 citation (faithfulness precondition)

### Ground Truth (Phase 8 — parallelizable with Phases 4–7)

- [ ] **GT-01**: Hand-curated eval set with ≥30 questions spanning single-doc factual, multi-doc comparative, and out-of-corpus refusal types
- [ ] **GT-02**: Each question carries gold passage IDs (for Hit@K, MRR), a gold answer (for faithfulness), and an expected citation set (for citation accuracy)
- [ ] **GT-03**: Eval set lives under `data/eval/ground_truth/` and is committed (it is part of the artifact)

### Metrics (Phase 9 — depends on ANS-* and GT-*)

- [ ] **MET-01**: Hit@K (K ∈ {1, 3, 5, 10}) computed against gold passages; reported with Wilson CIs
- [ ] **MET-02**: MRR over the gold passage set
- [ ] **MET-03**: Faithfulness via `LLMJudge` (every claim in answer is supported by cited evidence); reported with Wilson CIs
- [ ] **MET-04**: Citation accuracy — fraction of citations that point to the gold passage set; Wilson CIs
- [ ] **MET-05**: Latency (p50, p95) and $/query, both per-pipeline-stage and end-to-end
- [ ] **MET-06**: Bootstrap CIs on deltas (e.g., "with-rerank − without-rerank") used in ablation comparisons

### Eval Harness (Phase 10 — depends on MET-*)

- [ ] **EVAL-01**: Single CLI entrypoint (`docintel-eval run`) executes the full pipeline against the eval set and emits a report
- [ ] **EVAL-02**: Reports written to `data/eval/reports/<timestamp>/` with mandatory manifest header: `embedder.name`, `reranker.name`, `generator.name`, `prompt_version_hash`, git SHA
- [ ] **EVAL-03**: Reports committed (`data/eval/reports/*.md` is NOT gitignored — the cache `data/eval/cache/` is)
- [ ] **EVAL-04**: Stub-mode run completes in CI on every PR; real-key run is gated behind manual workflow_dispatch

### Ablation (Phase 11 — depends on EVAL-*)

- [ ] **ABL-01**: At least three ablations land with bootstrap-CI deltas: no-rerank, dense-only (BM25 off), chunk-size sweep
- [ ] **ABL-02**: Ablation results summarized into a single comparison table in the run's report

### Observability (Phase 12)

- [ ] **OBS-01**: Every request carries a `trace_id` propagated via `structlog.contextvars` (the foundation is already wired in Phase 1's `configure_logging`)
- [ ] **OBS-02**: Per-stage timings and token counts emitted as structured logs and exposed in the UI's Traces tab
- [ ] **OBS-03**: Logs are JSON; no unstructured `print` calls

### API + UI + Polish (Phase 13 — depends on Phases 11 + 12)

- [ ] **UI-01**: Streamlit UI has three tabs — `Query`, `Traces`, `Eval Results` (tab labels locked in Phase 1 Plan 04 per D-16)
- [ ] **UI-02**: Citations in answers are hoverable; hover surfaces the cited chunk text
- [ ] **UI-03**: Hero GIF answers the locked multi-hop comparative question across companies, plus the refusal demo on an out-of-corpus question
- [ ] **UI-04**: README rewritten from real measurements (Hit@K, MRR, faithfulness, latency, $/query) — not from the plan
- [ ] **UI-05**: `DECISIONS.md` ships with ≥8 ADRs covering the load-bearing choices
- [ ] **UI-06**: `git clone && docker-compose up` produces a working demo on a fresh machine (one-command demo gate)

## v2 Requirements

Deferred to Phase 14 / future release. Tracked but not in current roadmap.

### Multi-modal & Advanced Retrieval

- **V2-01**: Image-bearing 10-K exhibits (charts, tables-as-images) ingested via a multimodal embedder
- **V2-02**: Table-aware chunking that preserves cell structure for numeric questions
- **V2-03**: Query rewriting / HyDE for hard recall cases

### Production-shaped Ops

- **V2-04**: Multi-tenant API with per-tenant rate limiting
- **V2-05**: Online ingestion from SEC EDGAR (current pipeline is batch-only)
- **V2-06**: Live A/B of prompt versions in production with sequential testing

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Chat-style multi-turn UI | Single-turn Q&A is enough for the eval story; chat dilutes faithfulness/citation focus |
| Auth-protected API in v1 | Demo is single-user; auth would be theater for the audience |
| Live SEC EDGAR ingestion in demo path | Corpus is pre-fetched; one-command demo never hits the network |
| Real LLM/embedding calls at build time | All real-API paths are behind adapter protocols; stubs cover everything including eval |
| Online learning / fine-tuning | Out of scope for a 4–5 day portfolio artifact; story is RAG engineering, not model training |
| Mocked tests for adapters | Adapters are exercised through the stub adapter, not mocks — keeps the seam real |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FND-01 | Phase 1 | Complete |
| FND-02 | Phase 1 | Complete |
| FND-03 | Phase 1 | Complete |
| FND-04 | Phase 1 | Complete |
| FND-05 | Phase 1 | Complete |
| FND-06 | Phase 1 | Complete |
| FND-07 | Phase 1 | Complete |
| FND-08 | Phase 1 | Complete |
| FND-09 | Phase 1 | Complete |
| FND-10 | Phase 1 | Complete |
| FND-11 | Phase 1 | Complete |
| ADP-01 | Phase 2 | Complete |
| ADP-02 | Phase 2 | Complete |
| ADP-03 | Phase 2 | Complete |
| ADP-04 | Phase 2 | Complete |
| ADP-05 | Phase 2 | Complete |
| ADP-06 | Phase 2 | Complete |
| ADP-07 | Phase 2 | Complete |
| ING-01 | Phase 3 | Pending |
| ING-02 | Phase 3 | Pending |
| ING-03 | Phase 3 | Pending |
| ING-04 | Phase 3 | Pending |
| IDX-01 | Phase 4 | Pending |
| IDX-02 | Phase 4 | Pending |
| IDX-03 | Phase 4 | Pending |
| IDX-04 | Phase 4 | Pending |
| RET-01 | Phase 5 | Pending |
| RET-02 | Phase 5 | Pending |
| RET-03 | Phase 5 | Pending |
| RET-04 | Phase 5 | Pending |
| GEN-01 | Phase 6 | Pending |
| GEN-02 | Phase 6 | Pending |
| GEN-03 | Phase 6 | Pending |
| GEN-04 | Phase 6 | Pending |
| ANS-01 | Phase 7 | Pending |
| ANS-02 | Phase 7 | Pending |
| ANS-03 | Phase 7 | Pending |
| GT-01 | Phase 8 | Pending |
| GT-02 | Phase 8 | Pending |
| GT-03 | Phase 8 | Pending |
| MET-01 | Phase 9 | Pending |
| MET-02 | Phase 9 | Pending |
| MET-03 | Phase 9 | Pending |
| MET-04 | Phase 9 | Pending |
| MET-05 | Phase 9 | Pending |
| MET-06 | Phase 9 | Pending |
| EVAL-01 | Phase 10 | Pending |
| EVAL-02 | Phase 10 | Pending |
| EVAL-03 | Phase 10 | Pending |
| EVAL-04 | Phase 10 | Pending |
| ABL-01 | Phase 11 | Pending |
| ABL-02 | Phase 11 | Pending |
| OBS-01 | Phase 12 | Pending |
| OBS-02 | Phase 12 | Pending |
| OBS-03 | Phase 12 | Pending |
| UI-01 | Phase 13 | Pending |
| UI-02 | Phase 13 | Pending |
| UI-03 | Phase 13 | Pending |
| UI-04 | Phase 13 | Pending |
| UI-05 | Phase 13 | Pending |
| UI-06 | Phase 13 | Pending |

**Coverage:**
- v1 requirements: 53 total
- Mapped to phases: 53
- Unmapped: 0 ✓
- Complete: 11 (Phase 1)
- Pending: 42

---
*Requirements defined: 2026-04-28 (original projectspec.md)*
*Last updated: 2026-05-11 — reconstructed from CLAUDE.md + Phase 1 SUMMARYs after `projectspec.md` was found missing in this fresh clone*
