# Roadmap: docintel

**Created:** 2026-04-28 (original)
**Reconstructed:** 2026-05-11 from CLAUDE.md + Phase 1 SUMMARYs
**Phases:** 13 v1 + Phase 14 (v2 deferred). One phase = one branch. Reports under `data/eval/reports/` are part of the artifact and are committed.

## Sequencing Constraints (hard)

These are encoded in each phase's `Depends on` line, but worth surfacing here because they're easy to miss:

- **Phase 2 must land before Phase 4.** Adapters/protocols/stubs gate everything downstream. If protocols slip, eval-in-CI becomes theater.
- **Phase 5 carries the reranker silent-truncation canary** as a structural acceptance gate. Cross-encoder must measurably improve top-3 hit rate vs. dense-only on ≥5 hand-written cases. If that gate fails, look at BGE 512-token truncation FIRST before suspecting hybrid retrieval, RRF, or chunk size.
- **Phase 9 depends on both Phase 7 (Answer schema) AND Phase 8 (ground truth).** Phase 8 is parallelizable with 4–7.
- **Phase 13 depends on Phase 11 (ablation) AND Phase 12 (observability).** Phase 13 carries disproportionate recruiter weight — multi-hop hero GIF, hoverable citations, README from measurements, ≥8 ADRs. Protect this phase's time.

---

## Phase 1: scaffold-foundation ✓ COMPLETE

**Status:** Complete (merged `f40bca7` to `main` on 2026-04-28)
**Branch:** `phase/1-scaffold-foundation` (merged)
**Depends on:** —
**Provides:** uv workspace, four sub-packages, `Settings`, structlog config, secrets hygiene, docker-compose scaffold, CI workflow
**Closes:** FND-01..FND-11

Phase 1 plans on disk: `.planning/phases/01-scaffold-foundation/01-01-SUMMARY.md`, `01-02-SUMMARY.md`. Plan 10 (CI workflow) also landed per git log (`1ceb792 chore: merge executor worktree (01-10 CI workflow)`).

**Success criteria (verified):**
- `uv lock --check` exits 0; `uv sync --all-packages --frozen` installs cleanly
- `gitleaks` pre-commit refuses to commit a fake API key (gate set up; test lives in Plan 09)
- `LLM_PROVIDER=stub` is the default in `.env.example`, CI, and docker-compose
- `os.environ`/`os.getenv` calls absent from every module except `config.py` (CI grep gate)

---

## Phase 2: adapters-protocols

**Status:** Next
**Branch:** `phase/2-adapters-protocols`
**Depends on:** Phase 1 (✓)
**Provides:** `Embedder`, `Reranker`, `LLMClient`, `LLMJudge` protocols; ≥1 real + 1 stub adapter for each; `make_adapters(cfg)` factory; tenacity retry wrapping every LLM call
**Closes:** ADP-01..ADP-07

**Why this comes before Phase 4:** if protocols slip, every later phase has to be rewritten to swap providers, and eval-in-CI becomes impossible. This is the single most load-bearing phase after Phase 1.

**Plans:** 6 plans

Plans:
**Wave 1**
- [ ] 02-01-PLAN.md — Wave 0: test scaffolding (xfail) for adapters/pricing/CI-gate
- [ ] 02-02-PLAN.md — Wave 1: protocols, types, AdapterBundle, pricing table

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 02-03-PLAN.md — Wave 2: 4 deterministic stub adapters

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 02-04-PLAN.md — Wave 3: make_adapters factory + Settings.llm_real_provider

**Wave 4** *(blocked on Wave 3 completion)*
- [ ] 02-05-PLAN.md — Wave 4: 5 real adapters + scripts/check_adapter_wraps.sh

**Wave 5** *(blocked on Wave 4 completion)*
- [ ] 02-06-PLAN.md — Wave 5: dep migration + mypy tighten + CI grep gate wiring

