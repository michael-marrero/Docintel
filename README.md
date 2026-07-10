# docintel

**Production-shaped RAG over SEC 10-Ks. The eval harness — not the chat UI — is
the headline artifact.** Hit@K, MRR, faithfulness, citation accuracy, latency,
and $/query are reported on a held-out 32-question reference set with **Wilson
CIs** on rates and **paired bootstrap CIs** on ablation deltas. Every PR
re-runs the full eval suite in stub mode in CI. Real-mode is one
`gh workflow run` away — no API keys at build time, no hidden dependencies.

![hero demo — multi-hop comparative answer + out-of-corpus refusal](docs/hero.gif)

> _The hero GIF above is recorded manually from the running demo._
> _See [`docs/HERO-STORYBOARD.md`](docs/HERO-STORYBOARD.md) for the_
> _shot-by-shot recording script. Until the GIF lands, the storyboard_
> _is the demo._

## Quickstart (one command, zero keys)

```bash
git clone https://github.com/<you>/docintel.git
cd docintel
docker-compose up
# open http://localhost:8501  (Streamlit UI)
# open http://localhost:8000/health  (FastAPI)
```

That's the demo. The `api` container's entrypoint self-bootstraps a stub/NumPy
index on first boot (`data/indices/` is gitignored), seeds a small set of
trace records so the Traces tab renders before any query is issued, then
`exec`s uvicorn. The `ui` container waits for the api healthcheck and serves
three tabs: **Query**, **Traces**, **Eval-Results**.

On first paint the Query tab is pre-filled with the locked hero question (a
multi-hop comparative across the corpus); click **Submit** and you get a
synthesized answer with inline hoverable `[N]` citation badges (hover
surfaces the chunk excerpt + company + section), a confidence pill, and a
per-query cost/latency meter. Clear the box, paste an out-of-corpus question,
and the same UI renders an amber refusal card.

## Eval Results

<!-- PASTE-REAL-NUMBERS: real numbers from baseline.json @ 2026-07-10T22:23:58Z (git_sha=8278e8a9ebff) -->
> **`representative: true` — real-mode measurements**
> from the v1.0 baseline run committed at 2026-07-10T21:39:26Z
> (`data/eval/reports/20260710_213926_942457Z/`, locked via `make baseline-lock`).

**Headline metrics (real-mode, n=32):**

| Metric                | Value | 95% Wilson CI    |
| --------------------- | ----- | ---------------- |
| Hit@5                 | 0.556 | [0.373, 0.724]   |
| Hit@3                 | 0.481 | [0.307, 0.660]   |
| MRR                   | 0.474 | —                |
| Faithfulness (pass)   | 0.893 | [0.728, 0.963]   |
| Latency p50           | 21167.4 ms   | — |
| Latency p95           | 58615.0 ms   | — |
| $/query               | $0.000000 | — |

<!-- END-PASTE-REAL-NUMBERS -->

> **Baseline, not launch-ready.** These are the v1.0 **baseline** measurements on
> free-tier NIM models (generator `llama-3.3-nemotron-super-49b`, judge `glm-5.2`) —
> committed as the fixed reference point to optimize against with stronger models or
> fine-tuning. They sit **below the PRD launch gates** (citation accuracy ≥ 0.90,
> faithfulness ≥ 0.95, Hit@5 ≥ 0.85), which remain the bar for PRD-readiness and are
> **not** relaxed to match the baseline. The artifact here is the eval harness and
> its honest numbers, not a launch claim.

---

## What's underneath

### Architecture

`docintel` is a `uv` workspace with one package per architectural seam — each
package is independently testable, independently mypy-strict, and gets its
own slot in the adapter factory:

| Package              | Role                                                                |
| -------------------- | ------------------------------------------------------------------- |
| `docintel-core`      | `Settings` (the single env reader), `Answer`/`Citation`/`GenerationResult` types, structlog config, the `TraceSpanCollector` + `load_traces` observability primitives, and the adapter protocols (`Embedder`, `Reranker`, `LLMClient`, `LLMJudge`) + `make_*(cfg)` factories. |
| `docintel-ingest`    | SEC 10-K fetch + parse + chunk pipeline. Emits `chunker_token_overflow_warning` on chunks that exceed the BGE 512-token cap (see [ADR-007](DECISIONS.md)). |
| `docintel-index`     | BM25 (`bm25s`) + dense (Qdrant in real mode, NumPy `.npy` in stub) index builders. CLI: `docintel-index build/verify/all`. Idempotent — MANIFEST.json gates rebuilds. |
| `docintel-retrieve`  | Hybrid retrieval: BM25 + dense in parallel → RRF fusion → cross-encoder rerank → top-K. |
| `docintel-generate`  | `Generator` class wrapping the retrieval-context-LLM-citation-telemetry pipeline. **All prompts live in this package** (`prompts.py`) with `sha256[:12]` hashes; a CI grep gate enforces locality. |
| `docintel-eval`      | Metrics (`hit_at_k`, `mrr`, faithfulness, citation accuracy, latency, refusal matrix) with Wilson + paired-bootstrap CIs. CLI: `docintel-eval run/validate/ablate`. |
| `docintel-api`       | FastAPI app. `POST /query`, `GET /traces`, `GET /trace/{id}`, `/health`. Pure-ASGI `TraceIdMiddleware` binds `X-Trace-Id` (see [ADR-003](DECISIONS.md)). |
| `docintel-ui`        | Streamlit UI with three tabs (`Query` / `Traces` / `Eval-Results`). UI is a thin HTTP client of the API — even the trace fetch goes over `GET /traces`, not via the filesystem. |

