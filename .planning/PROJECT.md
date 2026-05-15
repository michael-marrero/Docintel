# docintel

## What This Is

Production-shaped Retrieval-Augmented Generation system over SEC 10-K filings, built as a portfolio artifact for AI-engineering roles. Audience is dual: recruiters who need to skim the README and senior AI engineers who will read the code and the evaluation reports. Build window is 4–5 focused days.

## Core Value

**The eval harness is the headline artifact, not the chat UI.** Hit@5, MRR, faithfulness, citation accuracy, latency, and $/query are reported on a held-out reference set with real numbers — Wilson CIs on rates, bootstrap CIs on deltas — and every PR re-runs the full suite in CI (stub mode by default, real-key on manual trigger only).

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ **FND-01** uv workspace with `packages/*` members — Phase 1
- ✓ **FND-02** `docintel_core` package (Settings, structlog config, version export) — Phase 1
- ✓ **FND-06** pre-commit hygiene (ruff + black + gitleaks pinned, shared `.gitleaks.toml`) — Phase 1
- ✓ **FND-08** `LLM_PROVIDER=stub` is the offline-first default in `.env.example`, CI, and docker-compose — Phase 1
- ✓ **FND-09** GitHub Actions CI workflow runs uv lock check + ruff/black/mypy/pytest + gitleaks — Phase 1 (per `f40bca7` merge of `phase/1-scaffold-foundation`)

### Active

<!-- Current scope. Building toward these. -->

