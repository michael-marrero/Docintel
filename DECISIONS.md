# Architectural Decisions

This document is the synthesized ADR record for docintel — a production-shaped
Retrieval-Augmented Generation system over SEC 10-K filings. Each ADR captures
one load-bearing decision made during build, sourced from the per-phase
decision logs and the project's two empirical findings (a refuted assumption
and a structural stub-mode limitation that shaped the ablation harness).

The template is **Context / Decision / Consequences**. Pluses (`+`) call out
the value the decision delivered; minuses (`-`) call out the cost it locked
in. None of these decisions are aspirational — every one is backed by code
in this repo and tests in `tests/`.

---

## ADR-001: Offline-first stub default everywhere

**Status:** Accepted

**Context:**
The project's headline artifact is the evaluation harness — Hit@K, MRR,
faithfulness, citation accuracy, latency, cost — reported with Wilson CIs on
rates and bootstrap CIs on deltas. Reviewers without API keys must be able
to clone the repo, run the full pipeline, and reproduce the eval suite. CI
must run the same suite on every PR without burning OpenAI/Anthropic credit
on each commit. A portfolio piece that requires keys to demonstrate excludes
its audience and breaks on every fork.

**Decision:**
`DOCINTEL_LLM_PROVIDER=stub` is the default in `.env.example`,
`docker-compose.yml`, and every CI job. Every swappable component
(`Embedder`, `Reranker`, `LLMClient`, `LLMJudge`) ships a stub adapter
alongside the real one, and stubs are deterministic — the same input always
produces the same output. CI's `lint-and-test` job runs the full eval suite
in stub mode on every PR; real-mode runs only on manual `workflow_dispatch`.

**Consequences:**

- + Any reviewer can run `docker-compose up` on a fresh clone and exercise
  every code path — query, traces, eval tables, ablation deltas — with zero
  API keys.
- + CI is fast and cheap (no API billing per PR) while still gating real
  behavior change via the full eval suite.
- + Every stub-mode report is labeled `representative: false` in its
  manifest, the UI's Eval-Results tab carries a prominent banner, and the
  README marks its placeholder numbers the same way.
- - Real-mode published numbers depend on a manual `gh workflow run` step.
  See `docs/REAL-RUN-CHECKLIST.md` for the user-owned procedure.
- - The stub reranker is structurally non-discriminative (see ADR-006).

---

## ADR-002: Adapter protocols + a single factory for swappable components

**Status:** Accepted

**Context:**
Phase 2 had to wire embedding, reranking, generation, and judging in a way
that lets the same pipeline run against deterministic stubs in CI and against
real OpenAI/Anthropic clients on a `workflow_dispatch` job — without two
parallel codebases and without `if provider == "stub"` branches threading
through retrieval, generation, and eval. The eval harness has to read every
metric value out of the same call sites whether the backend is real or stub.

**Decision:**
Each swappable surface is a Python `Protocol` (`Embedder`, `Reranker`,
`LLMClient`, `LLMJudge`) in `packages/docintel-core/src/docintel_core/adapters/`
with at least one real adapter and one stub adapter implementing it. A single
factory `make_adapters(cfg)` (with siblings `make_retriever`, `make_generator`)
reads `Settings.llm_provider` and returns the appropriate bundle. Real
adapters live under `adapters/real/`; stubs live under `adapters/stub/`.
A CI grep gate (`scripts/check_adapter_wraps.sh`) asserts every LLM/embedder
call site is wrapped in `tenacity` retry with `before_sleep_log`.

**Consequences:**

- + Retrieval, generation, and eval code paths are byte-identical between
  stub and real — only the adapter bundle changes. The Phase 11 ablation
  harness re-uses this seam to swap `NullReranker`/`NullBM25Store` arms
  without forking `run_eval`.
- + The grep gate makes silent retries impossible: every `client.complete()`
  call has to be reachable from `_wrap_retry()` or CI fails.
- - Adding a 5th adapter family means writing a Protocol + 2 implementations
  + a factory hook + a grep-gate entry. This is a feature, not a bug.

---

## ADR-003: Pure-ASGI middleware (not BaseHTTPMiddleware) for trace_id propagation

**Status:** Accepted

**Context:**
Phase 12 needed to bind a `trace_id` contextvar so structlog's
`merge_contextvars` could attach it to every log line in a request — across
retrieval, generation, and the trace persistence layer. The obvious approach
in FastAPI / Starlette is `BaseHTTPMiddleware` because it has a clean
`async def dispatch(request, call_next)` signature.

