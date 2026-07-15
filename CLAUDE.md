# docintel — Project Guide for Claude Code

This file is loaded into every Claude Code session for this project. Keep it short and load-bearing.

## What this project is

Production-shaped Retrieval-Augmented Generation system over SEC 10-K filings. Portfolio artifact for AI-engineering roles. Audience: recruiters AND senior AI engineers (dual). Build window: 4–5 focused days.

**Headline artifact = the eval harness, not the chat UI.** Hit@5, MRR, faithfulness, citation accuracy, latency, $/query are reported with real numbers, with Wilson CIs on rates and bootstrap CIs on deltas. CI runs the full eval suite on every PR (stub mode by default; real-key on manual trigger only).

## Authoritative sources

This is a **BMAD-exclusive** repo. Read these first when picking up work:

1. **`/Users/michaelmarrero/Downloads/projectspec.md`** — original engineering spec (Sections 1–12). Locks the stack, the architecture, and the operating rules. Defer to it.
2. **`_bmad-output/implementation-artifacts/sprint-status.yaml`** — current epic/story status (source of truth for what's done and what's next).
3. **`_bmad-output/implementation-artifacts/*.md`** — per-story specs (`<epic>-<story>-*.md`) and `deferred-work.md`.
4. **`_bmad-output/planning-artifacts/`** — PRD, epics, requirements.
5. **`docs/`** — architecture, data models, API contracts, deployment/dev guides (local only, gitignored).

## Operating rules (from spec §10)

- **One story = one branch:** `git checkout -b story/<epic>-<story>-<name>` before any code.
- **Tests before code where possible**, especially for the eval harness.
- **No hidden state.** Every config goes through `src/docintel/config.py` (Pydantic v2 + `pydantic-settings`). No magic env reads in random modules.
- **All prompts live in `packages/docintel-generate/src/docintel_generate/prompts.py`**, versioned with a hash. Grep for inline string-literal prompts must return zero matches.
- **No silent retries on LLM calls.** Every LLM/embedding call wrapped with `tenacity` retry that logs each attempt via `before_sleep_log`.
- **Adapters/protocols for swappable components.** `Embedder`, `Reranker`, `LLMClient`, `LLMJudge` — protocols + at least one real adapter + one stub adapter each. Single factory `make_adapters(cfg)` reads `LLM_PROVIDER`.
- **Offline-first.** `LLM_PROVIDER=stub` is the default everywhere (CI, `.env.example`, `docker-compose.yml`). Stubs are deterministic and cover the entire pipeline including eval.
- **Commit `data/eval/reports/*.md`** — they are part of the artifact.
- **README is rewritten last** — from real measurements, not from the plan.

## Engineering canaries (easy to miss, expensive to get wrong)

- **Adapters/protocols/stubs must land before embedding/indexing.** If protocols slip, eval-in-CI becomes theater.
- **Reranker silent-truncation is the #1 subtle failure.** The cross-encoder must measurably improve top-3 hit rate vs. dense-only on ≥5 hand-written cases. If that gate fails, look at BGE 512-token truncation FIRST — before suspecting hybrid retrieval, RRF, or chunk size. The canary exists specifically to catch it.
- **Metrics depend on the Answer schema AND ground truth.** Both must exist before scoring.
- **The API+UI+polish work carries disproportionate recruiter weight** — multi-hop hero GIF, hoverable citations, README from measurements, ≥8 ADRs in DECISIONS.md. Protect its time.

## Demo story (locked)

Hero GIF answers a **multi-hop comparative question across companies** (e.g., "Which of these companies grew R&D while margins shrank in 2023?"). This question type stresses hybrid retrieval + cross-doc synthesis and is the hardest to fake. A refusal demo on an out-of-corpus question is also visible in the same recording.

## Constraints worth re-stating

- **No API keys at build time.** Everything that touches OpenAI or Anthropic is behind an adapter and gated by `LLM_PROVIDER`. Stubs are deterministic.
- **One-command demo.** `git clone && docker-compose up` produces a working demo on a fresh machine. Non-negotiable per spec §11.
- **Eval-in-CI.** GitHub Actions runs the full eval suite on every PR (stub mode). Reports committed under `data/eval/reports/<timestamp>/` with a mandatory manifest header (`embedder.name`, `reranker.name`, `generator.name`, `prompt_version_hash`, git SHA).
- **Corpus = SEC 10-Ks**, 10–20 companies, last 3 years. Stored under `data/corpus/` (gitignored). Provide `make fetch-corpus` for reproducibility.
- **BMAD workspace + generated docs stay local.** `_bmad/`, `_bmad-output/`, and `docs/` are gitignored — the public repo is just the source, tests, and committed eval reports. Commits are code + tests only.

## How to run a story (BMAD)

Per-story cycle: branch → dev → test → code-review → commit. All four epics (1–4) are `done`; see `sprint-status.yaml` for status and `deferred-work.md` for what's parked.

```
create-story        # spec the next story from the epic
dev-story           # implement against the story spec
code-review         # adversarial review in fresh context
```

---
*BMAD-exclusive repo. GSD artifacts removed 2026-07-15.*
