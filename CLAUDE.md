# docintel — Project Guide for Claude Code

This file is loaded into every Claude Code session for this project. Keep it short and load-bearing.

## What this project is

Production-shaped Retrieval-Augmented Generation system over SEC 10-K filings. Portfolio artifact for AI-engineering roles. Audience: recruiters AND senior AI engineers (dual). Build window: 4–5 focused days.

**Headline artifact = the eval harness, not the chat UI.** Hit@5, MRR, faithfulness, citation accuracy, latency, $/query are reported with real numbers, with Wilson CIs on rates and bootstrap CIs on deltas. CI runs the full eval suite on every PR (stub mode by default; real-key on manual trigger only).

## Authoritative sources

Read these first when picking up work:

1. **`/Users/michaelmarrero/Downloads/projectspec.md`** — original engineering spec (Sections 1–12). Locks the stack, the architecture, the phase structure, and the operating rules. Defer to it.
2. **`.planning/PROJECT.md`** — current project state, core value, key decisions.
3. **`.planning/ROADMAP.md`** — 14 phases (13 v1 + Phase 14 v2 deferred). Every requirement is mapped. Depends-on chains encode hard sequencing constraints.
4. **`.planning/REQUIREMENTS.md`** — REQ-IDs and traceability table.
5. **`.planning/research/SUMMARY.md`** — synthesized findings from 4 parallel research agents (Stack, Features, Architecture, Pitfalls). Has the roadmapper quick-reference at the end.
6. **`.planning/research/{STACK,FEATURES,ARCHITECTURE,PITFALLS}.md`** — drill into specifics when planning a phase.

## Operating rules (from spec §10)

- **One phase = one branch:** `git checkout -b phase/<N>-<name>` before any code.
- **Tests before code where possible**, especially for the eval harness.
- **No hidden state.** Every config goes through `src/docintel/config.py` (Pydantic v2 + `pydantic-settings`). No magic env reads in random modules.
- **All prompts live in `packages/docintel-generate/src/docintel_generate/prompts.py`**, versioned with a hash. Grep for inline string-literal prompts must return zero matches.
- **No silent retries on LLM calls.** Every LLM/embedding call wrapped with `tenacity` retry that logs each attempt via `before_sleep_log`.
- **Adapters/protocols for swappable components.** `Embedder`, `Reranker`, `LLMClient`, `LLMJudge` — protocols + at least one real adapter + one stub adapter each. Single factory `make_adapters(cfg)` reads `LLM_PROVIDER`.
- **Offline-first.** `LLM_PROVIDER=stub` is the default everywhere (CI, `.env.example`, `docker-compose.yml`). Stubs are deterministic and cover the entire pipeline including eval.
- **Commit `data/eval/reports/*.md`** — they are part of the artifact.
- **README is rewritten last** — from real measurements, not from the plan.

## Hard sequencing constraints

Encoded in ROADMAP.md `Depends on` lines, but worth surfacing here because they're easy to miss:

- **Phase 2 (adapters/protocols/stubs) must land before Phase 4 (embedding/indexing).** If protocols slip, eval-in-CI becomes theater.
- **Phase 5 carries the reranker silent-truncation canary as a structural acceptance gate.** Cross-encoder must measurably improve top-3 hit rate vs. dense-only on ≥5 hand-written cases. If that gate fails, look at BGE 512-token truncation FIRST — before suspecting hybrid retrieval, RRF, or chunk size. This is the most common subtle failure mode and the canary exists specifically to catch it.
- **Phase 9 (metrics) depends on Phase 7 (Answer schema) AND Phase 8 (ground truth).** Both must exist; ground truth is parallelizable with Phases 4–7.
- **Phase 13 (API+UI+polish) depends on Phase 11 (ablation) AND Phase 12 (observability).** Phase 13 carries disproportionate recruiter weight — multi-hop hero GIF, hoverable citations, README from measurements, ≥8 ADRs in DECISIONS.md. Protect this phase's time.

## Demo story (locked)

Hero GIF answers a **multi-hop comparative question across companies** (e.g., "Which of these companies grew R&D while margins shrank in 2023?"). This question type stresses hybrid retrieval + cross-doc synthesis and is the hardest to fake. A refusal demo on an out-of-corpus question is also visible in the same recording.

## Constraints worth re-stating

- **No API keys at build time.** Everything that touches OpenAI or Anthropic is behind an adapter and gated by `LLM_PROVIDER`. Stubs are deterministic.
- **One-command demo.** `git clone && docker-compose up` produces a working demo on a fresh machine. Non-negotiable per spec §11.
- **Eval-in-CI.** GitHub Actions runs the full eval suite on every PR (stub mode). Reports committed under `data/eval/reports/<timestamp>/` with a mandatory manifest header (`embedder.name`, `reranker.name`, `generator.name`, `prompt_version_hash`, git SHA).
- **Corpus = SEC 10-Ks**, 10–20 companies, last 3 years. Stored under `data/corpus/` (gitignored). Provide `make fetch-corpus` for reproducibility.
- **`.planning/` is gitignored** (commit_docs=false). Planning docs stay local; the public repo is just the source.

## How to start a new phase

```
/gsd-discuss-phase <N>     # gather context, clarify approach
/gsd-plan-phase <N>        # create PLAN.md with task breakdown + verification loop
/gsd-execute-phase <N>     # execute plans with atomic commits
```

Phase 1 is up next.

---
*Generated 2026-04-28 after `/gsd-new-project` initialization.*