That approach silently breaks. Starlette runs the endpoint handler in a
child `anyio` task, which gets a *copy* of the contextvar context at task
spawn — so `bind_contextvars(trace_id=...)` in the middleware does not
propagate into the handler, and the handler's logs come out without a
trace_id. The bug looks like "structlog stopped working" but is actually a
Starlette / contextvars composition issue.

**Decision:**
`TraceIdMiddleware` (in `packages/docintel-api/src/docintel_api/middleware.py`)
is a **pure-ASGI** middleware: it implements `async def __call__(scope,
receive, send)` directly, binds the contextvar before invoking the inner
app, and clears it in a `finally`. The inbound `X-Trace-Id` header is
UUID-validated before binding (V5 log-injection guard); invalid values are
replaced with a fresh `uuid4()`. The middleware also stores its live
`TraceSpanCollector` on `scope["state"]["trace_collector"]` so the
`POST /query` handler reuses the same collector and produces exactly one
`trace_completed` JSONL record per request.

**Consequences:**

- + `trace_id` propagates through every log line emitted during a request,
  including those inside the retriever and the generator — Phase 12 didn't
  have to retrofit `structlog.contextvars.bind_contextvars` calls into
  Phases 5 and 6.
- + No double-write: one request → one consolidated `trace_completed`
  record on disk. The Streamlit Traces tab renders that record as a single
  row with a per-stage waterfall.
- - Pure-ASGI middleware is lower-level than `BaseHTTPMiddleware` —
  inbound header lookup is a manual scan over `scope["headers"]`, and
  testing requires the pure-ASGI `TestClient` patterns rather than
  request/response mocks. The trade is correctness over ergonomics.

---

## ADR-004: BGE-small-en-v1.5 embedder + BGE-reranker-base cross-encoder

**Status:** Accepted

**Context:**
Phase 4 (embedding + indexing) and Phase 5 (hybrid retrieval) needed an
embedder small enough to run on a laptop and on the GitHub Actions runner,
deterministic enough that hashes match across reruns, and one of the
recognized strong open models so the eval numbers carry weight with senior
reviewers. The reranker had to be a cross-encoder (not a bi-encoder) for
the no-rerank-vs-baseline ablation to be a meaningful component swap.

**Decision:**
`BAAI/bge-small-en-v1.5` is the embedder (384-dim, ~133MB, sentence-transformers
loader). `BAAI/bge-reranker-base` (~280MB, AutoModelForSequenceClassification)
is the cross-encoder reranker. Both are downloaded once into the
HuggingFace cache, then loaded with `HF_HUB_OFFLINE=1` for CI determinism.
Dense vectors are stored in Qdrant (under the `real` compose profile) for
real runs and a NumPy `.npy` flat index for stub runs. BM25 uses `bm25s`.

**Consequences:**

- + Two of the strongest open-weight retrieval models at this size class —
  reviewer-recognizable choices that produce defensible Hit@K and MRR.
- + Stub-mode indices build in seconds on a fresh clone; real-mode indices
  build in ~7 minutes on the GitHub runner.
- - Reranker tokenizer has a 512-token sequence cap. This silent truncation
  is the most common subtle failure mode of cross-encoder rerankers; the
  Phase 5 RET-03 canary exists specifically to catch it (see ADR-006 for
  the empirical refutation of its sibling assumption about embedder/
  reranker tokenizer drift).

---

## ADR-005: Hybrid retrieval — BM25 + dense + Reciprocal Rank Fusion

**Status:** Accepted

**Context:**
Phase 5 had to choose a retrieval architecture. Pure-dense retrieval on
BGE-small leaves money on the table for lexical queries (ticker symbols,
exact phrases, numeric strings) — these are common in SEC 10-K questions
("R&D as % of revenue in FY2024 for TSLA"). Pure-BM25 misses semantic
matches and synonyms ("supply chain risk" vs "supplier concentration").
The hero question is a multi-hop comparative across companies, which
stresses both.

**Decision:**
Retrieval is hybrid: a BM25 search and a dense search run in parallel,
their top-K results are fused via **Reciprocal Rank Fusion** (`RRF` with
`k=60` per the standard recipe), then the fused top-N is reranked by the
cross-encoder. The Phase 11 ablation harness swaps `BM25Store` for a
null/no-op (the `dense-only` arm) and `Reranker` for a null/no-op (the
`no-rerank` arm) on the same byte-identical eval path — so the headline
ablation table shows Hit@5 / Hit@3 / MRR with paired bootstrap CIs on the
Δ-vs-baseline.