The factory pattern (`make_generator(cfg)`, `make_retriever(cfg)`,
`make_adapters(cfg)`) reads `Settings.llm_provider` and assembles a real or
stub bundle. Retrieval, generation, and eval call sites are byte-identical
across the two modes — only the adapter bundle changes. The Phase 11 ablation
harness re-uses this seam to swap `NullReranker` / `NullBM25Store` arms onto
the same `run_eval` path with no `if mode ==` branches in the hot loop.
See [ADR-002](DECISIONS.md) and [ADR-005](DECISIONS.md).

### Offline-first stub default

`DOCINTEL_LLM_PROVIDER=stub` is the default in `.env.example`,
`docker-compose.yml`, and every CI job (see [ADR-001](DECISIONS.md)). Every
swappable surface has a deterministic stub adapter, so:

- `git clone && docker-compose up` works without API keys.
- Every PR runs the full pipeline + the full eval suite in CI with no API
  cost.
- Stub reports are labeled `representative: false` in every manifest, the
  UI's Eval-Results tab carries a prominent banner, and the README's eval
  block above is delimited by `PASTE-REAL-NUMBERS` markers so it's obvious
  what gets replaced after a real-mode run.

The trade is documented honestly: the stub reranker structurally cannot
demonstrate cross-encoder quality (the canary is real-mode-only — see
[ADR-006](DECISIONS.md)).

### Eval methodology

- **Headline metrics:** Hit@K, MRR, faithfulness pass-rate (over non-refused
  answers), citation accuracy, refusal matrix, latency (p50/p95), $/query.
- **Wilson 95% CIs** on every rate, via
  `scipy.stats.binomtest(k,n).proportion_ci(method='wilson')`.
- **Paired bootstrap 95% CIs** on every ablation delta, via
  `bootstrap_delta_ci(seed=42, n_boot=10_000)`. Pairing is per-question;
  pairing is what makes the CI tight enough to be informative at n=32.
- **`representative: false` banner** wherever stub numbers appear (eval
  manifest, ablation manifest, the UI Eval-Results tab, the README block
  above).
- **Eval-in-CI:** the `lint-and-test` job runs `docintel-eval run` +
  `docintel-eval validate` on every PR in stub mode (no commit). Real-mode
  runs are the `real-eval` and `real-ablation` jobs in
  [`.github/workflows/ci.yml`](.github/workflows/ci.yml), gated on
  `workflow_dispatch`. See [ADR-011](DECISIONS.md).

### Observability

- `TraceIdMiddleware` is **pure-ASGI** (not `BaseHTTPMiddleware` — that
  silently breaks contextvars in Starlette child tasks; see
  [ADR-003](DECISIONS.md)).
- One `trace_completed` JSONL record per request, written via a
  `TraceSpanCollector` threaded through the middleware onto the request
  scope so the handler reuses the same collector — exactly one record per
  request, no double-writes.
- The Streamlit Traces tab fetches over `GET /traces` (never reads the
  trace directory directly) and renders a per-stage Altair Gantt-waterfall
  on row select.
- A CI grep gate (`scripts/check_no_print.sh`) asserts zero `print(` calls
  in `packages/*/src` — all output is structured structlog JSON.

### Architectural decisions

12 ADRs (Context / Decision / Consequences template) covering offline-first
defaults, the adapter factory pattern, the pure-ASGI middleware choice, the
hybrid retrieval design, the two empirical findings that shaped Phase 13
(the Option D reranker-canary decision and the +14% tokenizer-drift
refutation), the prompts-versioning + locality gate, the Wilson + paired
bootstrap statistics, and the one-command demo design — all in
[`DECISIONS.md`](DECISIONS.md).

---

## Running the demo

### One-command demo (default — stub mode)