**Success criteria:**
- All four protocols importable from `docintel_core.adapters` (or equivalent)
- `make_adapters(cfg)` with `LLM_PROVIDER=stub` returns the stub set; with `real` returns the real set
- Stubs are deterministic — same input → same output, no randomness, no clock reads
- Every LLM/embedding/judge call wrapped in tenacity retry with `before_sleep_log`; CI grep for un-wrapped calls returns zero
- mypy tightens (Phase 1's `ignore_missing_imports=true` exception removed)

---
## Phase 3: corpus-ingestion

**Status:** Planned
**Branch:** `phase/3-corpus-ingestion`
**Depends on:** Phase 1 (✓)
**Provides:** SEC 10-K fetcher (15 companies × 3 fiscal years), selectolax + Item-regex normalizer with citation-grade metadata, BGE-aware paragraph-greedy chunker, `data/corpus/MANIFEST.json` provenance, `make fetch-corpus` target, `docintel-ingest` workspace package
**Closes:** ING-01..ING-04

**Goal:** Build the SEC 10-K corpus the rest of the system retrieves over — fetch raw filings, normalize them with citation-grade metadata, lay them on disk under `data/corpus/` idempotently. Ship a new `docintel-ingest` workspace package with a CLI that `make fetch-corpus` invokes.

**Plans:** 7 plans across 6 waves (Wave 0 has two parallel plans)

Plans:
**Wave 1** *(Wave 0 — tests-first scaffolding; both plans run in parallel, disjoint files_modified)*
- [ ] 03-01-PLAN.md — Wave 0: 8 test-file scaffolds (xfail) + 4 fixtures + .gitleaks allowlist
- [ ] 03-02-PLAN.md — Wave 0: Settings amendment (D-19) + .env.example + .gitignore narrowing (D-04 + Pitfall 6) + scripts/check_ingest_wraps.sh (D-18 analog)

**Wave 2** *(blocked on Wave 0 completion)*
- [ ] 03-03-PLAN.md — Wave 1: docintel-ingest package skeleton + CLI + snapshot loader + docintel_core.types population (CD-01); 15-row companies.snapshot.csv (D-01, Pitfall 1)

**Wave 3** *(blocked on Wave 1 completion; CHECKPOINT — developer-machine SEC fetch)*
- [ ] 03-04-PLAN.md — Wave 2: fetch.py — tenacity-wrapped Downloader.get() + body-only HTML trimmer (D-03, D-05, Pitfall 8) + commit ~45 raw HTML files

**Wave 4** *(blocked on Wave 2 completion)*
- [ ] 03-05-PLAN.md — Wave 3: normalize.py — selectolax + Item regex + NFC whitespace (D-06, D-07, Pitfall 4 + 5) + commit 45 normalized JSON files

**Wave 5** *(blocked on Wave 3 completion)*
- [ ] 03-06-PLAN.md — Wave 4: tokenizer.py (lazy BGE, Pitfall 3 revision pin) + chunk.py (BGE-aware paragraph-greedy splitter, D-11..D-14, CD-02, CD-06) + commit 45 chunks JSONL

**Wave 6** *(blocked on Wave 4 completion)*
- [ ] 03-07-PLAN.md — Wave 5: manifest.py + verify.py (D-21, D-22, ING-04 idempotency gate) + Makefile fetch-corpus + CI ingest-wrap step + final xfail removal

**Success criteria:**
- `make fetch-corpus` lands 15 companies × 3 fiscal years under `data/corpus/` on a developer machine
- Corpus build is idempotent (re-running the chunker on committed normalized JSON produces byte-identical chunk JSONL — CI-asserted via `tests/test_chunk_idempotency.py`)
- Each chunk carries `company`, `fiscal_year`, `section`, `chunk_id`, source anchor for citation (D-15 + D-16 schema in `docintel_core.types.Chunk`)
- `data/corpus/` is partially committed (per D-04): raw + normalized + chunks + MANIFEST + companies.snapshot.csv are tracked; `.cache/` stays ignored
- `MANIFEST.json` records tokenizer revision SHA (Pitfall 3) + chunker config + per-filing sha256 hashes
- `bash scripts/check_ingest_wraps.sh` exits 0 in CI (D-18 / ADP-06 analog enforces tenacity wrap on sec-edgar-downloader call site)
- FND-11 single-env-reader rule preserved (Settings remains the only env-reading site)
---

## Phase 4: embedding-indexing

**Status:** Pending
**Branch:** `phase/4-embedding-indexing`
**Depends on:** Phase 2 (ADP-01), Phase 3 (ING-03)
**Provides:** Embedding index over chunked corpus, parallel BM25 index, build manifest
**Closes:** IDX-01..IDX-04

**Goal:** Build the embedding index and parallel BM25 index over the 6,053 chunks Phase 3 produced. Persist under `data/indices/` (gitignored). Write a single `data/indices/MANIFEST.json` capturing embedder identity, BM25 config, source-corpus identity, per-artifact sha256s, chunk count, build timestamp, and git SHA.

**Plans:** 7 plans across 6 waves

Plans:
**Wave 1** *(Wave 0 — tests-first scaffolding; both plans run in parallel, disjoint files_modified)*
- [x] 04-01-PLAN.md — Wave 0: 6 test scaffolds (xfail) for IDX-01..04 + Pitfall 3 + Pattern 3 + grep-gate negative fixture
- [x] 04-02-PLAN.md — Wave 0: Settings amendment (D-17) + .env.example + .gitignore comment + pytest `real` marker + scripts/check_index_wraps.sh + 3 more test scaffolds (D-12 idempotency, D-14 verify, D-21 gate)

**Wave 2** *(blocked on Wave 0 completion)*
- [x] 04-03-PLAN.md — Wave 2: DenseStore + BM25Store Protocols (D-02) + IndexStoreBundle + IndexManifest models (CD-02) + new docintel-index package skeleton (D-15..D-18 — pyproject pinning bm25s/PyStemmer/qdrant-client) + uv.lock regen

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 04-04-PLAN.md — Wave 3: Bm25sStore (D-07..D-11) + NumpyDenseStore (D-04, CD-05) — both in-process, no @retry

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 04-05-PLAN.md — Wave 4: QdrantDenseStore (amended CD-06 uuid5 + Pitfall 1 + Pitfall 5) + make_index_stores factory (D-03) + docintel-index build/verify/manifest/cli (D-12..D-14, D-16, Pitfall 8 atomic write, Pitfall 9 corpus identity hash)

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 04-06-PLAN.md — Wave 5: Makefile build-indices target (D-19) + docker-compose qdrant service profile real (D-05, Pitfall 7) + CI stub-mode build/verify steps + workflow_dispatch real-index-build job (D-20, D-21)

**Wave 6** *(blocked on Wave 5 completion — phase gate)*
- [x] 04-07-PLAN.md — Wave 6: remove xfail markers from 9 Wave-0 tests + add tests/test_index_build_real.py (@pytest.mark.real) + final phase-gate verification (decision-coverage audit for D-01..D-21)

**Success criteria:**
- Embedding index built using the `Embedder` adapter (stub-mode build works in CI)
- BM25 index keyed by the same `chunk_id`s
- Index manifest captures `embedder.name`, chunk count, build timestamp
- `data/indices/` gitignored
- `uv run docintel-index verify` exits 0 on clean build, 1 on tampered artifact (D-14)
- Idempotent re-build with unchanged corpus exits 0 and emits `index_build_skipped_unchanged_corpus` (D-12)
- `bash scripts/check_index_wraps.sh` exits 0 in CI (D-21 / ADP-06 analog — tenacity wrap on qdrant_client.* call sites)
- Default `docker-compose up` continues to bring up api + ui in stub mode without starting qdrant (UI-06 preserved per Pitfall 7)
- Real-mode index build gated behind `workflow_dispatch` (D-20)

---

## Phase 5: retrieval-hybrid-rerank

**Status:** Planned
**Branch:** `phase/5-retrieval-hybrid-rerank`
**Depends on:** Phase 4 (IDX-01..03)
**Provides:** Hybrid retrieval (BM25 + dense via RRF) + cross-encoder reranker over Phase 4 indices; `Retriever.search()` single seam; `make_retriever(cfg)` factory; canary acceptance gate
**Closes:** RET-01..RET-04

**🚨 STRUCTURAL ACCEPTANCE GATE — RERANKER SILENT-TRUNCATION CANARY**

Phase 5 carries an explicit hand-written canary: cross-encoder reranking must measurably improve top-3 hit rate vs. dense-only on ≥5 hand-written cases. **If that gate fails, look at BGE 512-token silent truncation FIRST before suspecting hybrid retrieval, RRF, or chunk size.** This is the most common subtle failure mode and the canary exists specifically to catch it.

**Goal:** Ship the query-time retrieval pipeline that takes a user question and returns the top-K most relevant chunks from the corpus, ready for Phase 6's generator. The pipeline is hybrid + reranked: BM25 (lexical) and dense (semantic) each return top-N candidates from Phase 4's indices, Reciprocal Rank Fusion combines them into a single ranking, and the BGE cross-encoder reranks the top-M of that fused set into the final top-K. Phase 5 also carries the silent-truncation canary (RET-03) as a STRUCTURAL ACCEPTANCE GATE: ≥5 hand-curated cases where the rerank pipeline measurably out-hits dense-only at top-3.

**Plans:** 7 plans across 4 waves

Plans:
**Wave 0** *(tests-first scaffolding + workspace package skeleton; both plans run in parallel — disjoint files_modified)*
- [ ] 05-01-PLAN.md — Wave 0: 6 test scaffolds (xfail) for RET-01..04 + data/eval/canary/cases.jsonl placeholder
- [ ] 05-02-PLAN.md — Wave 0: new 7th workspace package docintel-retrieve skeleton + uv.lock regen + RetrievedChunk Pydantic v2 model in docintel_core.types (CD-02)

**Wave 1** *(blocked on Wave 0 completion; two plans run in parallel — disjoint files_modified)*
- [ ] 05-03-PLAN.md — Wave 1: _rrf_fuse pure function + RRF_K=60 constant in fuse.py (D-07 + CD-05 + Pitfall 5)
- [ ] 05-04-PLAN.md — Wave 1: NullReranker + NullBM25Store in null_adapters.py (D-08 — Phase 11 ablation seam)

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 05-05-PLAN.md — Wave 2: Retriever class + make_retriever(cfg) factory + chunk-map eager-load + D-10/D-11 silent-truncation defenses + D-12 per-stage telemetry (RET-02, RET-04, CD-01, CD-04, CD-07, Pitfall 7)

**Wave 3** *(blocked on Wave 2 completion — empirical curation work)*
- [ ] 05-06-PLAN.md — Wave 3: canary cases.jsonl curation (7+ real 10-K cases per RESEARCH §7 playbook) + canary test driver implementation + CI visibility step (RET-03, D-13..D-17)

**Wave 4** *(blocked on Wave 3 completion — phase gate)*
- [ ] 05-07-PLAN.md — Wave 4: real-mode canary workflow_dispatch verification + xfail removal sweep + Decision-Coverage Audit (D-01..D-17 + CD-01..CD-09) + tokenizer-drift diagnostic (A1 assumption empirical measurement)

**Success criteria:**
- RRF fusion of BM25 + dense retrieval (top-N=100 each → fused unique 120-180)
- Cross-encoder reranker post-processes top-M=20 RRF candidates into final top-K=5
- Canary test (≥5 hand-curated cases): rerank top-3 hits > dense-only top-3 hits AND rerank top-3 hits ≥ 5, in BOTH stub-mode (every PR) and real-mode (workflow_dispatch)
- Retrieval API returns citation-ready metadata (RetrievedChunk with chunk_id, text, score, ticker, fiscal_year, item_code, char_span_in_section)
- Phase 5 adds ZERO new env vars (Settings unchanged); ZERO new tenacity wrap sites (CD-04); three CI grep gates (check_adapter_wraps, check_index_wraps, check_ingest_wraps) remain green
- `data/eval/canary/cases.jsonl` is committed (D-13); D-10 + D-16 failure messages contain verbatim CLAUDE.md hard-gate quote (Pitfall 6)
- Decision-Coverage Audit at `.planning/phases/05-retrieval-hybrid-rerank/05-DECISIONS-AUDIT.md` shows 26/26 ✓ for D-01..D-17 + CD-01..CD-09

---

## Phase 6: generation

**Status:** Planned
**Branch:** `phase/6-generation`
**Depends on:** Phase 2 (ADP-03), Phase 5 (RET-04)
**Provides:** `packages/docintel-generate/src/docintel_generate/prompts.py` with versioned prompts, generator wrapping `LLMClient`, refusal path
**Closes:** GEN-01..GEN-04

**Goal:** Ship the query-time generation layer — a new 8th workspace package `docintel-generate` with a single `prompts.py` module owning ALL canonical prompts (synthesis, refusal, judge) under a per-prompt + combined `PROMPT_VERSION_HASH`; a `Generator(bundle, retriever)` class with a 5-step `.generate(query, k) -> GenerationResult` pipeline (retrieval → format → call → parse → telemetry) exposed via a 4th sibling factory `make_generator(cfg)`; dual-layer refusal (hard zero-chunk + LLM-driven canonical sentinel); a `scripts/check_prompt_locality.sh` CI grep gate enforcing GEN-01. Also migrates the Phase 2 placeholder judge prompt + heuristic regex parser to the canonical `JUDGE_PROMPT` + provider-native structured output (Anthropic `tools=[{strict: true}]` / OpenAI `response_format={'json_schema': {'strict': true}}`) so Phase 9 inherits a stable manifest hash.

**Plans:** 7 plans across 5 waves

Plans:
**Wave 0** *(tests-first scaffolding + workspace package skeleton + grep gate + doc-path updates; both plans run in parallel — disjoint files_modified)*
- [ ] 06-01-PLAN.md — Wave 0: 10 test scaffolds (xfail-strict) for GEN-01..04 + D-03/D-09/D-14/D-16/D-17 + 2 fixture dirs (negative + noqa-escape) for the prompt-locality grep gate
- [ ] 06-02-PLAN.md — Wave 0: new 8th workspace package `docintel-generate` skeleton + `REFUSAL_TEXT_SENTINEL` in `docintel_core.types` (Pitfall 9 cycle-resolution) + `scripts/check_prompt_locality.sh` CI grep gate + 5 doc-path updates per D-02 + uv.lock regen

**Wave 1** *(blocked on Wave 0 completion)*
- [ ] 06-03-PLAN.md — Wave 1: `prompts.py` (3 named `Final[str]` prompts SYNTHESIS/REFUSAL/JUDGE + per-prompt + combined `PROMPT_VERSION_HASH` via hashlib at import time + `build_judge_user_prompt` helper) + `parse.py` (`_CHUNK_RE` + `is_refusal` helper) + `__init__.py` Wave-1 re-exports (D-07, D-08, D-10, D-11, CD-01, CD-02)

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 06-04-PLAN.md — Wave 2: `Generator` class + 5-step pipeline + `make_generator(cfg)` 4th sibling factory in `docintel_core.adapters.factory` + `GenerationResult` Pydantic model in `docintel_core.types` + `__init__.py` Wave-2 re-exports (D-03, D-13, D-14, D-15, D-16, D-17, CD-03, CD-04, CD-05, CD-06, CD-07)

**Wave 3** *(blocked on Wave 2 completion; two plans run in parallel — disjoint files_modified)*
- [ ] 06-05-PLAN.md — Wave 3: stub adapter update — `_STUB_REFUSAL` re-alias `REFUSAL_TEXT_SENTINEL` from core + `_CHUNK_RE` re-import from `docintel_generate.parse` (D-12, Pitfall 5)
- [ ] 06-06-PLAN.md — Wave 3: judge migration — remove Phase 2 placeholder `_JUDGE_SYSTEM_PROMPT`/`_build_judge_prompt`/`_SCORE_PATTERN`/`_parse_judge_response`; import `JUDGE_PROMPT` + `build_judge_user_prompt` from `docintel_generate.prompts`; provider-native structured output via 2 new `@retry`-wrapped helpers (`_judge_via_anthropic` + `_judge_via_openai`) deserializing into `JudgeVerdict`; sentinel-on-failure per Pitfall 6 (D-09, CD-09, Pitfall 6, Pitfall 8)

**Wave 4** *(blocked on Wave 3 completion — phase gate, CHECKPOINT)*
- [ ] 06-07-PLAN.md — Wave 4: CI YAML step wiring (D-06) + xfail-removal sweep (20 markers across 9 test files; `test_generator_real_hero.py` xfail preserved per Phase 5 precedent) + Decision-Coverage Audit at `.planning/phases/06-generation/06-DECISIONS-AUDIT.md` (27/27 ✓ for D-01..D-17 + CD-01..CD-10 + Pitfall 9 resolution) + developer-review checkpoint

**Success criteria:**
- All prompts live in `packages/docintel-generate/src/docintel_generate/prompts.py`; grep for inline string-literal prompts outside this file returns zero matches (CI gate via `scripts/check_prompt_locality.sh`)
- Each prompt has a deterministic per-prompt + combined `PROMPT_VERSION_HASH` (sha256[:12] hex) exposed for Phase 10's EVAL-02 manifest header
- Stub generator returns deterministic placeholder answers covering the full schema; new canonical refusal sentinel `"I cannot answer this question from the retrieved 10-K excerpts."` replaces Phase 2 placeholder
- Dual-layer refusal: hard zero-chunk skip (`Generator` Step B) AND LLM-driven canonical sentinel detection (`Generator` Step D)
- `Generator.generate(query, k) -> GenerationResult` single seam exposed; `make_generator(cfg)` 4th sibling factory composes adapters + retriever
- Phase 6 adds ZERO new env vars (Settings unchanged per FND-11); ZERO new tenacity wrap sites on `Generator.generate()` (CD-04 inherited; helpers in judge.py preserve wrap-discipline per ADP-06); four CI grep gates (`check_adapter_wraps`, `check_index_wraps`, `check_ingest_wraps`, `check_prompt_locality`) all green
- Judge migration: `_JUDGE_SYSTEM_PROMPT` / heuristic `_SCORE_PATTERN` retired; provider-native structured output (Anthropic `tools=[{strict: true}]` / OpenAI `response_format={'type': 'json_schema', 'strict': true}`) deserializes directly into `JudgeVerdict`
- Decision-Coverage Audit at `.planning/phases/06-generation/06-DECISIONS-AUDIT.md` shows 27/27 ✓ for D-01..D-17 + CD-01..CD-10 + Pitfall 9 resolution

---

## Phase 7: answer-schema

**Status:** Pending
**Branch:** `phase/7-answer-schema`
**Depends on:** Phase 6 (GEN-*)
**Provides:** Pydantic `Answer` + `Citation` models with quote spans
**Closes:** ANS-01..ANS-03

**Success criteria:**
- `Answer` carries `text`, `citations`, `confidence`, `refused`, `prompt_version_hash`
- `Citation` carries `chunk_id`, `company`, `fiscal_year`, `section`, quote span
- Every claim in `Answer.text` anchored to ≥1 citation (faithfulness precondition; checked in Phase 9)

---

## Phase 8: ground-truth-eval-set

**Status:** Pending (parallelizable with Phases 4–7)
**Branch:** `phase/8-ground-truth-eval-set`
**Depends on:** Phase 3 (ING-01)
**Provides:** Hand-curated eval set (≥30 questions) with gold passages, gold answers, expected citations
**Closes:** GT-01..GT-03

**Success criteria:**
- ≥30 questions spanning single-doc factual, multi-doc comparative, out-of-corpus refusal
- Gold passages + gold answers + expected citations per question
- Committed under `data/eval/ground_truth/`

**Note:** This phase is parallelizable with Phases 4–7 since it only needs the corpus to exist (Phase 3). Doing it in parallel buys time for Phase 9.

---

## Phase 9: metrics

**Status:** Pending
**Branch:** `phase/9-metrics`
**Depends on:** Phase 7 (ANS-*) AND Phase 8 (GT-*)
**Provides:** Hit@K, MRR, faithfulness, citation accuracy, latency, $/query — with Wilson CIs on rates and bootstrap CIs on deltas
**Closes:** MET-01..MET-06

**Success criteria:**
- Hit@{1,3,5,10}, MRR computed against gold passages with Wilson CIs
- Faithfulness scored by `LLMJudge` (stub-mode works); Wilson CIs
- Citation accuracy with Wilson CIs
- Latency p50/p95 and $/query per-stage and end-to-end
- Bootstrap CI implementation for deltas (used in Phase 11 ablations)

---

## Phase 10: eval-harness

**Status:** Pending
**Branch:** `phase/10-eval-harness`
**Depends on:** Phase 9 (MET-*)
**Provides:** `docintel-eval run` CLI; report writer with mandatory manifest header; CI integration
**Closes:** EVAL-01..EVAL-04

**Success criteria:**
- `docintel-eval run` executes full pipeline against eval set
- Reports under `data/eval/reports/<timestamp>/` with manifest header: `embedder.name`, `reranker.name`, `generator.name`, `prompt_version_hash`, git SHA
- Reports committed (`data/eval/reports/*.md` is NOT gitignored)
- Stub-mode run completes in CI on every PR; real-key gated behind manual `workflow_dispatch`

---

## Phase 11: ablation-studies

**Status:** Pending
**Branch:** `phase/11-ablation-studies`
**Depends on:** Phase 10 (EVAL-*)
**Provides:** ≥3 ablations with bootstrap-CI deltas
**Closes:** ABL-01, ABL-02

**Success criteria:**
- No-rerank, dense-only (BM25 off), chunk-size sweep ablations land
- Bootstrap CIs reported on every delta vs. baseline
- Single comparison table in the run's report

---

## Phase 12: observability

**Status:** Pending
**Branch:** `phase/12-observability`
**Depends on:** Phase 1 (FND-02 wired `merge_contextvars` into `configure_logging`)
**Provides:** `trace_id` propagation via `structlog.contextvars`, per-stage timings + token counts in structured logs, UI Traces tab populated
**Closes:** OBS-01..OBS-03

**Success criteria:**
- Every request carries a `trace_id` that appears in every log line for that request
- Per-stage timings and token counts emitted as structured fields
- No unstructured `print` calls anywhere (CI grep gate)
- UI Traces tab shows per-request timeline

---

## Phase 13: api-ui-polish

**Status:** Pending
**Branch:** `phase/13-api-ui-polish`
**Depends on:** Phase 11 (ABL-*) AND Phase 12 (OBS-*)
**Provides:** Polished API + Streamlit UI, hero GIF, README rewritten from measurements, ≥8 ADRs in `DECISIONS.md`
**Closes:** UI-01..UI-06

**Phase 13 carries disproportionate recruiter weight.** Protect its time.

**Success criteria:**
- Streamlit tabs: `Query`, `Traces`, `Eval Results` (labels locked in Phase 1 Plan 04 per D-16)
- Citations are hoverable; hover surfaces cited chunk text
- Hero GIF answers the locked multi-hop comparative question + the refusal demo
- README rewritten from real measurements — not from the plan
- `DECISIONS.md` ships with ≥8 ADRs
- `git clone && docker-compose up` produces a working demo on a fresh machine (one-command demo gate)

---

## Phase 14: v2-deferred

**Status:** Deferred (out of scope for v1)
**Branch:** (not started)
**Provides:** Tracking shell for V2-* requirements (multi-modal, table-aware chunking, query rewriting, multi-tenant, online ingestion, prompt-version A/B)
**Closes:** V2-01..V2-06

Not in current roadmap. Listed here so the requirements have a destination and the v1 boundary stays explicit.

---

## Coverage check

| Phase | Requirements | Status |
|-------|--------------|--------|
| 1 | FND-01..FND-11 (11) | ✓ Complete |
| 2 | ADP-01..ADP-07 (7) | Pending — next |
| 3 | ING-01..ING-04 (4) | Pending |
| 4 | IDX-01..IDX-04 (4) | Pending |
| 5 | RET-01..RET-04 (4) | Pending (canary gate) |
| 6 | GEN-01..GEN-04 (4) | Pending |
| 7 | ANS-01..ANS-03 (3) | Pending |
| 8 | GT-01..GT-03 (3) | Pending (parallelizable with 4–7) |
| 9 | MET-01..MET-06 (6) | Pending |
| 10 | EVAL-01..EVAL-04 (4) | Pending |
| 11 | ABL-01..ABL-02 (2) | Pending |
| 12 | OBS-01..OBS-03 (3) | Pending |
| 13 | UI-01..UI-06 (6) | Pending |
| 14 | V2-01..V2-06 (6) | Deferred |

**v1 total:** 53 requirements across 13 phases. All mapped.

---
*Roadmap defined: 2026-04-28 (original)*
*Last updated: 2026-05-11 — reconstructed from CLAUDE.md + Phase 1 SUMMARYs*