**Consequences:**

- + The Phase 11 ablation deltas are real component swaps, not parameter
  sweeps. Each arm is exactly one swap away from baseline, so causal
  attribution is honest.
- + The `dense-only` arm's empirical behavior in real mode is the project's
  load-bearing argument for why hybrid retrieval is worth the implementation
  cost.
- - RRF is a 1-line algorithm with no parameters worth tuning; the only knob
  is `k=60` which is the literature default. This is a feature.

---

## ADR-006: Stub reranker cannot beat stub dense-only — canary cases real-mode-only (Option D)

**Status:** Accepted (empirical finding)

**Context:**
Phase 5 RET-03 specifies a "reranker canary": on ≥5 hand-written hard cases,
the cross-encoder must measurably improve top-3 hit rate vs. dense-only.
The canary's purpose is to catch the cross-encoder's 512-token silent
truncation regression *before* it ships. The natural implementation is a
stub-mode test that runs the canary on the deterministic stub embedder +
stub reranker + the hand-written cases, and asserts `hits@3(rerank) >
hits@3(dense_only)`.

That test **structurally cannot pass** in stub mode. Both the stub embedder
and the stub reranker reduce to a deterministic hash of the input string;
the reranker's score is a monotone function of the same hash the dense
retriever uses to order candidates, so rerank produces zero rank changes
and `hits@3(rerank) == hits@3(dense_only)` by construction. The empirical
finding is recorded in `.planning/STATE.md` as one of the two flagged
Phase 13 ADRs.

**Decision:**
Option D from the Phase 5 D-14 decision: the reranker canary cases are
**real-mode-only**. Stub-mode CI does not run the canary assertion; the
real-mode `workflow_dispatch` job runs it as the structural acceptance
gate. The Phase 11 ablation `no-rerank` arm exists in both stub and real
mode (the arm's Δ is *measurable* in stub mode, just not load-bearing
about real-world rerank quality).

**Consequences:**

- + The canary stays load-bearing in real mode — its whole point is
  catching a real cross-encoder regression, and it does exactly that.
- + Stub-mode CI is honest: a passing stub canary would have been a lie.
  We surface the structural limitation rather than papering over it.
- - The real-mode canary depends on the user running `gh workflow run`
  with API keys configured — see `docs/REAL-RUN-CHECKLIST.md`.
- - The Phase 11 stub ablation's `no-rerank` Δ is a wiring assertion (does
  the arm-injection work end-to-end), not a quality claim. The ablation
  manifest carries `representative: false` to make this honest.

---

## ADR-007: BGE tokenizer-drift A1 — REFUTED, measured +14% chunk overflow

**Status:** Accepted (empirical refutation)

**Context:**
The Phase 3 chunker uses an XLM-RoBERTa tokenizer to count tokens against
the `TARGET_TOKENS=450` / `HARD_CAP_TOKENS=500` thresholds. The BGE
embedder uses its own tokenizer. Assumption A1 in the Phase 3/5 research
record was: "XLM-RoBERTa's token count is close enough to BGE's that the
500-token cap rarely overshoots BGE's 512-token sequence limit." A weak
overshoot was budgeted for; a large one would have meant the embedder
silently truncates the tail of long chunks and we'd be retrieving
incomplete vectors.

**Decision:**
The assumption was measured and **refuted**. The two tokenizers disagree
by a mean ratio of **1.1404** — a +14% systematic over-shoot. Of 6,053
chunks in the production corpus, **1,794 chunks (29.6%) exceed the
500-token threshold when re-counted with the BGE tokenizer**. This is
recorded in `.planning/STATE.md` as the second of two flagged Phase 13
ADRs, and the chunker now emits a `chunker_token_overflow_warning`
structlog event on every chunk where the BGE re-count exceeds the cap,
so downstream consumers can decide whether to re-chunk.

**Consequences:**

- + The token-overflow warning is now load-bearing observability — without
  it, BGE's silent tail-truncation on ~30% of chunks would degrade retrieval
  quality invisibly. The warning makes the truncation surface visible in
  every embed-build run.
- + The Phase 5 reranker canary (ADR-006) sits downstream of the same
  truncation surface, and the real-mode canary's pass/fail is the
  end-to-end test for whether the truncation actually hurts retrieval.