- [ ] **Phase 2** Adapter protocols (`Embedder`, `Reranker`, `LLMClient`, `LLMJudge`) + at least one real + one stub adapter each + `make_adapters(cfg)` factory keyed on `Settings.llm_provider`. Tenacity retry wraps every LLM call.
- [ ] **Phase 3** SEC 10-K corpus fetcher and on-disk layout (`data/corpus/`, gitignored, `make fetch-corpus`).
- [ ] **Phase 4** Embedding + index build over the corpus (depends on Phase 2 protocols).
- [ ] **Phase 5** Hybrid retrieval (BM25 + dense) with RRF + cross-encoder reranker. Carries the **silent-truncation canary** as a structural acceptance gate: cross-encoder must measurably improve top-3 hit rate vs. dense-only on ≥5 hand-written cases.
- [ ] **Phase 6** Generation: prompts module (`packages/docintel-generate/src/docintel_generate/prompts.py`) with version hashes; all LLM calls wrapped in tenacity retry with `before_sleep_log`.
- [ ] **Phase 7** `Answer` schema with citations + confidence (consumed by metrics).
- [ ] **Phase 8** Ground-truth eval set (parallelizable with Phases 4–7).
- [ ] **Phase 9** Metrics: Hit@K, MRR, faithfulness, citation accuracy, latency, $/query. Wilson CIs on rates, bootstrap CIs on deltas. Depends on Phases 7 + 8.
- [ ] **Phase 10** Eval harness + report renderer (manifest header per report: embedder/reranker/generator names, `prompt_version_hash`, git SHA).
- [ ] **Phase 11** Ablation studies (no-rerank, dense-only, chunk-size sweep).
- [ ] **Phase 12** Observability (structlog `trace_id` via contextvars; the foundation is already wired in Phase 1's `configure_logging`).
- [ ] **Phase 13** API + UI + polish: multi-hop hero GIF, hoverable citations, README rewritten from real measurements, ≥8 ADRs in `DECISIONS.md`. Depends on Phases 11 + 12.

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- **Multi-modal / image-bearing 10-K exhibits** — adds ingestion complexity that does not stress retrieval or eval design; deferred to v2 (Phase 14).
- **Online learning / fine-tuning of the embedder or generator** — out of scope for a portfolio artifact built in 4–5 days; the story is "engineering quality of a RAG system," not "we trained a model."
- **Multi-tenant / auth-protected API** — the demo is single-user; auth would be theater for the audience.
- **Live SEC EDGAR ingestion in the demo path** — corpus is pre-fetched into `data/corpus/`; `make fetch-corpus` exists for reproducibility but the one-command demo never hits the network.
- **Real LLM/embedding API calls at build time** — all real-API code paths sit behind adapter protocols gated by `LLM_PROVIDER`; stubs are deterministic and cover the entire pipeline including eval.
- **Chat-style multi-turn UI** — single-turn Q&A is enough to showcase retrieval + citation + faithfulness. Chat history would dilute the eval story.

## Context

- Repository is a **fresh clone** as of 2026-05-11. `.planning/` is gitignored (`commit_docs=false`); the public repo is just the source plus committed `data/eval/reports/*.md` artifacts.
- Phase 1 (scaffold-foundation) is **complete and merged to main** (`f40bca7`). The uv workspace, four sub-packages (`docintel-core`, `docintel-api`, `docintel-ui`, `docintel-eval`), `Settings`, structlog config, secrets-hygiene tooling, and CI workflow all exist on disk and pass.
- Phase 1 SUMMARYs (`01-01-SUMMARY.md`, `01-02-SUMMARY.md`) survive under `.planning/phases/01-scaffold-foundation/` and are the highest-fidelity record of decisions D-01..D-25 and the FND-* requirement IDs.
- The original `projectspec.md` (Sections 1–12) lived under `~/Downloads/` on the original build machine and was **not recovered** in this clone. This `PROJECT.md` is reconstructed from `CLAUDE.md` and the Phase 1 SUMMARYs; some prose is paraphrased rather than quoted.
- Corpus: SEC 10-K filings, 10–20 companies × last 3 years, stored under `data/corpus/` (gitignored).
- Demo story is locked: hero GIF answers a **multi-hop comparative question across companies** (e.g., "Which of these companies grew R&D while margins shrank in 2023?"), plus a refusal demo on an out-of-corpus question in the same recording.

## Constraints

- **Tech stack**: uv 0.11.8 workspace, Python 3.11, Pydantic v2.13 + `pydantic-settings` 2.14, structlog 25.5, FastAPI 0.136, Streamlit 1.56, sentence-transformers 5.4, hatchling as build backend. Pinned in `uv.lock`. Adding deps requires an updated lockfile and an ADR.
- **Offline-first**: `LLM_PROVIDER=stub` is the default in `.env.example`, CI, and docker-compose. Stubs are deterministic and cover the entire pipeline including eval. No API keys at build time.
- **Single env reader**: every config value flows through `src/docintel/config.py` (Pydantic v2 + `pydantic-settings`, `env_prefix="DOCINTEL_"`). Grep for `os.environ` / `os.getenv` outside that file must return zero matches (CI gate).
- **No silent retries on LLM calls**: every LLM/embedding call is wrapped with `tenacity` and logs each attempt via `before_sleep_log`.
- **Prompts are versioned**: all prompts live in `packages/docintel-generate/src/docintel_generate/prompts.py` with a hash. Grep for inline string-literal prompts must return zero matches (CI gate via `scripts/check_prompt_locality.sh`).
- **Adapters/protocols for swappable components**: `Embedder`, `Reranker`, `LLMClient`, `LLMJudge` — protocols + ≥1 real adapter + 1 stub adapter each. Single factory `make_adapters(cfg)` reads `LLM_PROVIDER`.
- **One-command demo**: `git clone && docker-compose up` produces a working demo on a fresh machine. Non-negotiable.
- **Eval-in-CI**: GitHub Actions runs the full eval suite on every PR (stub mode). Reports committed under `data/eval/reports/<timestamp>/` with a mandatory manifest header.
- **One phase = one branch**: `git checkout -b phase/<N>-<name>` before any code. Tests-before-code where possible, especially for the eval harness.
- **README is rewritten last**, from real measurements, not from the plan.
- **Timeline**: 4–5 focused days. Phase 13 carries disproportionate recruiter weight — protect its time.

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Eval harness (not chat UI) is the headline artifact | Recruiter+engineer audience reads measurements, not screenshots; this is what differentiates the portfolio piece | — Pending (validated when Phase 13 lands) |
| uv workspace with per-package pyproject (D-01..D-04) | Hard module boundaries between core/api/ui/eval; per-service Docker images stay small; deviates from spec's flat layout | ✓ Good — Phase 1 shipped clean |
| `LLM_PROVIDER=stub` default everywhere (D-11/D-20) | Offline-first is what makes one-command demo and eval-in-CI feasible without burning keys on every PR | ✓ Good — triple-redundant default (.env.example + CI + docker-compose) |
| Pydantic `Settings` as the single env reader (D-03) with `env_prefix="DOCINTEL_"` | Prevents hidden env reads in random modules; CI greps for `os.environ`/`os.getenv` outside config.py | ✓ Good — Phase 1 grep gate passes |
| `.planning/` gitignored (`commit_docs=false`) | Public repo stays focused on source + eval reports; planning is a build-time scaffold | ✓ Good — but bit us once: this clone has no PROJECT.md until reconstruction |
| Cross-encoder reranker is gated by a hand-written hit-rate canary (Phase 5) | Without the canary, BGE 512-token silent truncation can hide a regression for weeks | — Pending (verified in Phase 5) |
| Reports under `data/eval/reports/` are committed | They *are* the artifact; ignoring them would defeat the point of eval-in-CI | ✓ Good — gitignore explicitly excludes the cache but tracks reports |
| Demo question is multi-hop comparative across companies | Stresses hybrid retrieval + cross-doc synthesis; hardest type to fake | — Pending (verified in Phase 13) |
| README rewritten from real measurements only at the end | Numbers in a README written from the plan rot the moment reality drifts | — Pending |
| Hatchling as build backend; mypy `ignore_missing_imports=true` for Phase 1 only (D-12) | Tightens when Phase 2 lands typed protocols | ⚠️ Revisit at Phase 2 |

---
*Last updated: 2026-05-11 after reconstruction from CLAUDE.md + Phase 1 SUMMARYs (projectspec.md not recoverable in this fresh clone)*
