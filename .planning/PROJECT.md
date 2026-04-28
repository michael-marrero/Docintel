# docintel — Document Intelligence RAG

## What This Is

A production-shaped Retrieval-Augmented Generation system over SEC 10-K filings. It ingests heterogeneous PDFs (native and scanned), runs hybrid retrieval (BM25 + dense FAISS + RRF) with cross-encoder reranking, and produces grounded answers with inline citations and refusal logic. The deliverable is a portfolio artifact targeted at both recruiters (30-second scan) and senior AI engineers (30-minute defensible deep read).

## Core Value

**A defensible end-to-end RAG pipeline whose evaluation harness — not whose chat UI — is the headline.** Hit@5, MRR, faithfulness, citation accuracy, latency, and cost are reported with real numbers; one ablation is run; CI proves the eval suite is reproducible.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Ingestion & parsing**
- [ ] Detect scanned vs native PDFs by extracted-text density per page
- [ ] Parse native PDFs via `unstructured` / `pypdf` / `pdfplumber` (tables → pdfplumber)
- [ ] OCR scanned content with Tesseract via `pytesseract`
- [ ] Persist chunks to SQLite keyed by `(doc_id, chunk_id, text, source_page, parser_used)`

**Chunking**
- [ ] Recursive chunker (default) behind a `Chunker` protocol
- [ ] Semantic chunker behind the same protocol

**Embedding & indexing**
- [ ] `Embedder` protocol with OpenAI `text-embedding-3-small` adapter (gated behind a flag — keys absent at build time)
- [ ] BGE-base adapter behind the same protocol
- [ ] FAISS dense index (persisted)
- [ ] BM25 sparse index via `rank_bm25` (persisted)

**Retrieval**
- [ ] Hybrid retrieval: BM25 top-50 + dense top-50 → Reciprocal Rank Fusion
- [ ] Cross-encoder reranker (`bge-reranker-base`); Cohere Rerank adapter behind interface
- [ ] Metadata-filtered retrieval (date ranges, entities, doc types)

**Structured extraction**
- [ ] Pydantic `DocumentMetadata` schema (doc_type, title, parties, primary_dates, summary, key_entities)
- [ ] Claude tool-use extractor with retry on validation error
- [ ] Persist extracted metadata to SQLite keyed by `doc_id`

**Generation & citations**
- [ ] Versioned, hashed prompts in `generation/prompts.py` — no scattered string literals
- [ ] Synthesizer returns `{answer, citations: [{chunk_id, doc_id, page}], confidence}`
- [ ] Refusal logic when reranker top-1 score < threshold

**Evaluation harness (the headline)**
- [ ] ≥ 30 hand-curated Q&A pairs in `data/eval/ground_truth.jsonl` (10 factual, 10 multi-hop, 5 edge, 5 out-of-corpus)
- [ ] Synthetic Q&A generator with second-pass quality filter
- [ ] Retrieval metrics: Hit@1, Hit@5, MRR@10
- [ ] Generation metrics: faithfulness (LLM-judge), citation accuracy, refusal correctness
- [ ] System metrics: P50/P95 latency per stage, total tokens, $/query
- [ ] Timestamped markdown report committed to `data/eval/reports/`
- [ ] Eval suite runs in CI on PR
- [ ] At least one ablation (chunking strategy or reranker on/off) reported in README

**Observability**
- [ ] `trace_id` via `contextvars` propagated through every stage
- [ ] JSONL trace log with `{trace_id, stage, duration_ms, input_tokens, output_tokens, cost_usd}`
- [ ] Streamlit "Traces" page rendering recent queries

**Serving & demo**
- [ ] FastAPI: `POST /query`, `GET /trace/{id}`, `GET /health`
- [ ] Streamlit demo: query box, hoverable citations, traces page, eval-results page
- [ ] One-command setup: `docker-compose up` from a fresh clone
- [ ] 30–60s screen recording embedded in README
- [ ] README written from scratch with hero GIF, eval table, architecture diagram, decisions link
- [ ] DECISIONS.md with ≥ 8 ADR-style entries

**Operating discipline (per spec §10)**
- [ ] One phase = one branch (`phase/N-name`)
- [ ] Tests before code where possible (especially eval)
- [ ] All config through `config.py` (Pydantic settings) — no magic env reads
- [ ] All LLM calls wrapped with tenacity retry that logs each attempt — no silent retries
- [ ] All adapters (embedder, retriever, reranker, generator) behind protocols
- [ ] Both API providers (Anthropic, OpenAI) gated behind a flag so the system is developable offline with stubs