- - The chunker does NOT re-chunk on overflow — that would require a
  second pass with a different tokenizer and break Phase 3's deterministic
  pipeline. The decision is to surface the issue and let real-mode metrics
  decide whether re-chunking is worth its complexity.
- - This negative result is documented openly precisely because honest
  measurement of refuted assumptions is more useful to a reviewer than a
  vague "we considered this and chose to proceed."

---

## ADR-008: Single env reader via `Settings` (Pydantic-settings) — CI grep-gated

**Status:** Accepted

**Context:**
A 4-day portfolio project routinely accretes `os.environ.get("DOCINTEL_X",
"default")` calls scattered through retrieval, indexing, and UI modules
during development. Each one is a hidden dependency that breaks
configurability and makes the test harness's `monkeypatch.setenv` calls
order-sensitive. The pattern is so common it has a name (FND-11 in the
project's foundation requirements).

**Decision:**
**Every** environment variable read in the codebase flows through
`packages/docintel-core/src/docintel_core/config.py` (Pydantic v2 +
`pydantic-settings`, `env_prefix="DOCINTEL_"`). `Settings` is the single
env reader. A CI grep gate asserts `os.environ` / `os.getenv` matches
return zero in any file outside `config.py`. New configuration is added
as a new `Settings` field, not as a new env read.

**Consequences:**

- + Tests that need a specific config use `monkeypatch.setenv` + a fresh
  `Settings()` instance; nothing else has to be patched.
- + The compose file, the `.env.example`, and the CI env block are the
  authoritative list of every input the system reads.
- - Adding a new env var requires a `Settings` field with a default. This
  has been zero friction in practice.

---

## ADR-009: Prompts versioned with a content hash, locality CI-gated

**Status:** Accepted

**Context:**
A RAG system's prompts are part of its measurable behavior. If a prompt
changes between an eval run on Tuesday and an eval run on Wednesday, the
Hit@K and faithfulness deltas mean nothing — the system literally is a
different system. Reviewers reading `data/eval/reports/*/report.md` need to
know *which* prompts produced the numbers in front of them. And the
"prompts must live in one module" rule is dead unless it's mechanically
enforced — inline string-literal prompts crop up in stub adapters and tests
within days of the rule being written down.

**Decision:**
All prompts live in
`packages/docintel-generate/src/docintel_generate/prompts.py` as three
`Final[str]` constants: `SYNTHESIS_PROMPT`, `REFUSAL_PROMPT`, `JUDGE_PROMPT`.
Each prompt has a `sha256[:12]` hash (`_SYNTHESIS_HASH`, etc.) and a
combined `PROMPT_VERSION_HASH` that the eval manifest header records on
every run. A CI grep gate (`scripts/check_prompt_locality.sh`) asserts no
inline prompt-shaped string literals exist outside `prompts.py` (a
`# noqa: prompt-locality` escape exists for the stub adapter's
sentinel constants).

**Consequences:**

- + Every eval report names the exact prompt set that produced its numbers.
  A reviewer can read `PROMPT_VERSION_HASH = 65da07f1ba3e` in the manifest
  and check it out of git.
- + The grep gate makes prompt drift mechanically impossible. Phase 7
  D-04's confidence-marker edit rotated `_SYNTHESIS_HASH` and
  `PROMPT_VERSION_HASH` — both changes are visible in the next eval
  manifest, with no developer effort.
- - Tests that need a custom prompt must construct one inline and pass it
  to the LLM client directly, bypassing the prompts module. This is rare
  (3 occurrences) and the bypass is explicit.

---

## ADR-010: Wilson CIs on rates, paired bootstrap CIs on ablation deltas

**Status:** Accepted

**Context:**
The eval harness reports rates (Hit@K, MRR, faithfulness pass rate, refusal
matrix) and the ablation harness reports deltas-vs-baseline on those rates.
Naive point estimates on n=32 questions are dishonest — reviewers and
engineers both know the per-rate confidence is ±0.10 at that sample size,
and a delta of 0.05 might or might not be real. The ablation harness has to
distinguish "the cross-encoder improved Hit@5 by 0.06" from "we got lucky
on 2 questions."

**Decision:**
Every rate in `results.json` carries a 95% **Wilson CI** computed via
`scipy.stats.binomtest(k, n).proportion_ci(method='wilson')`. Every ablation
delta in `ablation-manifest.json` carries a 95% **paired bootstrap CI**
computed by `bootstrap_delta_ci(seed=42, n_boot=10_000)`. The bootstrap is
paired (per-question pairing) because each arm runs against the same 32
questions; pairing is what makes the CI tight enough to be informative at
n=32. The seed is fixed so CIs are deterministic across reruns.

**Consequences:**

- + Both UIs (the Streamlit Eval-Results tab and the rendered `report.md`)
  show CIs alongside every point estimate; readers don't have to ask
  "is that significant?"
- + The paired bootstrap is the right statistic at portfolio sample size
  (n=32); a non-paired bootstrap would inflate the CIs and hide real
  effects.
- - n=32 is small. The CIs are wide enough that some ablation deltas are
  inconclusive even in real mode. The honest move is to report this rather
  than to swap to a less rigorous statistic.

---

## ADR-011: Eval-in-CI is always stub-mode; real-mode is `workflow_dispatch`

**Status:** Accepted

**Context:**
Two competing pressures. (1) CI on every PR must run the full eval suite —
that's the project's quality gate, and the only way to catch regressions
that don't show up in unit tests. (2) Real-mode runs cost real Anthropic
and OpenAI API calls; running the full 32-question suite on every PR would
burn dozens of dollars a week and would block third-party PRs (no keys on
untrusted PRs is a Phase 10 threat-model item, T-10-CI1).

**Decision:**
The `lint-and-test` job runs the full eval suite in stub mode on every PR.
It generates + validates the report but **does not commit** it (no per-PR
git bloat). Real-mode runs are `workflow_dispatch`-only via two named
jobs: `real-eval` (full 32-Q eval) and `real-ablation` (full ablation
sweep including the chunk-size sweep arms). Both commit their reports
under `data/eval/reports/<ts>/` and `data/eval/ablations/<ts>/` with
`[skip ci]` to avoid trigger loops. One canonical `stub-sample/` report
+ ablation is committed to give the UI's Eval-Results tab data to render
on a fresh clone.

**Consequences:**

- + Every PR runs the full pipeline against the deterministic stub bundle —
  ranking determinism, refusal logic, citation parsing, faithfulness shape,
  cost wiring — without burning a cent.
- + Real-mode reports are owned by the user: a `gh workflow run ci.yml`
  trigger produces a real `data/eval/reports/<ts>/report.md` committed
  to the branch, and the Eval-Results tab auto-detects it on next render.
- - The published headline numbers in the README depend on the user
  running the workflow. Phase 13 D-14 is the explicit decision to NOT
  block on this — the README ships a labeled `representative: false`
  stub block + a documented paste step (see `docs/REAL-RUN-CHECKLIST.md`).

---

## ADR-012: One-command demo via stub-index built at container startup

**Status:** Accepted

**Context:**
The project spec's "Definition of Done" includes a non-negotiable one-command
demo: `git clone && docker-compose up` produces a working demo on a fresh
machine. The complication is that `data/indices/` is gitignored — indices
are 100s of MB of binary blobs that would balloon the repo. A fresh clone
has no MANIFEST, no BM25 store, no dense vectors. Every prior portfolio
project I've seen handles this by either committing indices (bloats the
repo) or pre-building them in CI (breaks the one-command promise).