```bash
docker-compose up        # builds api + ui images, brings up the stack
# - API:    http://localhost:8000  (FastAPI)
# - UI:     http://localhost:8501  (Streamlit)
# - Health: curl http://localhost:8000/health
docker-compose down -v   # teardown
```

### Local development (Python only)

```bash
# Install uv if you don't have it: https://docs.astral.sh/uv/
uv sync --all-packages

# Build the stub index on disk:
.venv/bin/docintel-index build

# Run the eval suite (stub mode):
.venv/bin/docintel-eval run
.venv/bin/docintel-eval validate data/eval/reports/<timestamp>

# Run the ablation suite (stub mode component arms):
.venv/bin/docintel-eval ablate

# Run the full stub test suite:
HF_HUB_OFFLINE=1 DOCINTEL_LLM_PROVIDER=stub .venv/bin/pytest -ra -q -m "not real"
```

### Real-mode runs

Real-mode runs require API keys and a `gh workflow run` trigger. The user
owns this step — see [`docs/REAL-RUN-CHECKLIST.md`](docs/REAL-RUN-CHECKLIST.md)
for the prerequisites (Phases 6–12 are local-only/unmerged), the exact
`gh workflow run` commands for `real-eval` and `real-ablation`, and the
README paste step (replace the `PASTE-REAL-NUMBERS` block above with the
contents of the committed real `results.json`).

---

## Repository layout

```
.
├── docker-compose.yml      # one-command demo (api + ui; qdrant under profile: real)
├── docker/                 # Dockerfile + api entrypoint
│   ├── Dockerfile
│   └── entrypoint-api.sh   # idempotent stub-index build + trace seed + exec uvicorn
├── packages/               # uv workspace — one package per architectural seam
│   ├── docintel-core/      # Settings, types, adapters, factories, trace primitives
│   ├── docintel-ingest/    # SEC 10-K fetch + chunk
│   ├── docintel-index/     # BM25 + dense index builders
│   ├── docintel-retrieve/  # hybrid BM25 + dense + RRF + rerank
│   ├── docintel-generate/  # Generator + prompts.py (single home for all prompts)
│   ├── docintel-eval/      # metrics + run/validate/ablate CLIs
│   ├── docintel-api/       # FastAPI (POST /query, GET /traces, /health)
│   └── docintel-ui/        # Streamlit (Query / Traces / Eval-Results tabs)
├── data/                   # data tree
│   ├── corpus/             # SEC 10-Ks (gitignored — `make fetch-corpus`)
│   ├── indices/            # built indices (gitignored)
│   ├── traces/             # runtime traces (gitignored)
│   └── eval/
│       ├── ground_truth/   # 32-question eval set (tracked)
│       ├── reports/        # eval reports (stub-sample tracked; real timestamps tracked)
│       ├── ablations/      # ablation reports (same)
│       └── traces-seed.jsonl  # 3 seed records the entrypoint copies on first boot
├── tests/                  # full stub test suite — 247+ tests, all green offline
├── DECISIONS.md            # 12 ADRs (Context / Decision / Consequences)
├── docs/
│   ├── HERO-STORYBOARD.md  # shot-by-shot hero GIF recording script
│   └── REAL-RUN-CHECKLIST.md  # user-owned real-key workflow procedure
└── README.md               # this file
```

## Constraints (the ones that shaped the design)

- **Offline-first.** No API keys at build time. Stubs are deterministic and
  cover the entire pipeline including eval. (ADR-001)
- **Single env reader.** All env vars flow through `Settings`. CI greps for
  `os.environ`/`os.getenv` outside `config.py` must return zero. (ADR-008)
- **No silent retries on LLM calls.** Every LLM/embedding call is wrapped in
  `tenacity` retry with `before_sleep_log`; a CI grep gate enforces this.
- **Prompts in one module, versioned.** All prompts in
  `packages/docintel-generate/src/docintel_generate/prompts.py` with
  `sha256[:12]` hashes; `scripts/check_prompt_locality.sh` is a CI gate.
  (ADR-009)
- **No `print(` statements.** All output is structured structlog JSON.
  `scripts/check_no_print.sh` is a CI gate. (Phase 12 OBS-03)
- **One phase = one branch.** `git checkout -b phase/<N>-<name>`. Tests
  before code where possible.
- **Eval-in-CI.** Full stub eval on every PR; real-mode is
  `workflow_dispatch`. (ADR-011)
- **README rewritten last, from measurements.** This file shipped with a
  labeled `representative: false` block + a paste step rather than fake
  numbers. (Phase 13 D-14)

## License

(Add your license here.)

---

_Generated for Phase 13 — api-ui-polish. See [`DECISIONS.md`](DECISIONS.md)_
_for the 12 ADRs that frame every design choice above._