### Out of Scope (v1)

- **Real-time ingestion / file-watcher** — batch-only is enough to demo; spec doesn't require it.
- **Multi-tenant auth, user accounts** — single-user portfolio demo.
- **Cohere Rerank as default** — adapter exists, BGE is default; Cohere is benchmarked-only if pursued (Phase 9).
- **Agentic retrieval (tool-use loop)** — deferred to Phase 9.
- **Redis cache** — deferred to Phase 9.
- **Phoenix/Langfuse trace export** — JSONL is sufficient; deferred to Phase 9.
- **Multiple corpora simultaneously** — spec says "do not mix corpora in v1." SEC 10-Ks only.
- **Next.js UI** — Streamlit ships in hours; Next.js is a stretch only if Phase 8 has slack.
- **Vector store other than FAISS** — abstracted behind interface; swap path documented in DECISIONS.md but not implemented.

## Context

- **Source spec:** `/Users/michaelmarrero/Downloads/projectspec.md` is the authoritative scope and design document. Every architectural choice has an interview-defensible rationale already written. Refer back to it before deviating.
- **Audience is dual:** recruiters scan, senior engineers dig. README must be polished AND DECISIONS.md must be deep. Both are first-class artifacts.
- **Demo story:** the hero GIF answers a multi-hop comparative question across multiple companies (e.g., "Which of these reported declining margins while increasing R&D in 2023?"). This question type stresses hybrid retrieval + cross-doc synthesis and is the hardest to fake.
- **Corpus:** SEC 10-Ks, 10–20 companies, last 3 years. Stored under `data/corpus/` (gitignored). Provide `make fetch-corpus` for reproducibility — commit only source URLs and dates.
- **No API keys at build time.** Everything that touches OpenAI or Anthropic must be behind an adapter and gated by a flag (e.g., `LLM_PROVIDER=stub`). Stubs return deterministic fixtures so tests and the eval harness can run end-to-end without network.

## Constraints

- **Tech stack**: Python 3.11+, FastAPI, Pydantic v2, FAISS, `rank_bm25`, `bge-reranker-base`, Anthropic Claude (Sonnet) for generation, OpenAI `text-embedding-3-small` for embeddings, Tesseract for OCR, SQLite for metadata, `structlog` for logging, Streamlit for UI, Docker for packaging — locked by spec §3.
- **Timeline**: 4–5 focused days target build window per spec.
- **Provider keys**: absent at build time; system must be developable and testable offline via stub adapters.
- **No vendor lock-in for v1**: vector store and reranker behind protocols; Pinecone/Weaviate/Cohere swap paths documented in DECISIONS.md, not implemented.
- **One-command demo**: `git clone && docker-compose up` must produce a working demo on a fresh machine. This is non-negotiable per spec §11.
- **Eval-in-CI**: GitHub Actions runs the full eval suite on every PR. Reports committed to `data/eval/reports/`.
- **Branching**: each phase opens `phase/N-name`, ends with passing tests, merges to main only after acceptance criteria pass.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Corpus = SEC 10-Ks | Demos well to legal-tech reviewers without being legal-themed; stresses long docs + tables + structured exhibits; the spec's recommended option | — Pending |
| Audience = recruiters AND senior engineers | Forces both polish (README) and depth (DECISIONS.md, eval rigor); raises the bar but expands reach | — Pending |
| Demo story = multi-hop comparative question | Hardest to fake; showcases hybrid retrieval + cross-doc reasoning; the single most defensible thing in a screen recording | — Pending |
| Roadmap granularity = fine, with eval split | Phase 6 (Eval) is the headline per spec; splitting it into ground-truth curation, metrics, CI integration, and ablation maximizes traceable artifacts | — Pending |
| Stretch (Phase 9) = include as deferred phases | Keeps the door open for ablation matrix / Cohere benchmark / agentic retrieval without bloating v1; signals awareness of next steps | — Pending |
| API keys absent → stub-first build | All LLM/embedding calls behind adapter + flag; deterministic stubs let CI and offline dev run end-to-end | — Pending |
| Use GSD workflow for execution | Phase-by-phase discuss → plan → execute matches the spec's branch-per-phase model and produces ADR/decision artifacts naturally | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-28 after initialization*