**Decision:**
The `api` container's entrypoint (`docker/entrypoint-api.sh`, POSIX sh,
`set -e`) runs `docintel-index build` in stub/NumPy mode at container
startup if `${DOCINTEL_DATA_DIR}/indices/MANIFEST.json` is absent (the build
is idempotent — IDX-03 — so subsequent boots skip the rebuild in
milliseconds). Once the index is built, the entrypoint `exec`s uvicorn so
the Python process is PID 1 and Docker's SIGTERM reaches it directly. A
committed `data/eval/traces-seed.jsonl` (3 hand-authored `trace_completed`
records, one with `refused=true`) is copied into the trace directory if
empty, so the Streamlit Traces tab renders something before the first
query is issued. The healthcheck `start_period` is 30s — enough to cover
first-boot Python cold-start + index build.

**Consequences:**

- + `git clone && docker-compose up` works on any machine with Docker, zero
  API keys, no pre-build step. The promise is structurally kept.
- + The first-boot cost (a few seconds) is paid once per fresh volume; the
  idempotent MANIFEST check skips on subsequent boots.
- + The trace seed means the Traces tab demonstrates per-stage timing bars
  before the user runs any query — important for the recordable demo and
  for the recruiter who scans the UI in 30 seconds.
- - If `docintel-index build` ever fails at runtime (e.g. corrupt chunks
  file), the container exits unhealthy with a clear error rather than
  serving 500s. `set -e` makes this explicit.

---

## ADR-013: Eval-set mutation policy (Phase 14 D-03)

**Status:** Accepted

**Context:**
The v1.0 retro's #1 unwritten lesson — "stub geometry must mirror real-mode
geometry for canaries to be meaningful" — has an eval-set analog: paired-
bootstrap deltas mean nothing if the underlying questions or golds drift
mid-experiment. Phase 14 froze the ground-truth eval set at
`data/eval/ground_truth/eval_set.jsonl` (renamed from `questions.jsonl` per
D-01) and pinned its byte-identity via a 64-char hex SHA256 constant in
`tests/test_eval_set_frozen.py::EVAL_SET_SHA256`. Any future change to the
eval set — adding a question, fixing a typo'd gold ID, rewriting a refusal
prompt — silently invalidates every committed report and every
Phase 17 paired-bootstrap delta unless the change is paired with a
re-baseline cycle. Without a written protocol the natural pattern would be
"edit the JSONL, bump the SHA256 constant, push" — which is exactly the
silent-invalidation failure mode this ADR exists to prevent.

**Decision:**
Any mutation of `data/eval/ground_truth/eval_set.jsonl` after the Phase 14
freeze MUST execute all four steps below, in order, in the same PR:

1. **Write a new ADR in `DECISIONS.md`** documenting the change, the
   reviewer-visible reason it could not wait for v2.0, and the previous
   baseline being superseded (the "supersedes baseline `<ts>`" field).
2. **Update `EVAL_SET_SHA256`** in `tests/test_eval_set_frozen.py` to the
   fresh `sha256(open(eval_set.jsonl,"rb").read()).hexdigest()` of the
   mutated file. The xfail-strict marker is permanently removed (Plan
   14-02); the only path back to green is a matching constant.
3. **Re-run real-eval** via `gh workflow run real-eval` to produce a
   fresh `representative: true` report under `data/eval/reports/<ts>/`.
   The report's `manifest.dataset_hash` MUST match the new
   `EVAL_SET_SHA256` (the existing validate gate at `validate.py:248-259`
   asserts this on every committed report dir).
4. **Update `data/eval/baseline.json`** per D-07 to point at the new
   report dir + its `eval_set_sha256`. Phase 17 plans MUST validate
   against the baseline they declare (the schema mismatch surfaces as
   `"baseline invalidated; re-baseline per ADR-013"` at delta-compute
   time, not as a silently misrouted comparison against a stale baseline).

**Consequences:**

- + Paired-bootstrap deltas remain interpretable across phases. A Phase 17
  delta against the locked v1.0 baseline is structurally guaranteed to
  compare like-against-like; mutations require an explicit re-baseline that
  every downstream consumer sees in the git history.
- + CI catches accidental mutations loudly. A one-character typo in
  `eval_set.jsonl` flips `test_eval_set_sha256_matches_frozen_constant`
  from green to red with a stderr pointer at this ADR; the developer cannot
  bypass it by editing the constant without also touching DECISIONS.md and
  re-running real-eval (the validate gate fails on `dataset_hash` mismatch
  if they try).
- + The `data/eval/baseline.json` pointer mechanism (D-07) makes the
  cross-check declarative: Phase 17 reads the baseline's
  `eval_set_sha256` and asserts the current file matches it before
  computing any delta. The mismatch error message names this ADR.
- - Any legitimate eval-set fix — e.g. a typo'd gold chunk_id that
  resolves to the wrong company, or a refusal flavor that drifted out of
  the controlled vocabulary — requires the full 4-step cycle, not a
  one-line patch. The cost is real: a real-eval run costs API budget and
  ~15 min of wall-clock.
- - Phase 17 mid-development runs that touch the eval set (e.g. expanding
  the multi-hop set to stress the new chunker) must explicitly land a
  baseline-supersession ADR before merging. The ADR-014/015 slots are not
  reserved for this — every supersession allocates its own number from
  whatever the running count is at PR time.

---

## ADR-014: OpenAI-compatible endpoint override + distinct-model cross-family judge (Phase 14 D-14)

**Status:** Accepted

**Context:**
ADR-002 made every LLM swappable behind a protocol + factory, and ADR-004
locked BGE for embedding/reranking. But the OpenAI generation path (Phase 6)
was written against `api.openai.com` and the model `gpt-4o` specifically: the
SDK client was constructed with no `base_url`, the model id was a module
constant in both `llm_openai.py` and `judge.py`, and the pricing table keyed
only `gpt-4o`/`gpt-4.1`. The v1.0 real-eval therefore *required* two metered
provider accounts (Anthropic + OpenAI) because ADR's cross-family judge (D-04)
forces the judge onto the complement *provider* to avoid a model
rubber-stamping its own output.

For the Phase 14 empirical-closure run the operator's available inference is an
**NVIDIA NIM hosted endpoint** (`https://integrate.api.nvidia.com/v1`, an
OpenAI-compatible chat-completions gateway) serving the open-weight
`openai/gpt-oss-120b`. A single gateway, OpenAI-SDK-shaped, free dev-credit
tier. Two facts collide with the v1.0 assumptions: (1) the OpenAI adapter
cannot reach a non-OpenAI base URL or run a non-`gpt-4o` model, and (2) the
cross-family judge's *cross-PROVIDER* mechanism has no second provider to point
at — both generator and judge would be "the OpenAI adapter."

**Decision:**
Add three `Settings` knobs (the only env reader, ADR-008): `openai_base_url`
(→ `openai.OpenAI(base_url=...)`, None = SDK default), `openai_model`
(generator id, default `gpt-4o` so v1.0 behaviour is unchanged), and
`judge_model`. When `llm_real_provider='openai'` **and** `judge_model` is set,
the factory builds the judge as a **second `OpenAIAdapter` pinned to
`judge_model`** rather than the Anthropic complement. The anti-rubber-stamp
guarantee shifts from *distinct provider* to **distinct model**: generator
`openai/gpt-oss-120b` is judged by `meta/llama-3.3-70b-instruct` — different
weights, different family, no self-judging — both via the one NIM endpoint. The
`nvapi-...` key reuses `openai_api_key`. When `judge_model` is None the v1.0
cross-PROVIDER path (Anthropic judges OpenAI) is preserved untouched.

NIM models are registered in `pricing.py` at `(0.00, 0.00)` because
build.nvidia.com hosted inference is a free dev-credit tier — the eval's
`$/query` then reflects token volume at zero marginal cost, and the
manifest/README must say so explicitly so the number is not mistaken for
metered OpenAI pricing. The `(0,0)` rows exist to clear the ADR-006/D-06
KeyError gate (an unregistered generator model crashes the eval mid-run), not
to assert a real price.

**Pre-run gate (load-bearing):** the judge sends
`response_format={"type":"json_schema","strict":true}`. If the judge model on
NIM does not honor strict JSON-schema, *every* verdict silently degrades to the
sentinel `score=0` (Pitfall 6) and faithfulness is garbage-but-green. A live
one-shot structured-output probe against `judge_model` MUST pass before any
full real-eval run is trusted; `scripts/nim_probe.py` is that probe.

**Consequences:**

- + The real-eval can run on free open-weight inference, and the headline
  artifact becomes a *stronger* demonstration of the ADR-002 swappable-seam
  thesis: a 120B open model behind the identical `LLMClient` protocol, judged
  cross-family, with zero code paths special-cased for it.
- + Fully backward compatible. `judge_model=None` + default `openai_model`
  reproduce the v1.0 Anthropic↔OpenAI cross-provider eval byte-for-byte; the
  Phase 6 tests and the D-04 contract test are unchanged.
- − The faithfulness number now rests on *cross-model* rather than
  *cross-provider* independence. Two models served by the same vendor on the
  same stack are less independent than two separate providers; the eval report
  and README must disclose the judge model and this weaker independence claim.
- − `$/query` is $0 and therefore not comparable to a metered-API cost story.
  The manifest carries a `cost_basis: "nvidia-nim-free-tier"`-style note so a
  reviewer does not read it as "gpt-oss-120b costs nothing on OpenAI."
- − A new silent-failure surface: a NIM model that ignores strict json_schema
  produces all-sentinel verdicts. Mitigated by the mandatory pre-run probe, but
  the eval report's `judge_structured_output_invalid` rate must still be
  eyeballed per run (it already is, per Pitfall 5/6 wiring).

**Coupled fix — the `representative` flag (runner.py / metrics.py):**
The manifest's `representative` flag was computed as `any(cost_usd > 0.0)` — a
proxy for "real models ran, not stubs." That proxy breaks for a free-tier real
endpoint: NIM at $0/token yields `cost_usd == 0` for every question, so the
report would be `representative: false` and `make baseline-lock` (which hard-
rejects `representative != true`, Makefile:187) would throw away an otherwise-
valid real run. The flag is now derived from the authoritative signal —
`provider != "stub"` (`runner.py` for the manifest; `compute_latency_stats`
gains an explicit `representative` arg) — matching what `ablate.py:458` already
did. This only flips the free-tier-real case to its correct value; stub
(`is_stub → false`) and paid-real (`cost>0 → true`) paths are unchanged. The
legacy cost>0 heuristic is retained as the default when no flag is passed, so
existing callers and tests are unaffected.

---

## ADR-015: Corpus re-baseline for 10-Q provenance fields (Story 1.1, AD-13)

**Status:** Accepted

**Context:**
Story 1.1 (extend ingestion to 10-Q) adds `filing_type` and `fiscal_period`
provenance to the `Chunk` and `NormalizedFiling` schemas (FR-A6). Both models
serialize every declared field — the committed corpus at
`data/corpus/chunks/**/*.jsonl` and `data/corpus/normalized/**/*.json` is
produced by `model_dump_json()` / `json.dumps(model_dump(), sort_keys=True)`,
so adding two serialized fields necessarily changes every committed 10-K file
and every per-filing sha256 in `MANIFEST.json`. There is no field-exclusion
trick that also satisfies AC-1 ("every chunk carries filing type"). The
byte-identity gate `tests/test_chunk_idempotency.py` and the golden-fixture
gate `tests/test_normalize.py::test_normalize_golden_matches` therefore went
red the moment the fields landed — the sanctioned signal that a re-baseline
is required (AC-4). Per ARCHITECTURE-SPINE AD-13, a corpus re-baseline is a
deliberate, ADR-gated event, never a silent regeneration.

**Decision:**
Re-baseline the committed 10-K corpus as a mechanical `+2 keys` migration,
gated by a reproducibility proof:

1. **Safety gate (proven before touching committed data):** re-running
   `normalize_html` + `chunk_filing` over all 45 committed filings reproduces
   them byte-for-byte *except* `{filing_type, fiscal_period}` (and the
   never-hashed `fetched_at`). 45/45 normalized and 45/45 chunk files
   reproduced; zero non-key diffs. This proves the migration changes nothing
   but the two new keys.
2. **Normalized:** inject `filing_type="10-K"` / `fiscal_period="FY"` into each
   committed normalized JSON via the same `json.dumps(…, indent=2,
   sort_keys=True)` writer — preserves `fetched_at`, inserts the two keys
   alphabetically, byte-identical otherwise.
3. **Chunks:** re-chunk each updated normalized JSON with the current chunker
   and overwrite the committed JSONL via the exact `chunk_all` writer
   (`"\n".join(model_dump_json()) + "\n"`; empty filings stay zero-byte). 6053
   chunks over 45 files. 10-K `chunk_id`s are unchanged (the Q-keyed segment is
   non-10-K only; `fiscal_period="FY"` keeps the bare `FY{year}` token).
4. **Manifest:** bump `MANIFEST_VERSION` 1 → 2 (adds per-filing `filing_type` /
   `fiscal_period`) and regenerate `MANIFEST.json` so every sha256 matches the
   new bytes.
5. **Golden fixtures:** same injection + re-chunk for `tests/fixtures/sample_10k/`.

No API budget or network is required — the 10-K re-baseline is fully offline
(re-normalize committed raw HTML + re-chunk). The distinct 10-Q *addition*
(new filings) is a separate, live-fetch-dependent step (Story 1.1 fetch
dispatch + Story 1.6 for 8-K).

**Consequences:**

- + The byte-identity and golden gates are green again; the full offline suite
  is 298 passed / 0 failed (1 hero-gif xfail). 10-K chunk text, ordering, and
  `chunk_id`s are unchanged — only two provenance keys were added.
- + The reproducibility gate makes the migration auditable: it is provably a
  `+2 keys` change, not an opaque regeneration that could mask a normalizer or
  chunker drift.
- + `MANIFEST.json` v2 now carries form/period provenance, so downstream
  consumers (index manifest, eval-report provenance) can filter by form
  without re-parsing every normalized JSON.
- − The git diff touches all 45 normalized + 45 chunk files + MANIFEST — a
  large but mechanical change reviewers verify via the reproducibility script
  (`+2 keys` only), not by reading every line.
- − Any future schema field on `Chunk` / `NormalizedFiling` incurs the same
  re-baseline cycle. This is the intended cost of committing the corpus as a
  byte-identity-gated artifact.

---

*Last updated: 2026-07-13, Story 1.1 (ADR-015 10-Q re-baseline).*
