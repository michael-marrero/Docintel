# Phase 6: generation - Research

**Researched:** 2026-05-15
**Domain:** RAG synthesis with cited generation + cross-family LLM judging + prompt versioning
**Confidence:** HIGH (every factual claim verified against pinned SDK CHANGELOGs, official docs, or repo source)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 — New 8th workspace package `docintel-generate`** at `packages/docintel-generate/`. Layout: `pyproject.toml`, `src/docintel_generate/__init__.py` (re-exports `Generator`, `GenerationResult`, the three `*_PROMPT` constants, `PROMPT_VERSION_HASH`), `prompts.py`, `generator.py`, `parse.py`, `py.typed`. Workspace pyproject's `packages/*` glob picks it up automatically; `uv.lock` regenerated.

**D-02 — Docs reconciliation.** Phase 6 plan updates `CLAUDE.md`, `.planning/config.json` (`prompt_home`), `.planning/REQUIREMENTS.md` (GEN-01 path), `.planning/ROADMAP.md` (Phase 6 `Provides:`), and `.planning/PROJECT.md` (Constraints "Prompts are versioned") to reference `packages/docintel-generate/src/docintel_generate/prompts.py`. Original spec path `src/docintel/generation/prompts.py` was a reconstruction artifact that never existed in this repo.

**D-03 — `make_generator(cfg) -> Generator` factory in `docintel_core.adapters.factory`** — 4th sibling factory alongside `make_adapters(cfg)`, `make_index_stores(cfg)`, `make_retriever(cfg)`. Internally calls `make_adapters(cfg)` + `make_retriever(cfg)`, constructs `Generator(bundle=adapters, retriever=retriever)`. Lazy import `from docintel_generate.generator import Generator` lives inside function body.

**D-04 — `scripts/check_prompt_locality.sh`** — CI grep gate mirroring `check_adapter_wraps.sh` / `check_index_wraps.sh` / `check_ingest_wraps.sh`. Pattern set (planner finalises): triple-quoted module-level string literals matching `\b(You are|Based on the|<context>|<chunks>|cite|grounded|chunk_id)\b` AND > 80 chars; identifier names matching `_*PROMPT*` / `_*INSTRUCTION*` / `_*SYSTEM*` outside allowlisted paths.

**D-05 — Exclusion policy = path allowlist + per-line `# noqa: prompt-locality` escape.** Default-excluded: `packages/docintel-generate/src/docintel_generate/prompts.py`, `parse.py`, `tests/**`, `**/conftest.py`, `**/test_*.py`, `packages/docintel-core/src/docintel_core/adapters/stub/llm.py`. **Phase 6 D-12 updates `_STUB_REFUSAL` to the new canonical refusal sentinel.** Per-line escape: appending `# noqa: prompt-locality` silences a line.

**D-06 — CI wiring** — `.github/workflows/ci.yml` gains one new step: `- name: Check prompt locality (GEN-01); run: bash scripts/check_prompt_locality.sh`. Stub-mode default. Exit 1 fails build with file + line + matched pattern.

**D-07 — Three named module-level prompts in `prompts.py`**: `SYNTHESIS_PROMPT: Final[str]`, `REFUSAL_PROMPT: Final[str]`, `JUDGE_PROMPT: Final[str]`.

**D-08 — Per-prompt + combined `PROMPT_VERSION_HASH`**, computed at module import time via `hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]`. `_SYNTHESIS_HASH`, `_REFUSAL_HASH`, `_JUDGE_HASH`, then `PROMPT_VERSION_HASH = _h(_SYNTHESIS_HASH + _REFUSAL_HASH + _JUDGE_HASH)`. EVAL-02 manifest reads combined; ablation reports + structlog read per-prompt.

**D-09 — Judge migration scope = prompt + parser, not the dispatch.** Move `_JUDGE_SYSTEM_PROMPT` + `_build_judge_prompt(prediction, reference, rubric)` body into `prompts.py` as `JUDGE_PROMPT` + `build_judge_user_prompt(...)`. **Replace** heuristic `_SCORE_PATTERN` regex parser with structured JSON-mode output: Anthropic uses `tools=[{name, input_schema, strict: true}]` + `tool_choice={"type": "tool", "name": "submit_verdict"}`; OpenAI uses `response_format={"type": "json_schema", "json_schema": {name, strict: true, schema}}`. Both adapter paths deserialize directly into `JudgeVerdict`. **Preserve** Phase 2 D-04 cross-family wiring in `adapters/real/judge.py` — `CrossFamilyJudge` class, `Settings.llm_real_provider` complement-selection, tenacity-delegation stay.

**D-10 — Inline `[chunk_id]` brackets with locked fenced example in `SYNTHESIS_PROMPT`.** Verbatim example with two `[TICKER-FYxxxx-Item-XX-NNN]` citations. Explicit faithfulness rule. Matches existing stub `_CHUNK_RE = re.compile(r"\[([^\]]+)\]")` (Phase 2 D-16) verbatim.

**D-11 — Canonical refusal sentinel = `"I cannot answer this question from the retrieved 10-K excerpts."`** Stored in `REFUSAL_PROMPT`. Generator checks `generation_text.startswith(REFUSAL_TEXT_SENTINEL)` to set `refused = True`. Phase 2 stub `_STUB_REFUSAL` updates to emit this new sentinel verbatim.

**D-12 — Stub adapter update.** `packages/docintel-core/src/docintel_core/adapters/stub/llm.py` amended: `_STUB_REFUSAL` value changes to match `REFUSAL_PROMPT_SENTINEL` from `docintel_generate.prompts` (one upward-stack import allowed; generator never imports stub). `[STUB ANSWER citing ...]` template unchanged. `_CHUNK_RE` moves to `docintel_generate.parse._CHUNK_RE` and is re-imported by the stub.

**D-13 — Faithfulness enforcement = prompt-instructed + post-hoc parse, NO blocking.** Pipeline: build user prompt → `bundle.llm.complete(prompt, system=SYNTHESIS_PROMPT)` (already tenacity-wrapped at adapter layer; NO new wrap site) → `_CHUNK_RE.findall(response.text)` to extract `cited_chunk_ids` → validate every cited chunk_id is in `{c.chunk_id for c in retrieved_chunks}`; drop hallucinated IDs with `generator_hallucinated_chunk_id` warning (text NOT modified) → check `response.text.startswith(REFUSAL_TEXT_SENTINEL)` to set `refused = True` → return `GenerationResult(...)`. No re-prompting, no sentence-stripping.

**D-14 — Chunk formatting = numbered `<context>` blocks with metadata header.** Format: `<context>` opens; per chunk `[chunk_id: X | company: Y | fiscal_year: Z | section: W]` + raw chunk.text + `---` separator; `</context>` closes; `Question: <user query>` follows. Four-field header matches `RetrievedChunk` (Phase 5 D-03). XML-style tag for both Claude and GPT.

**D-15 — `Generator.generate(query: str, k: int = 5) -> GenerationResult`** single seam. Pipeline: **Step A** `self._retriever.search(query, k=k)`; **Step B** if empty → hard refusal `GenerationResult(text=REFUSAL_TEXT_SENTINEL, cited_chunk_ids=[], refused=True, retrieved_chunks=[], completion=None, prompt_version_hash=PROMPT_VERSION_HASH)` + `generator_refused_zero_chunks` warn; **Step C** format D-14 context, call `bundle.llm.complete(prompt=user_prompt, system=SYNTHESIS_PROMPT)`; **Step D** parse citations + refusal sentinel; **Step E** emit `generator_completed` + return.

**D-16 — Single `generator_completed` structlog line** with 14 fields: `query_tokens`, `n_chunks_retrieved`, `n_chunks_cited`, `refused`, `prompt_version_hash`, `synthesis_hash`, `refusal_hash`, `judge_hash`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `retrieval_ms`, `generation_ms`, `total_ms`, `model`. (Note: count includes both `prompt_version_hash` and the three per-prompt hashes — that's 4 hash fields + 10 metric fields = 14 emitted, plus the implicit log-level/timestamp from `configure_logging` processors.) Phase 9 MET-05 reads `cost_usd` + `total_ms`; Phase 9 MET-03 reads `refused`; Phase 12 binds `trace_id` via `contextvars` automatically.

**D-17 — `GenerationResult`** is a new Pydantic model in `docintel_core.types` with `ConfigDict(extra="forbid", frozen=True)`. Fields: `text: str`, `cited_chunk_ids: list[str]`, `refused: bool`, `retrieved_chunks: list[RetrievedChunk]`, `completion: CompletionResponse | None`, `prompt_version_hash: str`. Home matches `RetrievedChunk` precedent (Phase 5 CD-02 / Phase 4 IndexManifest). `frozen=True` matches `RetrievedChunk` — downstream callers can't mutate.

### Claude's Discretion

- **CD-01 — Exact SYNTHESIS_PROMPT wording.** Structure is locked (system + user with `<context>` blocks, citation example, refusal sentinel, faithfulness rule); exact phrasing is planner discretion.
- **CD-02 — Exact JUDGE_PROMPT wording + structured-output schema field names.** Migration is locked (move to `prompts.py`, switch parser to structured output via SDK structured-output APIs); exact JSON schema field labels = `JudgeVerdict` shape (`score`, `passed`, `reasoning`, `unsupported_claims`).
- **CD-03 — `Generator.__init__` eager-load vs lazy-load.** Recommend EAGER (matches Phase 5 CD-01 `Retriever` precedent — instantiation cheap, first-call cost is SDK init which is already lazy in `AnthropicAdapter._get_client`).
- **CD-04 — Tenacity retry on the LLM call.** None added at Phase 6. Phase 5 CD-04 carries over verbatim. `bundle.llm.complete(...)` already wrapped at adapter layer (Phase 2 D-18). `scripts/check_adapter_wraps.sh` continues to enforce; `check_prompt_locality.sh` is independent.
- **CD-05 — `make_generator(cfg)` caching.** NO factory-level cache. Phase 13 FastAPI `lru_cache`s the `Generator`; Phase 10 eval harness constructs once per run.
- **CD-06 — Context-window budget verification.** Planner verifies during execution by logging `prompt_tokens` on hero question and confirming < 8K. K=5 × ~500 BGE tokens ≈ 2500 tokens chunk + ~400 system + ~100 question + ~200 scaffolding ≈ 3.2-3.5K total; well under Claude Sonnet 4.6 200K and GPT-4-class ≥128K context.
- **CD-07 — Hallucinated chunk_id handling = log + drop** (not raise). Phase 9 MET-04 measures citation accuracy as a fraction; raising on hallucination converts a measurable failure mode into a hard crash, hurting eval signal.
- **CD-08 — Test layout for `docintel-generate`.** Wave 0 scaffolds (xfail) mirroring Phase 5 pattern: one test file per requirement (GEN-01 grep gate, GEN-02 hash exposure, GEN-03 stub determinism, GEN-04 refusal path) + integration tests for `Generator.generate()` end-to-end (stub mode every PR; real-mode `@pytest.mark.real` + workflow_dispatch).
- **CD-09 — JSON-mode SDK call signature.** Anthropic 0.101.0 supports `tools=[{name, input_schema, strict: true}]` + `tool_choice={"type": "tool", "name": "submit_verdict"}` (GA, stable since 0.85-ish). OpenAI 2.36.0 supports `response_format={"type": "json_schema", "json_schema": {name, strict: true, schema}}` (GA). No dep pin bumps required.
- **CD-10 — Wave structure.** Recommend 5 waves matching Phase 5's shape (researcher refines below).

### Deferred Ideas (OUT OF SCOPE)

- Per-question-type prompt routing (`FACTUAL_PROMPT`, `COMPARATIVE_PROMPT`).
- Footnote-style `[1]` citations with mapping section.
- Score-threshold refusal gate.
- Question-aware refusal text (refusal echoes topic).
- Re-prompting on missing citations.
- Stripping uncited sentences.
- Generator owning retrieval AND generation as `.answer(query)`.
- Already-shaped `Answer` (Phase 7 schema) as Phase 6 return.
- `make_generator(cfg)` factory-level cache.
- Async / streaming generator API.
- Three-provider judge rotation.
- Re-tokenize check on synthesis-prompt context-window budget.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **GEN-01** | All prompts live in `prompts.py`; grep for inline string-literal prompts outside this file returns zero matches (CI gate) | §4 (CI grep gate design), §6 (Wave 0 test scaffold for grep gate), `scripts/check_prompt_locality.sh` template from `check_adapter_wraps.sh`. Path updates to `packages/docintel-generate/src/docintel_generate/prompts.py` per D-02. |
| **GEN-02** | Each prompt has a deterministic version hash exposed as `PROMPT_VERSION_HASH`; included in every eval report manifest | §3 (Prompt versioning + hash exposure), §6 (Wave 0 hash test). `hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]` at module import time, `Final[str]` mypy-strict. Per-prompt + combined per D-08. |
| **GEN-03** | Generator gated by `LLM_PROVIDER`, uses `LLMClient` adapter; stub generator returns deterministic placeholder answers covering full schema | §5 (Generator API + telemetry), §6 (stub determinism test). `make_generator(cfg)` 4th sibling factory; stub returns `[STUB ANSWER citing chunk_ids]` deterministic per Phase 2 D-16. |
| **GEN-04** | Refusal path — generator returns explicit refusal when retrieved evidence is insufficient | §5 (Step B hard-refusal path), §6 (refusal test). Dual-layer per D-10/D-11: hard zero-chunk floor skips LLM; LLM-driven sentinel emitted otherwise. |

</phase_requirements>

## Summary

Phase 6 ships a query-time generation seam — `Generator(bundle, retriever).generate(query, k) -> GenerationResult` — by composing two already-shipped contracts (Phase 2 `AdapterBundle` + Phase 5 `Retriever`) under a thin orchestrator that owns three responsibilities the upstream phases deliberately left open: **(1)** prompt locality (GEN-01 grep gate), **(2)** prompt version-hash exposure (GEN-02 manifest contract), and **(3)** refusal semantics (GEN-04 dual-layer hard-floor + LLM-driven sentinel). The phase also migrates Phase 2's placeholder judge prompt + heuristic regex parser into `prompts.py` + structured JSON-mode output so Phase 9/10 eval reports inherit a stable `PROMPT_VERSION_HASH` from the first eval forward — bisection on faithfulness metrics requires this hash not drift mid-eval. [VERIFIED: CONTEXT.md D-01..D-17, repo source under `packages/docintel-core/src/docintel_core/adapters/`]

The research below confirms three load-bearing technical decisions: **(a)** the pinned `anthropic==0.101.0` and `openai==2.36.0` SDKs both expose structured-output APIs as GA (no pin bumps required — verified against PyPI changelogs and live Anthropic docs); **(b)** the `[chunk_id]`-bracket citation pattern + post-hoc validation against `retrieved_chunks` set is the documented standard for citation-grounded RAG (verified against Anthropic prompt-engineering docs and the FACTUM citation-hallucination paper); **(c)** prompt versioning via per-prompt + combined SHA256[:12] at module import time is the industry-standard pattern for deterministic prompt manifests (verified against Braintrust + LangSmith + LaunchDarkly prompt-versioning guides). [VERIFIED: pypi.org `anthropic` + `openai` package JSON; platform.claude.com structured-outputs docs; Braintrust prompt-versioning guide]

**Primary recommendation:** Plan 5 waves matching Phase 5's shape — Wave 0 scaffolds + skeleton + docs/CI gate, Wave 1 `prompts.py` + `parse.py`, Wave 2 `Generator` + `make_generator` + `GenerationResult`, Wave 3 judge migration + stub sentinel sync, Wave 4 CI wiring + xfail removal + Decision-Coverage Audit. Total ~7 plans across 5 waves (Wave 0 has 2-3 parallel plans per disjoint files_modified). Avoid hand-rolling: structured-output parsers (SDK does it), prompt-template DSLs (plain Python f-strings cover D-14), citation extractors beyond the existing `_CHUNK_RE` (Phase 2 D-16 locked the regex).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Query → answer orchestration | `docintel-generate` (Generator) | — | New 8th workspace package per D-01; sibling to `docintel-retrieve`. |
| Retrieval (Phase 5) | `docintel-retrieve` (Retriever) | — | Already shipped; `Generator` delegates to `Retriever.search` in Step A. |
| LLM call surface (synthesis + judge) | `docintel-core` adapter layer (LLMClient real adapters) | — | Already tenacity-wrapped (Phase 2 D-18). Phase 6 only changes the `system` parameter content. |
| Prompt definitions + version hash | `docintel-generate.prompts` | — | Single source of truth per GEN-01 + D-02. Manifest consumer in `docintel-eval` (Phase 10). |
| Citation extraction regex | `docintel-generate.parse` | `docintel-core.adapters.stub.llm` (re-imports) | One regex across stub + real per D-12. Phase 7's `Citation` parser also reuses it. |
| Result Pydantic model | `docintel-core.types.GenerationResult` | — | Shared contract per CD-02 (matches `RetrievedChunk` precedent) — Phase 7 imports without depending on `docintel-generate`. |
| Factory composition | `docintel-core.adapters.factory.make_generator` | — | 4th sibling factory; matches Phase 5 D-04 import direction (`docintel-generate` imports from `docintel-core`, never reverse). |
| CI grep gate | `scripts/check_prompt_locality.sh` | `.github/workflows/ci.yml` | Mirrors three existing wrap-gate scripts; one new `bash scripts/check_prompt_locality.sh` step per D-06. |
| Per-query telemetry | `docintel-generate.generator` (single structlog line) | `docintel-core.log` (configure_logging + merge_contextvars) | One `generator_completed` line per D-16; Phase 12 binds `trace_id` automatically via contextvars (no Phase 6 retrofit). |
| Hallucinated chunk_id handling | `docintel-generate.generator` (log + drop) | `docintel-core.log` (structlog warning) | Per D-13 + CD-07: measurement, not enforcement. Phase 9 MET-04 reads the rate. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `anthropic` (Python SDK) | `0.101.0` (currently pinned in `docintel-core/pyproject.toml`); range `>=0.101.0,<1` | Claude Sonnet 4.6 client for `AnthropicAdapter.complete` synthesis + judge calls. `tools=[{name, input_schema, strict: true}]` + `tool_choice={"type": "tool", "name": "submit_verdict"}` for structured JSON output. | GA structured-output via tools API since SDK 0.85 (March 2026 — verified against repo CHANGELOG). Strict tool use available; response shape stable. [VERIFIED: github.com/anthropics/anthropic-sdk-python/CHANGELOG.md] |
| `openai` (Python SDK) | `2.36.0` (currently pinned); range `>=2.36.0,<3` | GPT-4o client for `OpenAIAdapter.complete`. `response_format={"type": "json_schema", "json_schema": {name, strict: true, schema}}` for structured JSON output. | Structured Outputs with `json_schema` GA since SDK 1.40 (Aug 2024); model support since gpt-4o-2024-08-06. Stable in 2.36. [VERIFIED: github.com/openai/openai-python/CHANGELOG.md; pypi.org/project/openai] |
| `pydantic` (v2) | `2.13.3` (existing pin) | `GenerationResult` model with `ConfigDict(extra="forbid", frozen=True)`. | Already in use across the workspace (`Chunk`, `RetrievedChunk`, `IndexManifest`). `frozen=True` matches existing precedents. [VERIFIED: docintel-core/pyproject.toml line 6] |
| `tenacity` | `9.1.4` (existing pin) | Inherited from Phase 2 D-18 wraps on adapter `.complete()` calls. **No new tenacity wrap sites in Phase 6** (CD-04). | One wrap site per SDK call site; Phase 6 composes already-wrapped adapter calls. [VERIFIED: CONTEXT.md CD-04; docintel-core/pyproject.toml line 16] |
| `structlog` | `25.5.0` (existing pin) | Single `generator_completed` log line + `generator_hallucinated_chunk_id` warning + `generator_refused_zero_chunks` warning. | Already wired in `docintel_core.log.configure_logging` with `merge_contextvars` (Phase 1) — Phase 12 will bind `trace_id` automatically. [VERIFIED: docintel-core/pyproject.toml line 9; docintel-core/src/docintel_core/log.py] |
| `hashlib` (stdlib) | Python 3.11 | `sha256(s.encode("utf-8")).hexdigest()[:12]` for per-prompt + combined `PROMPT_VERSION_HASH`. | Standard library; deterministic; matches the industry-standard prompt-versioning pattern (Braintrust, LangSmith, LaunchDarkly use SHA256 of prompt template). [VERIFIED: braintrust.dev prompt-versioning guide; launchdarkly.com blog] |
| `hatchling` | (workspace default) | Build backend for new `docintel-generate` package. | Workspace pyproject default; matches Phase 3 / 4 / 5 precedent. [VERIFIED: docintel-retrieve/pyproject.toml lines 11-13] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `docintel-core` (workspace) | `0.1.0` | Workspace dep for `Generator`. Provides `AdapterBundle`, `RetrievedChunk`, `GenerationResult` (new), `CompletionResponse`, `LLMClient` protocol. | Always — the `Generator` class composes `bundle.llm`. |
| `docintel-retrieve` (workspace) | `0.1.0` | Workspace dep for `Generator`. Provides `Retriever`. | Always — `Generator.__init__(bundle, retriever)` takes the constructed `Retriever`. |
| `pytest` (test-only) | (workspace) | Test scaffolds (xfail) + real-mode `@pytest.mark.real`. | All test layers. |
| `numpy` (test-only / via retrieve) | `2.4.4` | Not used directly by `Generator`; pulled in transitively via `docintel-retrieve`. | Existing transitive dep. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `tools=[{...}]` + `tool_choice={"type": "tool"}` for Anthropic judge | `output_config={"format": {"type": "json_schema", "schema": {...}}}` (newer Anthropic JSON Outputs API; the docs call this "Structured Outputs" GA) | The `output_config` API is stable and arguably cleaner (response.content[0].text is the JSON directly), BUT it was only added across the recent SDK series; `tools=[{strict: true}]` is the older + more broadly-documented path and works on Claude Sonnet 4.6 verbatim. **Recommendation:** use `tools=[]` + `tool_choice` for D-09 to minimize the SDK-feature-availability risk; revisit if Phase 9 finds it overspending tokens vs `output_config`. [VERIFIED: platform.claude.com/docs/en/build-with-claude/structured-outputs] |
| `response_format={"type": "json_schema", ...}` for OpenAI judge | `client.beta.chat.completions.parse()` with Pydantic model directly | `.parse()` is the SDK-native ergonomic path (auto-generates schema from `JudgeVerdict`, auto-deserializes), BUT lives under `.beta` namespace in `openai==2.36.0` and has had instability across the 1.x → 2.x bumps (see github.com/openai/openai-python/issues/1763, 1733). **Recommendation:** use the stable `response_format` dict path; cleaner separation from `.beta.*` API drift. [VERIFIED: github.com/openai/openai-python/issues/1733; helpers.md in repo] |
| Per-prompt `Final[str]` hash constants computed at import time | Hash file at first `.generate()` call + cache | Import-time matches `Final[str]` annotation — mypy-strict can verify; no race conditions; no first-call latency. Lazy is strictly worse here. **Recommendation:** keep import-time. [VERIFIED: CONTEXT.md D-08] |
| `<context>` XML-style tag for chunk wrapping | JSON-structured input (`{"chunks": [...]}`) | Anthropic prompt-engineering docs explicitly call out XML tags as the "most effective way to provide RAG context" (Claude trained on XML during fine-tuning); GPT-4-class models also reliably parse XML tags. JSON would double token budget on `{"chunk_id": "..."}` quoting. **Recommendation:** keep `<context>` per D-14. [CITED: docs.anthropic.com/claude/docs/use-xml-tags; shshell.com RAG-prompting lesson] |
| Module-level function `generate(query, bundle, retriever)` | `Generator(bundle, retriever).generate(query, k)` class | Class composition matches Phase 5 `Retriever` precedent — Phase 13 FastAPI `lru_cache`s the constructed object; Phase 11 ablations swap the bundle without re-importing the function. **Recommendation:** class per D-15. [VERIFIED: CONTEXT.md D-15; retriever.py line 1] |

**Installation:**

```bash
# All deps already in docintel-core; docintel-generate adds workspace deps only.
# Plan creates packages/docintel-generate/pyproject.toml:
#   dependencies = ["docintel-core", "docintel-retrieve"]
# Then:
uv lock           # regen lockfile
uv sync --all-packages --frozen
```

**Version verification (executed 2026-05-15):**

| Package | Pinned in repo | Latest on PyPI | Action |
|---------|----------------|---------------|--------|
| `anthropic` | `0.101.0` (range `>=0.101.0,<1`) | `0.102.0` (released 2026-05-13) | **No bump required.** 0.101.0 already exposes `tools=[{strict: true}]` + `tool_choice` — these went GA around 0.85.0 (March 2026). |
| `openai` | `2.36.0` (range `>=2.36.0,<3`) | `2.36.0` (released 2026-05-07) | **No bump required.** `response_format={"type": "json_schema", ...}` available since 1.40 (Aug 2024). Latest pinned. |
| `pydantic` | `2.13.3` | (existing) | No change. |
| `tenacity` | `9.1.4` | (existing) | No change. |
| `structlog` | `25.5.0` | (existing) | No change. |

[VERIFIED: pypi.org JSON metadata for anthropic + openai packages; CHANGELOG.md in both repos; docintel-core/pyproject.toml lines 11-16]

## Architecture Patterns

### System Architecture Diagram

```
                              ┌──────────────────────────────────────────────┐
                              │  Caller (Phase 10 eval / Phase 13 FastAPI)   │
                              │  - constructs via make_generator(cfg)        │
                              │  - lru_cache OK at this layer (CD-05)        │
                              └────────────────────┬─────────────────────────┘
                                                   │ .generate(query, k=5)
                                                   ▼
              ┌─────────────────────────────────────────────────────────────────────┐
              │                  Generator (docintel-generate)                       │
              │                                                                      │
              │   Step A: retriever.search(query, k=k) ─► list[RetrievedChunk]      │
              │           (Phase 5 — already emits retriever_search_completed)      │
              │                            │                                         │
              │           empty? ──── yes ─┼──► Step B: HARD REFUSAL                 │
              │                            │     - skip LLM entirely                 │
              │                            │     - emit generator_refused_zero_chunks│
              │                            │     - GenerationResult(completion=None) │
              │                            │     - return                            │
              │                            │ no                                      │
              │                            ▼                                         │
              │   Step C: format <context> block per D-14                           │
              │           bundle.llm.complete(prompt=user_prompt,                   │
              │                                system=SYNTHESIS_PROMPT)              │
              │           (already @retry-wrapped per Phase 2 D-18 — CD-04 no new)  │
              │                            │                                         │
              │                            ▼                                         │
              │   Step D: parse with _CHUNK_RE.findall(response.text)               │
              │           validate cited ⊆ retrieved set                             │
              │           drop hallucinated IDs + emit generator_hallucinated_chunk_id│
              │           check response.text.startswith(REFUSAL_TEXT_SENTINEL)     │
              │                            │                                         │
              │                            ▼                                         │
              │   Step E: emit generator_completed (14 fields) → return             │
              │                            │                                         │
              └────────────────────────────┼─────────────────────────────────────────┘
                                           │
                                           ▼
                              ┌─────────────────────────────┐
                              │   GenerationResult           │
                              │   (docintel_core.types)      │
                              │   - text                     │
                              │   - cited_chunk_ids          │
                              │   - refused                  │
                              │   - retrieved_chunks         │
                              │   - completion: CR | None    │
                              │   - prompt_version_hash      │
                              │   ConfigDict(extra='forbid', │
                              │              frozen=True)    │
                              └──────────────────────────────┘

                   ┌─────────────────────┐
                   │ docintel-generate   │
                   │  /prompts.py        │ ──► imported by Generator (synthesis)
                   │   - SYNTHESIS_PROMPT│      AND by adapters/real/judge.py (judge)
                   │   - REFUSAL_PROMPT  │      AND by adapters/stub/llm.py (refusal sentinel)
                   │   - JUDGE_PROMPT    │      AND by Phase 10 eval manifest (PROMPT_VERSION_HASH)
                   │   - PROMPT_VERSION_HASH ────► EVAL-02 manifest header
                   │   - _SYNTHESIS_HASH ────────► ablation reports + generator_completed
                   │   - _REFUSAL_HASH               structlog line
                   │   - _JUDGE_HASH
                   └─────────────────────┘

                   ┌─────────────────────┐
                   │ docintel-generate   │
                   │  /parse.py          │ ──► _CHUNK_RE re-imported by stub LLM (D-12)
                   │   - _CHUNK_RE       │      AND by Generator Step D
                   │   - REFUSAL_TEXT_   │      AND by Phase 7 Citation parser
                   │     SENTINEL helpers│
                   └─────────────────────┘

                   ┌─────────────────────┐
                   │ scripts/check_      │ ──► CI grep gate per D-06
                   │   prompt_locality.sh│      Mirrors 3 existing wrap gates
                   └─────────────────────┘
```

[VERIFIED: matches D-01..D-17 verbatim; cross-references Phase 5 `docintel_retrieve/retriever.py:1-100`]

### Recommended Project Structure

```
packages/docintel-generate/
├── pyproject.toml                                     # workspace deps: docintel-core, docintel-retrieve
├── src/
│   └── docintel_generate/
│       ├── __init__.py                                # re-exports Generator, GenerationResult, *_PROMPT, PROMPT_VERSION_HASH
│       ├── prompts.py                                 # SYNTHESIS_PROMPT, REFUSAL_PROMPT, JUDGE_PROMPT + hashes
│       ├── generator.py                               # Generator class + REFUSAL_TEXT_SENTINEL constant
│       ├── parse.py                                   # _CHUNK_RE + sentinel-detection helpers
│       └── py.typed                                   # PEP 561 marker

packages/docintel-core/src/docintel_core/
├── types.py                                           # ADDS GenerationResult (D-17)
└── adapters/
    ├── factory.py                                     # ADDS make_generator(cfg) — 4th sibling factory (D-03)
    ├── real/
    │   └── judge.py                                   # MIGRATED: removes _JUDGE_SYSTEM_PROMPT + _build_judge_prompt + _SCORE_PATTERN; imports JUDGE_PROMPT from prompts.py; switches parser to structured JSON-mode (D-09)
    └── stub/
        └── llm.py                                     # _STUB_REFUSAL value updated to mirror REFUSAL_PROMPT sentinel; _CHUNK_RE re-imports from docintel_generate.parse (D-12)

scripts/
└── check_prompt_locality.sh                           # NEW CI grep gate (D-04)

.github/workflows/
└── ci.yml                                             # ADDS one step: bash scripts/check_prompt_locality.sh (D-06)

tests/
├── test_prompt_locality.py                            # GEN-01 — grep gate exit-code test
├── test_prompt_version_hash.py                        # GEN-02 — hash exposure + sensitivity test
├── test_generator_stub_determinism.py                 # GEN-03 — stub-mode deterministic output
├── test_generator_refusal.py                          # GEN-04 — dual-layer refusal (hard zero + LLM sentinel)
├── test_generator_search_integration.py               # end-to-end Generator + stub Retriever
├── test_make_generator.py                             # D-03 factory + lazy-import gate
└── test_judge_structured_output.py                    # D-09 structured-output deserializer (xfail until Wave 3)

CLAUDE.md                                              # D-02 path update
.planning/config.json                                  # D-02: constraints.prompt_home → new path
.planning/REQUIREMENTS.md                              # D-02: GEN-01 path update
.planning/ROADMAP.md                                   # D-02: Phase 6 Provides: line update
.planning/PROJECT.md                                   # D-02: Constraints "Prompts are versioned" path update
```

[VERIFIED: matches D-01..D-17, D-02 docs sweep list verbatim; structure mirrors Phase 5 `packages/docintel-retrieve/`]

### Pattern 1: Single-Seam Generator with Composed Adapters

**What:** One callable, end-to-end (`Generator.generate(query, k) -> GenerationResult`). Mirrors Phase 5's `Retriever.search()` shape.

**When to use:** Always — for the synthesis path. Phase 6 has no two-stage public API; internal steps (`_format_context`, `_parse_citations`) are private methods.

**Example:**

```python
# Source: packages/docintel-generate/src/docintel_generate/generator.py (Wave 2 — planner refines)
# Pattern matches packages/docintel-retrieve/src/docintel_retrieve/retriever.py Steps A..G

from __future__ import annotations

import time
from typing import Final

import structlog
from docintel_core.adapters.types import AdapterBundle, CompletionResponse
from docintel_core.types import GenerationResult, RetrievedChunk
from docintel_retrieve.retriever import Retriever

from docintel_generate.parse import _CHUNK_RE
from docintel_generate.prompts import (
    PROMPT_VERSION_HASH,
    REFUSAL_PROMPT,
    SYNTHESIS_PROMPT,
    _REFUSAL_HASH,
    _SYNTHESIS_HASH,
    _JUDGE_HASH,
)

log = structlog.stdlib.get_logger(__name__)

# Derived from REFUSAL_PROMPT body — the exact sentinel string we instruct
# the LLM to emit verbatim and that we grep for in response.text.
REFUSAL_TEXT_SENTINEL: Final[str] = (
    "I cannot answer this question from the retrieved 10-K excerpts."
)


class Generator:
    def __init__(self, bundle: AdapterBundle, retriever: Retriever) -> None:
        self._bundle = bundle
        self._retriever = retriever

    def generate(self, query: str, k: int = 5) -> GenerationResult:
        t_total_start = time.perf_counter()

        # Step A — retrieval (already emits retriever_search_completed)
        t_retr_start = time.perf_counter()
        retrieved = self._retriever.search(query, k=k)
        retrieval_ms = (time.perf_counter() - t_retr_start) * 1000

        # Step B — hard zero-chunk refusal (skip LLM)
        if not retrieved:
            log.warning("generator_refused_zero_chunks", query_tokens=len(query.split()))
            result = GenerationResult(
                text=REFUSAL_TEXT_SENTINEL,
                cited_chunk_ids=[],
                refused=True,
                retrieved_chunks=[],
                completion=None,
                prompt_version_hash=PROMPT_VERSION_HASH,
            )
            self._emit_completed(query, result, retrieval_ms, 0.0,
                                 (time.perf_counter() - t_total_start) * 1000)
            return result

        # Step C — format + call LLM (already tenacity-wrapped at adapter)
        user_prompt = self._format_user_prompt(query, retrieved)
        t_gen_start = time.perf_counter()
        completion = self._bundle.llm.complete(prompt=user_prompt, system=SYNTHESIS_PROMPT)
        generation_ms = (time.perf_counter() - t_gen_start) * 1000

        # Step D — citation parse + hallucination drop + refusal detect
        raw_ids = _CHUNK_RE.findall(completion.text)
        retrieved_id_set = {c.chunk_id for c in retrieved}
        cited_chunk_ids: list[str] = []
        seen: set[str] = set()
        for cid in raw_ids:
            if cid in retrieved_id_set and cid not in seen:
                cited_chunk_ids.append(cid)
                seen.add(cid)
            elif cid not in retrieved_id_set:
                log.warning("generator_hallucinated_chunk_id", chunk_id=cid, query_tokens=len(query.split()))

        refused = completion.text.startswith(REFUSAL_TEXT_SENTINEL)

        result = GenerationResult(
            text=completion.text,
            cited_chunk_ids=cited_chunk_ids,
            refused=refused,
            retrieved_chunks=retrieved,
            completion=completion,
            prompt_version_hash=PROMPT_VERSION_HASH,
        )

        # Step E — telemetry + return
        self._emit_completed(query, result, retrieval_ms, generation_ms,
                             (time.perf_counter() - t_total_start) * 1000)
        return result

    def _format_user_prompt(self, query: str, retrieved: list[RetrievedChunk]) -> str:
        # D-14: numbered <context> blocks with [chunk_id | company | fiscal_year | section] header
        lines = ["<context>"]
        for c in retrieved:
            lines.append(
                f"[chunk_id: {c.chunk_id} | company: {c.ticker} | "
                f"fiscal_year: {c.fiscal_year} | section: {c.item_code}]"
            )
            lines.append(c.text)
            lines.append("---")
        lines.append("</context>")
        lines.append("")
        lines.append(f"Question: {query}")
        return "\n".join(lines)

    def _emit_completed(self, query: str, result: GenerationResult,
                        retrieval_ms: float, generation_ms: float, total_ms: float) -> None:
        comp = result.completion
        log.info(
            "generator_completed",
            query_tokens=len(query.split()),
            n_chunks_retrieved=len(result.retrieved_chunks),
            n_chunks_cited=len(result.cited_chunk_ids),
            refused=result.refused,
            prompt_version_hash=PROMPT_VERSION_HASH,
            synthesis_hash=_SYNTHESIS_HASH,
            refusal_hash=_REFUSAL_HASH,
            judge_hash=_JUDGE_HASH,
            prompt_tokens=comp.usage.prompt_tokens if comp else 0,
            completion_tokens=comp.usage.completion_tokens if comp else 0,
            cost_usd=comp.cost_usd if comp else 0.0,
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
            total_ms=total_ms,
            model=comp.model if comp else "stub-refusal",
        )
```

[VERIFIED: structure matches D-13, D-14, D-15, D-16 verbatim; pattern derived from `packages/docintel-retrieve/src/docintel_retrieve/retriever.py` Steps A..G]

### Pattern 2: Module-Import-Time Prompt Hashing

**What:** Compute SHA256[:12] of each prompt body at module load, assigned to `Final[str]` constants. Combined hash is SHA256[:12] of the concatenation of the three per-prompt hashes.

**When to use:** Every named prompt that needs to land in the manifest. GEN-02 + EVAL-02 manifest contract requires deterministic, grep-able hashes.

**Example:**

```python
# Source: packages/docintel-generate/src/docintel_generate/prompts.py
# Pattern: D-08 verbatim; matches industry standard (Braintrust, LangSmith)

from __future__ import annotations

import hashlib
from typing import Final


def _h(s: str) -> str:
    """SHA256 truncated to 12 hex chars — manifest-friendly."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


SYNTHESIS_PROMPT: Final[str] = """You are answering a question using ONLY the
retrieved 10-K excerpts provided in the <context> block.

[... full body — planner's discretion per CD-01 — must include:
 - explicit instruction to ground every claim in <context>
 - locked fenced citation example (D-10):
     Example:
     Apple highlighted supplier concentration in China and Taiwan as a key
     risk in its FY2024 10-K [AAPL-FY2024-Item-1A-018]. NVIDIA disclosed
     revenue concentration with a single hyperscaler customer
     [NVDA-FY2024-Item-7-042].
 - refusal-when-insufficient instruction emitting verbatim:
     "I cannot answer this question from the retrieved 10-K excerpts."
 - no-invented-chunk-ids rule
 - cite-from-context-only rule
]"""

REFUSAL_PROMPT: Final[str] = (
    "I cannot answer this question from the retrieved 10-K excerpts."
)

JUDGE_PROMPT: Final[str] = """You are a strict citation-faithfulness judge.
[... full body — planner's discretion per CD-02 — must instruct the LLM to:
 - output structured JSON matching {score: float, passed: bool,
   reasoning: str, unsupported_claims: list[str]}
 - score in [0.0, 1.0]; passed = score >= 0.5
 - list unsupported_claims explicitly
 - avoid self-preference / family bias by judging only the prediction-vs-reference
   structural match
]"""

_SYNTHESIS_HASH: Final[str] = _h(SYNTHESIS_PROMPT)
_REFUSAL_HASH: Final[str] = _h(REFUSAL_PROMPT)
_JUDGE_HASH: Final[str] = _h(JUDGE_PROMPT)
PROMPT_VERSION_HASH: Final[str] = _h(_SYNTHESIS_HASH + _REFUSAL_HASH + _JUDGE_HASH)
```

[CITED: braintrust.dev/articles/what-is-prompt-versioning (SHA-based versioning industry standard); CONTEXT.md D-08 verbatim]

### Pattern 3: Structured-Output Judge Parser (Anthropic + OpenAI)

**What:** Replace heuristic regex parsing of the judge LLM response with provider-native structured output. Both SDKs deserialize directly into `JudgeVerdict`.

**When to use:** Inside `CrossFamilyJudge.judge()` in `adapters/real/judge.py` — Wave 3 migration per D-09.

**Example (Anthropic — `tools=[]` + `tool_choice` path):**

```python
# Source: packages/docintel-core/src/docintel_core/adapters/real/judge.py (Wave 3 amendment)
# Reference: github.com/anthropics/anthropic-sdk-python/CHANGELOG.md (tools API GA since 0.85)
# Reference: platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use

import json
from anthropic import Anthropic
from docintel_core.adapters.types import JudgeVerdict
from docintel_generate.prompts import JUDGE_PROMPT, build_judge_user_prompt

_JUDGE_VERDICT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "passed": {"type": "boolean"},
        "reasoning": {"type": "string"},
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "passed", "reasoning", "unsupported_claims"],
}

# Inside CrossFamilyJudge.judge() when self._llm is an AnthropicAdapter:
def _judge_via_anthropic(client: Anthropic, user_prompt: str) -> JudgeVerdict:
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=JUDGE_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        tools=[{
            "name": "submit_verdict",
            "description": "Submit the faithfulness verdict for the prediction.",
            "input_schema": _JUDGE_VERDICT_SCHEMA,
            "strict": True,
        }],
        tool_choice={"type": "tool", "name": "submit_verdict"},
    )
    # response.content is a list of blocks; the tool_use block carries .input
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_verdict":
            return JudgeVerdict(**block.input)
    raise RuntimeError("judge response missing tool_use block")
```

**Example (OpenAI — `response_format` path):**

```python
# Reference: github.com/openai/openai-python/helpers.md
# Reference: openai.com/index/introducing-structured-outputs-in-the-api

from openai import OpenAI
from docintel_core.adapters.types import JudgeVerdict

# Inside CrossFamilyJudge.judge() when self._llm is an OpenAIAdapter:
def _judge_via_openai(client: OpenAI, user_prompt: str) -> JudgeVerdict:
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=2048,
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "submit_verdict",
                "strict": True,
                "schema": _JUDGE_VERDICT_SCHEMA,
            },
        },
    )
    payload = json.loads(response.choices[0].message.content or "{}")
    return JudgeVerdict(**payload)
```

[VERIFIED: github.com/anthropics/anthropic-sdk-python/CHANGELOG.md (tools stable through 0.101); pypi.org/project/openai release 2.36.0; both SDKs already imported in `adapters/real/llm_anthropic.py:29` + `adapters/real/llm_openai.py:32`]

### Pattern 4: CI Grep Gate Mirroring Wrap-Gate Scripts

**What:** Bash script with grep, exits 1 on offending file with file+line message. Mirrors the three existing wrap-gate scripts.

**When to use:** Always — GEN-01 enforcement, run on every PR.

**Example:**

```bash
#!/usr/bin/env bash
# scripts/check_prompt_locality.sh — CI grep gate for GEN-01 (Phase 6 D-04).
#
# Fails if a Python file outside the allowlist contains an inline prompt-like
# string literal. Mirrors check_adapter_wraps.sh / check_index_wraps.sh /
# check_ingest_wraps.sh structure verbatim.
#
# Usage:
#   scripts/check_prompt_locality.sh [SCAN_DIR]
#
# SCAN_DIR defaults to packages/. Tests invoke with an explicit fixture dir.
#
# Default allowlist (planner finalises during execution):
#   - packages/docintel-generate/src/docintel_generate/prompts.py
#   - packages/docintel-generate/src/docintel_generate/parse.py
#   - tests/**, **/conftest.py, **/test_*.py
#   - packages/docintel-core/src/docintel_core/adapters/stub/llm.py
#     (pre-existing _STUB_REFUSAL + _CHUNK_RE per Phase 2 D-16 + Phase 6 D-12)
#
# Per-line escape: append `# noqa: prompt-locality` to silence a line.
# Outstanding exceptions grep-able via:
#   grep -rn 'noqa: prompt-locality' packages/
#
# Exit codes:
#   0 — no inline prompts outside allowlist
#   1 — at least one offending line found
set -euo pipefail

SCAN_DIR="${1:-packages/}"
PROBLEM=0

# Pattern set (D-04): identifier name OR phrase content > 80 chars
# Planner refines during execution. Default pattern is conservative.
NAME_PATTERN='_[A-Z_]*PROMPT[A-Z_]*\b|_[A-Z_]*INSTRUCTION[A-Z_]*\b|_[A-Z_]*SYSTEM_PROMPT\b'
PHRASE_PATTERN='\b(You are|Based on the|<context>|<chunks>|cite|grounded|chunk_id)\b'

ALLOWLIST=(
    "packages/docintel-generate/src/docintel_generate/prompts.py"
    "packages/docintel-generate/src/docintel_generate/parse.py"
    "packages/docintel-core/src/docintel_core/adapters/stub/llm.py"
)

# Build grep --exclude-dir / --exclude args from ALLOWLIST + tests/conftest.
EXCLUDES=("--exclude-dir=tests" "--exclude=conftest.py" "--exclude=test_*.py")
for f in "${ALLOWLIST[@]}"; do
    EXCLUDES+=("--exclude=$(basename "$f")")
done

# Identifier-name violations.
while IFS=: read -r file lineno match; do
    [[ -z "$file" ]] && continue
    if grep -q '# noqa: prompt-locality' <<<"$(sed -n "${lineno}p" "$file")"; then
        continue
    fi
    echo "FAIL: $file:$lineno matches identifier pattern: $match"
    PROBLEM=1
done < <(grep -rnE "${EXCLUDES[@]}" --include='*.py' "$NAME_PATTERN" "$SCAN_DIR" 2>/dev/null || true)

# Phrase content over 80 chars (planner refines).
while IFS=: read -r file lineno match; do
    [[ -z "$file" ]] && continue
    [[ ${#match} -lt 80 ]] && continue
    if grep -q '# noqa: prompt-locality' <<<"$(sed -n "${lineno}p" "$file")"; then
        continue
    fi
    echo "FAIL: $file:$lineno contains prompt-like phrase (>80 chars): $match"
    PROBLEM=1
done < <(grep -rnE "${EXCLUDES[@]}" --include='*.py' "$PHRASE_PATTERN" "$SCAN_DIR" 2>/dev/null || true)

if [ "$PROBLEM" -eq 0 ]; then
    echo "OK: no inline prompts outside allowlist"
fi
exit "$PROBLEM"
```

[VERIFIED: structural template from `scripts/check_adapter_wraps.sh`, `scripts/check_index_wraps.sh`, `scripts/check_ingest_wraps.sh`; allowlist + noqa pattern matches D-04 + D-05]

### Anti-Patterns to Avoid

- **Re-prompting the LLM on missing citations.** Doubles cost + latency; defeats Phase 9 MET-04 measurement. The decision is `log + drop` per D-13 + CD-07. [VERIFIED: CONTEXT.md deferred-ideas]
- **Stripping uncited sentences from the response.** Hides faithfulness regressions and produces mysteriously-truncated answers visible in the UI. [VERIFIED: CONTEXT.md deferred-ideas]
- **Score-threshold refusal gate.** Reranker scores are not calibrated across stub (cosine-over-hash) vs real (bge-reranker-base logits) — a threshold that works for stub fails for real. Dual-layer hard + LLM-driven sentinel is provider-agnostic. [VERIFIED: CONTEXT.md D-10 + deferred-ideas]
- **JSON-structured prompt input** (`{"chunks": [{"text": ...}]}`). LLMs over-fixate on JSON formatting overhead; doubles token budget on quoting. XML-style `<context>` tags are explicitly the recommended pattern (Anthropic prompt-engineering docs). [CITED: docs.anthropic.com/claude/docs/use-xml-tags]
- **Hand-rolled regex parsing of LLM JSON output for the judge.** Phase 2's `_SCORE_PATTERN` is the current placeholder; Phase 6 replaces it. The SDKs do schema-constrained generation natively; regex parsing was always a placeholder. [VERIFIED: `adapters/real/judge.py:52` placeholder TODO line]
- **Adding new tenacity wrap sites in `Generator.generate()`.** `bundle.llm.complete()` is already wrapped at the adapter layer (Phase 2 D-18). Double-wrapping causes retry storms. CD-04 inherits Phase 5 CD-04 verbatim. [VERIFIED: CONTEXT.md CD-04; `adapters/real/llm_anthropic.py:102-108`]
- **Adding new Settings fields** for prompt configuration (e.g., `DOCINTEL_REFUSAL_THRESHOLD`). FND-11 single-env-reader rule binds; provider switching reuses `llm_provider` + `llm_real_provider`. Prompt values are module constants in `prompts.py`, not env vars. [VERIFIED: CONTEXT.md "Established Patterns / Single env reader"]
- **Generator owning retrieval AND generation as a single `.answer(query)` seam.** Collapses Phase 5 `.search()` seam used by Phase 10 (separate retrieval signal) and Phase 11 (ablation swaps). [VERIFIED: CONTEXT.md deferred-ideas]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured-output deserialization from LLM response | Custom JSON parser with regex fallback | Anthropic `tools=[{strict: true}]` + `tool_choice` OR OpenAI `response_format={"type": "json_schema", "strict": true, ...}` | SDKs do schema-constrained generation natively; output is guaranteed valid JSON matching the schema. Hand-rolling reintroduces the heuristic-regex failure mode Phase 6 is fixing. [CITED: openai.com Structured Outputs blog; platform.claude.com structured-outputs] |
| Citation extraction regex | Custom Python parser walking `ast.Constant` or token-by-token | Existing `_CHUNK_RE = re.compile(r"\[([^\]]+)\]")` from `adapters/stub/llm.py:31` (Phase 2 D-16), MOVED to `docintel_generate.parse._CHUNK_RE` per D-12 | Single regex across stub + real + Phase 7 Citation parser. Single source of truth eliminates two-parser drift. [VERIFIED: `adapters/stub/llm.py:31`] |
| Prompt versioning system | Database table, file-watcher with rehash | Module-import-time `hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]` with `Final[str]` constants | Standard library; deterministic; no runtime cost per query; mypy-strict verifiable. Industry standard (Braintrust, LangSmith, LaunchDarkly). [CITED: braintrust.dev/articles/what-is-prompt-versioning] |
| Per-query telemetry collection | Custom JSON-line emitter, OpenTelemetry span builder | `structlog.stdlib.get_logger(__name__).info("generator_completed", **fields)` | `configure_logging` (Phase 1) already wires `merge_contextvars` + JSON renderer; Phase 12 binds `trace_id` upstream and Phase 6's log line gains it automatically with NO retrofit. [VERIFIED: `docintel_core/log.py`; CONTEXT.md D-16] |
| Refusal-detection heuristic | Custom NLI model, embedding cosine | `text.startswith(REFUSAL_TEXT_SENTINEL)` (substring match against `REFUSAL_PROMPT` body) | Sentinel string is locked + grep-detectable; refusal is structural (we instruct the LLM to emit it verbatim). Phase 9 MET-03 measures the rate. [VERIFIED: CONTEXT.md D-11 + D-13 step 5] |
| Workspace package discovery | Custom hatchling build-target enumeration | `packages/*` glob in workspace pyproject (already wired by Phase 1 FND-01) | Auto-picks up `docintel-generate/`; matches Phase 3 / 4 / 5 precedent verbatim. [VERIFIED: `packages/docintel-retrieve/pyproject.toml:1-17`] |
| LLM retry / backoff logic | Custom retry-loop with exponential backoff | Already-wrapped `bundle.llm.complete()` via tenacity at adapter layer (Phase 2 D-18) | One wrap site per SDK boundary. Phase 6 adds NONE. CI grep gate `scripts/check_adapter_wraps.sh` continues to enforce. [VERIFIED: `adapters/real/llm_anthropic.py:102-108`] |
| Chunk-text-to-prompt formatting DSL | Jinja2 / Mako template | Plain Python f-strings + `"\n".join(lines)` per `_format_user_prompt` example above | D-14 format is fixed (4-field metadata header + raw chunk.text + `---` separator). One small method is simpler than a template engine. [VERIFIED: CONTEXT.md D-14] |
| Cross-family judge selection | Custom factory with provider-detection logic | Existing Phase 2 D-04 `CrossFamilyJudge` + `Settings.llm_real_provider` complement-selection in `make_adapters(cfg)` | Already shipped; Phase 6 D-09 preserves it verbatim and only changes the prompt + parser. [VERIFIED: `adapters/factory.py:91-102`] |
| Test fixture for grep-gate negative case | Custom mock-file-system | Existing pattern in `tests/test_index_wraps_gate.py` — invoke `bash scripts/check_index_wraps.sh tests/fixtures/missing_tenacity` and assert exit 1 | Mirrors three existing wrap-gate test patterns; planner reuses the fixture-dir-then-invoke approach. [VERIFIED: `tests/test_index_wraps_gate.py`; `tests/fixtures/` directory] |

**Key insight:** Phase 6 is composition-heavy and net-new-logic-light. Almost everything Phase 6 needs already exists in some form: the LLM call surface is shipped, the retrieval seam is shipped, the citation regex is shipped, the cross-family judge wiring is shipped. Phase 6's invariant-bearing work is **(a)** the new `prompts.py` module with locked structure + hashes, **(b)** the `Generator` orchestrator that composes existing parts, **(c)** the migration of the placeholder judge prompt + parser, and **(d)** the new CI grep gate. Resist the temptation to redesign upstream contracts.

## Runtime State Inventory

*N/A for greenfield Phase 6 — no rename / refactor / migration is being performed. The phase ADDS a new package, a new factory function, a new Pydantic model, a new bash script, a new CI step, and FIVE doc-path updates (CLAUDE.md / config.json / REQUIREMENTS.md / ROADMAP.md / PROJECT.md). It MODIFIES two existing files: `adapters/real/judge.py` (D-09 prompt + parser migration) and `adapters/stub/llm.py` (D-12 sentinel value + `_CHUNK_RE` re-import). No stored runtime state, no live service config, no OS-registered state, no secrets/env vars, no build artifacts to migrate.* [VERIFIED: CONTEXT.md `<domain>` boundary]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `anthropic` SDK | `AnthropicAdapter` real-mode synthesis + judge | ✓ | `0.101.0` | — (already pinned in `docintel-core`) |
| `openai` SDK | `OpenAIAdapter` real-mode synthesis + judge | ✓ | `2.36.0` | — (already pinned in `docintel-core`) |
| `pydantic` v2 | `GenerationResult` model | ✓ | `2.13.3` | — |
| `tenacity` | Inherited wraps; NOT used directly in Phase 6 | ✓ | `9.1.4` | — |
| `structlog` | Telemetry log lines | ✓ | `25.5.0` | — |
| Python `hashlib` (stdlib) | Prompt versioning | ✓ | 3.11 | — |
| `bash` | CI grep gate script | ✓ | GitHub Actions ubuntu-latest default | — |
| `grep -E` extended regex | CI grep gate | ✓ | GNU grep on ubuntu-latest | — |
| `sed -n "${lineno}p"` for noqa check | CI grep gate (planner refines) | ✓ | POSIX sed | — |
| `uv` 0.11.8 | Workspace package management + `uv.lock` regen | ✓ | already pinned | — |
| `pytest` | Test scaffolds | ✓ | (workspace) | — |
| `hatchling` | Build backend for new package | ✓ | (workspace) | — |
| Real-mode API keys (`DOCINTEL_ANTHROPIC_API_KEY`, `DOCINTEL_OPENAI_API_KEY`) | `@pytest.mark.real` end-to-end test on hero question | Available only via `workflow_dispatch` | — | Stub-mode CI works without keys (lazy SDK init, commit `9ec4d36` Phase 5) |

**Missing dependencies with no fallback:** None — Phase 6 is composition + new-module work over existing pinned deps. The real-mode hero-question test is gated by `workflow_dispatch` per Phase 4 D-20 + Phase 5 D-15 precedent, exactly like the existing `real-index-build` job — no new infrastructure required.

**Missing dependencies with fallback:** None.

[VERIFIED: `docintel-core/pyproject.toml` lines 11-16; PyPI metadata for anthropic/openai; `.github/workflows/ci.yml` lines 244-319]

## Common Pitfalls

### Pitfall 1: SDK structured-output API drift between pinned version and live docs

**What goes wrong:** Live Anthropic docs at platform.claude.com show two paths for structured output — newer `output_config={"format": {"type": "json_schema", ...}}` and older `tools=[{strict: true}]` + `tool_choice`. The pinned 0.101.0 supports both, but `output_config` may have edge-case differences across 0.95 → 0.102 series. OpenAI docs similarly show both `response_format` AND `.beta.chat.completions.parse()`; the `.beta.*` namespace has had documented instability (issues #1733, #1763 in openai-python).

**Why it happens:** Phase 2 pinned SDKs in May 2026; structured-output features are stable but actively evolving; the prompt-engineering surface (system prompt + structured constraint together) ships in two flavors per provider.

**How to avoid:** Use the OLDER + MORE-STABLE path on both providers: Anthropic `tools=[{strict: true}]` + `tool_choice={"type": "tool", "name": "submit_verdict"}`; OpenAI `response_format={"type": "json_schema", "json_schema": {strict: true, schema}}`. Plan tests against these specifically. Defer migration to `output_config` / `.beta.*.parse()` until Phase 11 ablation work if/when those become primary.

**Warning signs:** Anthropic `block.input` is `None` or has unexpected schema; OpenAI `response.choices[0].message.content` is `None` instead of a JSON string; `JudgeVerdict(**payload)` raises `pydantic.ValidationError`.

[VERIFIED: github.com/openai/openai-python/issues/1733 + #1763; platform.claude.com/docs/en/build-with-claude/structured-outputs notes "Migrating from beta? The output_format parameter has moved to output_config.format"]

### Pitfall 2: Prompt-locality grep false positives on legitimate strings

**What goes wrong:** The grep gate fires on a legitimately-short string constant that happens to contain "you are" or "cite" — e.g., a docstring quoting the rule, a test fixture, an exception message. CI fails on a green PR.

**Why it happens:** Phrase-based pattern matching has inherent false-positive risk; the 80-char minimum length helps but isn't perfect; some legitimate strings will trip the pattern.

**How to avoid:** D-05 provides two escape valves: **(a)** path allowlist (`tests/**`, `conftest.py`, `**/test_*.py`, the canonical `prompts.py` + `parse.py`, and the existing stub `adapters/stub/llm.py`). **(b)** per-line `# noqa: prompt-locality` escape hatch. The grep script must check `sed -n "${lineno}p" "$file" | grep -q 'noqa: prompt-locality'` BEFORE reporting a hit. Plan must include a deliberate false-positive test fixture and assert it's silenced by the noqa.

**Warning signs:** First post-Wave-4 PR fails the new gate; phrase pattern matches a docstring or test message.

[VERIFIED: CONTEXT.md D-05; analog in `# noqa: E501` / `# type: ignore` patterns across the codebase]

### Pitfall 3: Hash drift from whitespace reformatting

**What goes wrong:** A future contributor (black, autoformatter) reformats `prompts.py` — adjusts indentation, joins long strings, normalises trailing whitespace. The literal `SYNTHESIS_PROMPT` string changes; `_SYNTHESIS_HASH` and `PROMPT_VERSION_HASH` drift. Every committed eval report after that point references a different `prompt_version_hash` from every report before, breaking bisection.

**Why it happens:** SHA256 is byte-exact; whitespace, encoding, or line-ending changes propagate. `black` typically leaves triple-quoted strings alone, but `ruff format` or human edits can shift contents.

**How to avoid:** **(a)** Document the rule in `prompts.py` module docstring: "The SHA256[:12] hash of each prompt body is byte-exact — DO NOT modify whitespace, encoding, or line endings without bumping the per-prompt hash intentionally. CI compares hash against the canonical value." **(b)** Optional defense: GEN-02 test scaffold (Wave 0) asserts `PROMPT_VERSION_HASH == "<canonical-hex>"` — but the canonical value can only be computed AFTER the prompts are written (Wave 1). Plan needs to thread this carefully: Wave 0 test uses `monkeypatch` to verify hash changes when SYNTHESIS_PROMPT is mutated; Wave 4 test pins the actual hash value. **(c)** Add a comment near the hashes: `# DO NOT reformat — see Pitfall 3`.

**Warning signs:** Two PRs in a row that touch `prompts.py` produce different `PROMPT_VERSION_HASH` values in eval reports even though no semantic change was intended.

[VERIFIED: CONTEXT.md D-08; analogous concern documented in Braintrust prompt-versioning guide]

### Pitfall 4: Context-window overflow from K=5 chunks + system + question

**What goes wrong:** A specific chunk hits the upper end of the 500-token cap (Phase 3 D-11); the synthesis prompt template + chunk header + question pushes total prompt tokens past the model's effective context window. Claude Sonnet 4.6 has 200K context and GPT-4o has 128K, so this is unlikely — but Phase 11 may eventually sweep K (number of retrieved chunks), and at K=20 the budget gets tight on smaller models.

**Why it happens:** Token budget is the sum of (5 × 500 chunks ≈ 2500) + (~400 system) + (~200 context-block scaffolding) + (~100 question) ≈ 3200 — well under 200K. Safe for v1. Pitfall is structural for v2 / Phase 11.

**How to avoid:** **(a)** CD-06 requires the planner to log actual `prompt_tokens` from the first hero-question real-mode run and assert < 8K. **(b)** Add a Wave 2 test `test_generator_prompt_token_budget` that runs the stub against a fixture of K=5 max-size chunks (500 tokens each), checks `completion.usage.prompt_tokens` is reasonable (planner picks threshold). **(c)** Document in `generator.py` module docstring that K=20 + max-size chunks may need a context-budget guard.

**Warning signs:** Hero-question real-mode test fails with `BadRequestError` mentioning context length; Anthropic returns truncation flag; OpenAI returns `length` finish_reason.

[VERIFIED: CONTEXT.md CD-06; HuggingFace BGE-small-en-v1.5 token limits; claude.com token-counting docs]

### Pitfall 5: Stub `_STUB_REFUSAL` value drift between Phase 2 location and Phase 6 source-of-truth

**What goes wrong:** Phase 2 D-16 placed `_STUB_REFUSAL = "[STUB REFUSAL] No evidence found in retrieved context."` in `adapters/stub/llm.py`. Phase 6 D-11 + D-12 update the value to `"I cannot answer this question from the retrieved 10-K excerpts."` (matching `REFUSAL_PROMPT`). If the update gets missed in Wave 3, stub tests + real tests have different sentinel strings and Phase 9 faithfulness tests behave inconsistently across modes.

**Why it happens:** The constant lives in `adapters/stub/llm.py` (allowlist exception per D-05), but the canonical source of truth is `docintel_generate.prompts.REFUSAL_PROMPT`. Two physical locations for a string that must be byte-identical.

**How to avoid:** **(a)** Wave 3 plan explicitly imports the sentinel: `from docintel_generate.prompts import REFUSAL_PROMPT as _STUB_REFUSAL  # D-12: stub mirrors generate package` — one upward-stack import per D-12 (stub → generate is acceptable; generator never imports stub). **(b)** Wave 0 / Wave 3 test asserts `from docintel_core.adapters.stub.llm import _STUB_REFUSAL; from docintel_generate.prompts import REFUSAL_PROMPT; assert _STUB_REFUSAL == REFUSAL_PROMPT`. **(c)** D-13 step 5 (`text.startswith(REFUSAL_TEXT_SENTINEL)`) is grep-friendly — any drift in sentinel value will fail the `test_generator_refusal_stub_emits_sentinel` test.

**Warning signs:** Stub-mode test passes; real-mode test passes; eval shows divergent refusal rates between modes; Phase 7's Citation parser handles the two strings differently.

[VERIFIED: CONTEXT.md D-12; `adapters/stub/llm.py:23` current value]

### Pitfall 6: Structured-output deserialization failure cascading into tenacity retry storm

**What goes wrong:** Anthropic's `tools=[{strict: true}]` is supposed to guarantee schema compliance, but real-world reports show edge cases (especially with `extended_thinking`) where the model emits a tool_use block with empty `.input` or where `block.input` doesn't fully match the schema. `JudgeVerdict(**payload)` raises `pydantic.ValidationError`. If this error bubbles through `CrossFamilyJudge.judge()` and the caller catches and retries, AND the underlying adapter is also tenacity-wrapped, we get nested retry-storm: tenacity at the adapter retries 5 times on `RateLimitError`, the judge's caller retries the whole flow N times, total = 5×N calls per failure.

**Why it happens:** Two retry layers (Phase 2 D-18 + caller's retry intent) without explicit no-double-wrap rule. Phase 9 may add retry around `bundle.judge.judge(...)` without realizing the inner LLM is already wrapped.

**How to avoid:** **(a)** Document explicitly in `judge.py` module docstring (Phase 2 already does — line 7-11): "The underlying LLMClient.complete() is already tenacity-wrapped. This module does NOT add a second @retry layer." **(b)** Wave 3 plan task: on `pydantic.ValidationError` from the structured-output deserialization, log the failure (`judge_structured_output_invalid` structlog warning) and return a sentinel `JudgeVerdict(score=0.0, passed=False, reasoning="<deserialization failed>", unsupported_claims=[])` — NEVER raise. Failures are measurements (Phase 9 sees them as zero-score judgments), not retry triggers. **(c)** No retry decorator on the judge function itself.

**Warning signs:** Phase 9 eval reports show one or two judgments per run with `score=0.0` + `reasoning="<deserialization failed>"` — that's the canary firing; investigate model behavior, not infrastructure.

[VERIFIED: CONTEXT.md CD-04 + D-09 + Phase 2 D-18; github.com/anthropics/anthropic-sdk-python/issues/1204 (structured-output bugs with thinking + tool use)]

### Pitfall 7: Hallucinated chunk_ids slip into `cited_chunk_ids`

**What goes wrong:** Without validation, the LLM emits `[NVDA-FY2024-Item-7-999]` in its response — a plausible-looking chunk_id that doesn't exist in the retrieved set. `_CHUNK_RE.findall()` extracts it; the generator hands it to Phase 7 Citation which fails to find it in the chunk map; Phase 9 MET-04 measures citation accuracy below 100%.

**Why it happens:** LLMs occasionally pattern-match the chunk_id format and synthesize new ones. This is the documented citation-hallucination failure mode (FACTUM paper, 2026; "Citation Grounding" Medium article).

**How to avoid:** D-13 step 4 explicitly designs the validation: every parsed chunk_id is checked against `{c.chunk_id for c in retrieved_chunks}`; misses get a `generator_hallucinated_chunk_id` structlog warning + are DROPPED from `cited_chunk_ids`. The response `text` is NOT modified — Phase 9 MET-04 measures the hallucination rate as a fraction. Wave 2 test fixture: stub the LLM to return a response with a deliberate hallucinated ID, assert (a) the ID is dropped from `cited_chunk_ids`, (b) the structlog warning fires, (c) the `text` is unchanged.

**Warning signs:** `generator_completed` structlog lines show `n_chunks_cited < len(raw extracted IDs)`; eval reports show citation-accuracy bands below 100% on the hero question.

[CITED: arxiv.org/pdf/2601.05866 (FACTUM citation-hallucination paper); medium.com/@Nexumo "RAG Grounding: 11 Tests"; CONTEXT.md D-13 step 4 + CD-07]

### Pitfall 8: Judge prompt migration changes `PROMPT_VERSION_HASH` mid-Phase

**What goes wrong:** Phase 6 ships in 5 waves. Wave 1 writes `SYNTHESIS_PROMPT` + `REFUSAL_PROMPT` + a placeholder `JUDGE_PROMPT`. Wave 3 migrates the actual judge prompt body from `adapters/real/judge.py` and changes `JUDGE_PROMPT`. Between Wave 1 and Wave 3, `PROMPT_VERSION_HASH` changes — and any eval reports written between those waves (unlikely but possible if Phase 8/9/10 parallel work lands) carry a stale hash.

**Why it happens:** Wave structure puts judge migration in Wave 3, but Phase 9/10 are pending — their first reports come after Phase 6 completes. As long as Phase 6 lands all 5 waves before Phase 9 starts emitting reports, this is fine.

**How to avoid:** **(a)** Sequencing: Phase 9 depends on Phase 7 + Phase 8 (per ROADMAP.md); Phase 7 depends on Phase 6; so Phase 9 cannot land reports until after Phase 6 is fully merged. **(b)** Decision-Coverage Audit (Wave 4) explicitly verifies the judge migration is complete and the canonical `PROMPT_VERSION_HASH` is stable. **(c)** Document explicitly in the Phase 6 phase-gate audit: "Pre-Wave-3 `JUDGE_PROMPT` is a placeholder; Wave 3 migrates the real text from `adapters/real/judge.py`. The committed `PROMPT_VERSION_HASH` only stabilizes after Wave 3 lands."

**Warning signs:** A `data/eval/reports/<ts>/` directory committed between Wave 1 and Wave 3 with a stale `prompt_version_hash` — should not happen given sequencing.

[VERIFIED: ROADMAP.md sequencing; CONTEXT.md `<specifics>` "The judge migration (D-09) happens at Phase 6 specifically because of the manifest hash"]

### Pitfall 9: One-package-too-many import cycle when `adapters/stub/llm.py` imports from `docintel-generate`

**What goes wrong:** Phase 6 D-12 says the stub adapter imports `REFUSAL_PROMPT` (or a renamed `REFUSAL_PROMPT_SENTINEL`) from `docintel_generate.prompts`. But `docintel-core` is a workspace dep of `docintel-generate`, NOT the reverse. If `adapters/stub/llm.py` imports from `docintel-generate`, we create a CYCLE: `docintel-core` → `docintel-generate` → (transitive) `docintel-core`.

**Why it happens:** The natural import-direction convention is "downstream phase imports from upstream" — `docintel-generate` imports from `docintel-core`. The stub-adapter import inverts this.

**How to avoid:** **(a)** D-12 explicitly acknowledges this as an exception: "One stub import is allowed to cross into `docintel-generate`". **(b)** The Phase 6 plan should verify the cycle is acceptable at the *runtime import* level: `docintel-core/adapters/stub/llm.py` imports `docintel_generate.prompts.REFUSAL_PROMPT` at module load. As long as `docintel-generate/pyproject.toml` does NOT pin `docintel-core` AT IMPORT TIME for the stub-relevant code path (it does pin core for everything else, but the stub-adapter import only fires when `make_adapters(cfg)` returns a stub), this is fine. **(c)** Alternative: move `REFUSAL_PROMPT_SENTINEL` to `docintel_core.types` as a module constant (single-string, not a prompt body), and have BOTH `docintel-generate.prompts` and `adapters/stub/llm.py` import it from core. This avoids the cycle entirely at the cost of one extra constant in core.

**Recommendation:** Use the alternative (move sentinel to `docintel_core.types`) — cleaner import graph, no exception to document, matches the existing CD-02 pattern (shared contracts live in core). The `REFUSAL_PROMPT` in `docintel_generate.prompts` then becomes `REFUSAL_PROMPT = REFUSAL_TEXT_SENTINEL` (or just the same string body) — but the canonical 50-character constant lives in core.

**Warning signs:** `python -c "import docintel_core.adapters.stub.llm"` fails with `ImportError` or `ModuleNotFoundError`; pytest collection fails on `test_stub_llm.py`.

[VERIFIED: workspace package layout in `packages/`; CONTEXT.md D-12 "stub → generate is upward-stack, acceptable" — but the alternative is cleaner. Flagged for planner consideration.]

### Pitfall 10: Hero question (multi-hop comparative) under-performs the single SYNTHESIS_PROMPT

**What goes wrong:** The locked hero question is "Which of these companies grew R&D while margins shrank in 2023?" — a multi-hop comparative across multiple 10-Ks. The single `SYNTHESIS_PROMPT` is designed to handle both single-doc factual AND multi-hop comparative under one template (D-07 + CD-01 + `<specifics>` "single-prompt-handles-both ... is load-bearing for the demo"). If the prompt phrasing favors single-doc factual, the comparative case under-performs in Phase 9 eval; if it favors comparative, single-doc precision suffers.

**Why it happens:** RAG synthesis prompts are typically tuned for one question type; tuning for both requires careful instruction structure (e.g., "For comparative questions, explicitly enumerate each compared entity's grounded evidence from `<context>` before reaching a conclusion").

**How to avoid:** **(a)** CD-01 leaves exact phrasing to planner — Wave 1 plan should explicitly include both factual AND comparative example questions in the system prompt's example block (not the locked `[chunk_id]` example, but a more general "for multi-hop questions, structure the answer as: <Entity 1 evidence> ... <Entity 2 evidence> ... <comparison>"). **(b)** Wave 2 stub test should include a fixture for a comparative-style question; verify the stub's `[STUB ANSWER citing ...]` template doesn't break the comparative pattern. **(c)** Phase 8 ground-truth set must include ≥3 comparative questions for Phase 9 MET-03 to measure the comparative case. **(d)** Deferred idea (per CONTEXT.md): if Phase 9 shows the single prompt underperforms on comparatives, retrofit `Generator.generate(query, k, prompt_template=SYNTHESIS_PROMPT)` and add `COMPARATIVE_PROMPT` — the seam is documented in deferred-ideas.

**Warning signs:** Phase 9 MET-03 (faithfulness) bucketed by question-type shows substantially lower comparative vs factual; hero-question demo answers feel templated rather than reasoned.

[VERIFIED: CONTEXT.md `<specifics>` line; deferred-ideas "Per-question-type prompt routing"; ROADMAP.md hero question is multi-hop comparative]

## Code Examples

### Example 1: Module-import-time prompt + hash + sentinel

```python
# Source: packages/docintel-generate/src/docintel_generate/prompts.py
# Reference: CONTEXT.md D-07, D-08, D-10, D-11

from __future__ import annotations

import hashlib
from typing import Final


def _h(s: str) -> str:
    """SHA256 truncated to 12 hex chars — manifest-friendly."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


# DO NOT reformat the body of these prompts — the SHA256[:12] hash is byte-exact.
# Whitespace changes drift the hash. See Pitfall 3.

SYNTHESIS_PROMPT: Final[str] = """\
You are answering a question using ONLY the retrieved 10-K excerpts in the <context> block below.

Rules:
1. Every factual sentence in your answer MUST end with one or more [chunk_id] citations
   referencing the chunks provided. Do not invent chunk_ids; only cite from <context>.
2. If a claim cannot be grounded in the provided context, omit the claim.
3. If the context does not contain enough information to answer the question, emit
   verbatim and ONLY this sentence: "I cannot answer this question from the retrieved
   10-K excerpts."
4. For comparative questions across companies, structure the answer to enumerate each
   compared entity's grounded evidence before reaching a comparison conclusion.

Example:
Apple highlighted supplier concentration in China and Taiwan as a key risk in its
FY2024 10-K [AAPL-FY2024-Item-1A-018]. NVIDIA disclosed revenue concentration with a
single hyperscaler customer [NVDA-FY2024-Item-7-042].
"""

REFUSAL_PROMPT: Final[str] = (
    "I cannot answer this question from the retrieved 10-K excerpts."
)

JUDGE_PROMPT: Final[str] = """\
You are a strict citation-faithfulness judge.

Evaluate whether each claim in the prediction is supported by at least one of the
reference passages provided. Emit a structured verdict via the submit_verdict tool.

Scoring rubric:
- score in [0.0, 1.0] = fraction of prediction claims grounded in the reference set.
- passed = (score >= 0.5).
- reasoning = concise human-readable explanation of how you arrived at the score.
- unsupported_claims = list of prediction claims you could not ground in the references.

Judge ONLY the prediction-vs-reference structural match. Do not infer claims outside
the reference set. Do not penalise the prediction for omitting claims that ARE
supported by references but were not stated.
"""

# Per-prompt + combined hashes, computed at module import. mypy --strict verifies Final[str].
_SYNTHESIS_HASH: Final[str] = _h(SYNTHESIS_PROMPT)
_REFUSAL_HASH: Final[str] = _h(REFUSAL_PROMPT)
_JUDGE_HASH: Final[str] = _h(JUDGE_PROMPT)
PROMPT_VERSION_HASH: Final[str] = _h(_SYNTHESIS_HASH + _REFUSAL_HASH + _JUDGE_HASH)


def build_judge_user_prompt(prediction: str, reference: list[str], rubric: str = "") -> str:
    """Build the user-side prompt for the judge LLM call (D-09 migration helper)."""
    ref_text = "\n".join(f"[{i}] {r}" for i, r in enumerate(reference))
    rubric_section = f"\nAdditional rubric: {rubric}" if rubric else ""
    return (
        f"Prediction to evaluate:\n{prediction}\n\n"
        f"Reference passages:\n{ref_text}"
        f"{rubric_section}"
    )
```

[VERIFIED: matches D-07 + D-08 + D-10 + D-11 verbatim; planner refines exact wording per CD-01 + CD-02]

### Example 2: `GenerationResult` Pydantic model in `docintel_core.types`

```python
# Source: packages/docintel-core/src/docintel_core/types.py (ADDITION)
# Reference: CONTEXT.md D-17; matches RetrievedChunk precedent (Phase 5 CD-02)

from pydantic import BaseModel, ConfigDict

# CompletionResponse + RetrievedChunk are existing imports — already in this module.


class GenerationResult(BaseModel):
    """Phase 6 generation output. Phase 7 Answer wraps this into the application schema.

    D-17: frozen=True so downstream callers cannot mutate (defense-in-depth against
    Phase 7 schema-shape mistakes that would otherwise silently corrupt shared lists).
    extra='forbid' so a tampered or partial construction raises pydantic.ValidationError
    immediately at the boundary.

    Home: docintel_core.types — matches RetrievedChunk precedent (Phase 5 CD-02). Phase 7
    Citation imports this contract without depending on docintel-generate.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # The raw LLM response text. On hard refusal (zero chunks retrieved), this equals
    # REFUSAL_TEXT_SENTINEL verbatim. On LLM-driven refusal, the LLM emitted the
    # sentinel as the first part of its response.
    text: str

    # De-duplicated, validated subset of {c.chunk_id for c in retrieved_chunks}.
    # Hallucinated chunk_ids (LLM invented an ID) are DROPPED with a structlog
    # generator_hallucinated_chunk_id warning. Phase 9 MET-04 measures the drop rate.
    cited_chunk_ids: list[str]

    # True iff hard zero-chunk path OR text.startswith(REFUSAL_TEXT_SENTINEL).
    # Phase 9 MET-03 reads this for refusal-rate metrics; the demo's out-of-corpus
    # question demo relies on the LLM-driven path triggering this.
    refused: bool

    # The K chunks Phase 5's Retriever returned. Carried for Phase 7 (Citation
    # quote-span enrichment), Phase 13 UI (hover-to-show chunk text), and Phase 10
    # eval reports (per-chunk citation accuracy breakdown).
    retrieved_chunks: list[RetrievedChunk]

    # The LLM's native shape; carries usage / cost_usd / latency_ms / model.
    # None on hard refusal (the LLM was not called).
    completion: CompletionResponse | None

    # The combined PROMPT_VERSION_HASH at generation time. Phase 10 EVAL-02 manifest
    # reads this; Phase 11 ablation reports bin results by this hash.
    prompt_version_hash: str
```

[VERIFIED: matches D-17 verbatim; structure parallels existing `RetrievedChunk` at `types.py:148-191`]

### Example 3: `make_generator` 4th sibling factory

```python
# Source: packages/docintel-core/src/docintel_core/adapters/factory.py (ADDITION)
# Reference: CONTEXT.md D-03; mirrors make_retriever (Phase 5 D-04) verbatim

def make_generator(cfg: Settings) -> Generator:
    """Construct and return a Generator composed of AdapterBundle + Retriever.

    Phase 6 D-03: 4th sibling factory alongside make_adapters / make_index_stores /
    make_retriever. Lives in docintel_core.adapters.factory (NOT in docintel-generate)
    so the import direction matches every prior phase: docintel-generate imports from
    docintel-core, never the reverse.

    Lazy-import discipline (D-12 Phase 2 + Pattern S5 Phase 5): `from
    docintel_generate.generator import Generator` lives INSIDE the function body so
    `import docintel_core.adapters.factory` stays cheap.

    CD-03 (recommended): eager-load. Generator instantiation is cheap (just stashes
    bundle + retriever); first-call cost is the underlying LLM SDK init which is
    already lazy in AnthropicAdapter._get_client (commit 9ec4d36).

    CD-05: NO factory-level cache. Phase 13 FastAPI lru_caches at the dependency
    layer; Phase 10 eval harness constructs once per run.

    Args:
        cfg: Settings instance with llm_provider set.

    Returns:
        Generator ready to call .generate(query, k). The instance holds AdapterBundle
        + Retriever references; subsequent .generate calls do not re-trigger factory
        dispatch.
    """
    # Lazy import — keeps `import docintel_core.adapters.factory` cheap.
    from docintel_generate.generator import Generator

    bundle = make_adapters(cfg)
    retriever = make_retriever(cfg)
    return Generator(bundle=bundle, retriever=retriever)
```

(Also add `from docintel_generate.generator import Generator` under the existing `TYPE_CHECKING` block for mypy resolution of the `-> Generator` return annotation, mirroring the Phase 5 `Retriever` pattern at `factory.py:50`.)

[VERIFIED: matches D-03 verbatim; mirrors `make_retriever` at `factory.py:153-205`]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Heuristic regex parsing of LLM JSON-like response | Provider-native structured output (Anthropic `tools=[{strict: true}]`, OpenAI `response_format={"type": "json_schema", "strict": true}`) | OpenAI: 1.40 (Aug 2024). Anthropic: 0.85 stable; `output_config` newer alternative. | Phase 6 D-09 migrates from Phase 2 placeholder. Eliminates `_SCORE_PATTERN` regex failure modes; output guaranteed valid JSON matching `JudgeVerdict` shape. |
| JSON-templated prompts (`{"context": [...]}`) | XML-tagged prompts (`<context>...<chunk_id: X>...</context>`) | Anthropic prompt-engineering best practices (stable since Claude 2 era) | Phase 6 D-14 uses `<context>` tags. Better token efficiency, better adherence on both Claude and GPT-4-class. |
| Refusal via score threshold | Dual-layer: hard zero-chunk floor + LLM-driven canonical sentinel | RAG-grounding best practices 2024-2026 (FACTUM paper, RAG-evaluation guides) | Phase 6 D-10 + D-11. Provider-agnostic (no calibrated thresholds); separately measurable in Phase 9 MET-03. |
| Re-prompting LLM on missing citations | Log + drop hallucinated IDs (measure, don't enforce) | Citation-grounded code-comprehension paper (arxiv 2512.12117, late 2025); FACTUM (arxiv 2601.05866) | Phase 6 D-13 + CD-07. Preserves Phase 9 MET-04 measurement signal; avoids cost/latency doubling. |
| Free-form prompt text in code | Versioned `prompts.py` module with SHA256[:12] hashes + manifest header propagation | Industry standard 2024-2026 (Braintrust, LangSmith, LaunchDarkly, Antigravity) | Phase 6 D-08 + GEN-02 + EVAL-02 manifest header. Deterministic; bisectable; CI-gateable. |
| Single-provider LLM with provider-native judging (self-judge) | Cross-family judging (Anthropic generator → OpenAI judge, or vice versa) | LLM-as-judge bias research 2024-2026 (arxiv 2604.23178) | Phase 2 D-04 shipped this; Phase 6 D-09 preserves the wiring verbatim and only migrates the prompt + parser. |

**Deprecated/outdated:**

- **OpenAI `client.completions.create(...)` (text-completions endpoint).** Deprecated in favor of `chat.completions.create` since SDK 0.x → 1.x (2023). Phase 2 already uses `chat.completions.create` — no Phase 6 action.
- **Anthropic non-`messages` API.** The pre-`messages.create` endpoint is deprecated. Phase 2 already uses `client.messages.create` — no Phase 6 action.
- **Inline string-literal prompts in business logic.** The GEN-01 grep gate's whole purpose is to deprecate this pattern.
- **`_SCORE_PATTERN = re.compile(r"score\s*:\s*([0-9]*\.?[0-9]+)")`** placeholder in `adapters/real/judge.py:52`. Phase 6 D-09 REMOVES this regex.

[VERIFIED: github.com/anthropics/anthropic-sdk-python/CHANGELOG.md; github.com/openai/openai-python/CHANGELOG.md; arxiv.org/pdf/2604.23178; arxiv.org/pdf/2601.05866]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `output_config` Anthropic API (newer JSON Outputs) is stable in `anthropic==0.101.0`. | Standard Stack / Alternatives Considered | LOW. We're recommending the `tools=[{strict: true}]` path, which is independently confirmed stable since 0.85. If `output_config` is preferred in a future revision, planner can switch — but it's NOT the recommended Phase 6 path. |
| A2 | OpenAI `response_format={"type": "json_schema", "json_schema": {strict: true, ...}}` works in `openai==2.36.0` against `gpt-4o` (the default model in `OpenAIAdapter`). | Pattern 3 / Standard Stack | LOW. Verified against OpenAI changelog + openai-python helpers.md; `gpt-4o-2024-08-06` and later snapshots officially support `json_schema` strict mode (the default model name `gpt-4o` resolves to a recent snapshot at request time). Planner should pin the snapshot version (e.g., `gpt-4o-2024-08-06`) for reproducibility in Wave 3 if Phase 9 eval reports show drift. |
| A3 | The single `SYNTHESIS_PROMPT` covers both single-doc factual AND multi-hop comparative under one template adequately. | Pitfall 10 | MEDIUM. Tracked as deferred idea ("Per-question-type prompt routing"). Phase 9 MET-03 bucketed by question-type measures this; if comparative under-performs by a meaningful margin, the retrofit seam is documented. |
| A4 | Module-import-time hash computation is acceptable (no first-call latency, no race conditions). | Pattern 2 / Pitfall 3 | LOW. Standard pattern; `Final[str]` annotation enforces it. No data dependency on runtime state. |
| A5 | The stub `adapters/stub/llm.py` importing from `docintel-generate` (a downstream workspace package) is acceptable. | Pitfall 9 | MEDIUM — recommendation is to MOVE `REFUSAL_TEXT_SENTINEL` to `docintel_core.types` to avoid the cycle entirely. Planner picks during execution. |
| A6 | `_CHUNK_RE = re.compile(r"\[([^\]]+)\]")` is the correct regex for both stub + real + Phase 7 Citation parsing. | Don't Hand-Roll | LOW. Already shipped (Phase 2 D-16); proven across stub-mode pytest runs. The `[^\]]+` non-greedy class excludes literal `]`, so nested brackets `[NVDA-[YYYY]-007]` would still match the outermost bracket-pair — but chunk_ids are flat strings without nested brackets, so this is fine. |
| A7 | Phase 12 `trace_id` binding via `structlog.contextvars.bind_contextvars` will automatically propagate into Phase 6's `generator_completed` log line without any Phase 6 retrofit. | Pattern 1 | LOW. Verified: `configure_logging` (Phase 1) already includes `structlog.contextvars.merge_contextvars` as the FIRST processor; any `bind_contextvars(trace_id=...)` call upstream gets merged into every subsequent log line. |
| A8 | The `JudgeVerdict` JSON schema `{score: number [0,1], passed: bool, reasoning: str, unsupported_claims: list[str]}` is what BOTH SDKs' strict mode supports. | Pattern 3 | LOW. Both providers' strict mode require `additionalProperties: false` + all fields in `required`. Our four-field schema meets both. Nested objects work (verified in openai docs) but we don't need them. |

[All assumptions are tagged for planner / discuss-phase review. None are HIGH-RISK; A3 is the main one to monitor in Phase 9.]

## Open Questions

1. **Should `REFUSAL_TEXT_SENTINEL` live in `docintel_core.types` (cleaner) or stay split between `docintel_generate.prompts.REFUSAL_PROMPT` and `adapters/stub/llm.py._STUB_REFUSAL`?**
   - What we know: CONTEXT.md D-12 allows the stub → generate import. CD-02 precedent suggests core for shared contracts.
   - What's unclear: Whether the planner wants to honor D-12 verbatim or adopt the Pitfall 9 alternative recommendation.
   - Recommendation: Move the sentinel string constant (a 50-character literal, not a prompt body) to `docintel_core.types` as `REFUSAL_TEXT_SENTINEL: Final[str]`. Both `docintel_generate.prompts.REFUSAL_PROMPT` and `adapters/stub/llm.py._STUB_REFUSAL` then import it from core. This eliminates the upward-stack exception, keeps the GEN-01 grep gate clean (the constant in core is a short literal, doesn't match the >80-char phrase pattern), and aligns with CD-02 precedent. Plan decision; doesn't block research.

2. **Which Wave should land the 5 doc-path updates (CLAUDE.md, config.json, REQUIREMENTS, ROADMAP, PROJECT.md)?**
   - What we know: D-02 says "one consolidated doc-update commit in Wave 0 or Wave 5 (planner picks)".
   - What's unclear: Wave 0 is earlier (no risk of forgetting); Wave 5 is later (only commit if Phase 6 actually shipped).
   - Recommendation: Wave 0 (Plan 06-02 alongside the test scaffolds). The doc updates are deterministic — they don't depend on anything Phase 6 builds. Landing them in Wave 0 means the canonical path is correct in the repo from the start, avoiding any "old path" muscle memory during execution.

3. **Should the planner pin `gpt-4o-2024-08-06` as the OpenAI default in Wave 3 OR keep `gpt-4o` (which resolves at request time)?**
   - What we know: Structured outputs `json_schema` strict mode is officially supported on `gpt-4o-2024-08-06` and later snapshots; `gpt-4o` is the floating alias.
   - What's unclear: Whether floating-alias drift matters for Phase 6 (vs Phase 9 eval reproducibility).
   - Recommendation: Keep `gpt-4o` for Phase 6 (planning decision, low risk); revisit in Phase 9 if eval reports show drift. Phase 6's structured-output usage is the judge path; Phase 9 ablation can pin the snapshot if needed. Not a Phase 6 blocker.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (workspace pin) |
| Config file | `pyproject.toml [tool.pytest.ini_options]` (workspace-level) |
| Quick run command | `uv run pytest tests/test_prompt_locality.py tests/test_prompt_version_hash.py tests/test_generator_stub_determinism.py tests/test_generator_refusal.py -ra -q -m "not real"` |
| Full suite command | `uv run pytest -ra -q -m "not real"` (stub-only; matches existing CI) |
| Real-mode hero question | `uv run pytest -m real -ra -q -k "generator and hero"` (workflow_dispatch-only, like `real-index-build`) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GEN-01 | grep gate exit 0 on canonical layout | unit | `uv run pytest tests/test_prompt_locality.py -x` | ❌ Wave 0 |
| GEN-01 | grep gate exit 1 on planted violation (fixture dir) | unit | `uv run pytest tests/test_prompt_locality.py::test_grep_gate_fails_on_violation -x` | ❌ Wave 0 |
| GEN-01 | grep gate respects `# noqa: prompt-locality` escape | unit | `uv run pytest tests/test_prompt_locality.py::test_grep_gate_respects_noqa -x` | ❌ Wave 0 |
| GEN-02 | `PROMPT_VERSION_HASH` is a 12-char hex string | unit | `uv run pytest tests/test_prompt_version_hash.py::test_hash_format -x` | ❌ Wave 0 |
| GEN-02 | hash changes when any prompt body mutated | unit (monkeypatch) | `uv run pytest tests/test_prompt_version_hash.py::test_hash_sensitivity -x` | ❌ Wave 0 |
| GEN-02 | per-prompt hashes are exposed as `_SYNTHESIS_HASH`, `_REFUSAL_HASH`, `_JUDGE_HASH` | unit | `uv run pytest tests/test_prompt_version_hash.py::test_per_prompt_hashes_exposed -x` | ❌ Wave 0 |
| GEN-03 | stub generator returns deterministic `GenerationResult` for identical input | unit | `uv run pytest tests/test_generator_stub_determinism.py::test_determinism -x` | ❌ Wave 0 |
| GEN-03 | `cited_chunk_ids` is subset of `{c.chunk_id for c in retrieved_chunks}` | unit | `uv run pytest tests/test_generator_stub_determinism.py::test_citation_subset -x` | ❌ Wave 0 |
| GEN-03 | hallucinated chunk_ids are dropped with `generator_hallucinated_chunk_id` log | unit | `uv run pytest tests/test_generator_stub_determinism.py::test_hallucinated_ids_dropped -x` | ❌ Wave 0 |
| GEN-04 | empty retrieval → `refused=True`, `text == REFUSAL_TEXT_SENTINEL`, `completion is None` | unit | `uv run pytest tests/test_generator_refusal.py::test_hard_zero_chunk_refusal -x` | ❌ Wave 0 |
| GEN-04 | LLM emits refusal sentinel → `refused=True` even with non-empty retrieval | unit | `uv run pytest tests/test_generator_refusal.py::test_llm_driven_refusal -x` | ❌ Wave 0 |
| GEN-04 | hard-refusal emits `generator_refused_zero_chunks` structlog warning | unit | `uv run pytest tests/test_generator_refusal.py::test_zero_chunks_warning -x` | ❌ Wave 0 |
| D-03 | `make_generator(cfg)` returns `Generator` for stub Settings | unit | `uv run pytest tests/test_make_generator.py::test_factory_stub -x` | ❌ Wave 0 |
| D-03 | lazy-import gate: `import docintel_core.adapters.factory` does NOT load `docintel_generate.generator` | unit | `uv run pytest tests/test_make_generator.py::test_factory_lazy_imports_generator_module -x` | ❌ Wave 0 |
| D-09 | judge structured-output deserializes into `JudgeVerdict` correctly | unit (mocked client) | `uv run pytest tests/test_judge_structured_output.py -x` | ❌ Wave 0 |
| D-09 | judge deserialization failure produces sentinel `JudgeVerdict(score=0.0, passed=False, ...)`, never raises | unit | `uv run pytest tests/test_judge_structured_output.py::test_deserialization_failure_returns_sentinel -x` | ❌ Wave 0 |
| D-14 + hero | end-to-end stub: comparative question across companies returns a non-empty `cited_chunk_ids` covering multiple tickers | integration | `uv run pytest tests/test_generator_search_integration.py::test_hero_comparative_stub -x` | ❌ Wave 0 |
| D-16 | `generator_completed` structlog emits all 14 fields | unit (capture log) | `uv run pytest tests/test_generator_telemetry.py::test_completed_fields -x` | ❌ Wave 0 |
| D-17 | `GenerationResult` is frozen + `extra='forbid'` | unit | `uv run pytest tests/test_generation_result_schema.py -x` | ❌ Wave 0 |
| HERO | real-mode hero question returns non-refused answer with ≥2 tickers cited | integration (real) | `uv run pytest -m real tests/test_generator_real_hero.py -x` | ❌ Wave 0 (xfail until workflow_dispatch run lands) |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_<file>.py -x` (the test scaffold being promoted in that task)
- **Per wave merge:** `uv run pytest -ra -q -m "not real"` (full stub suite)
- **Phase gate:** Full stub suite green + `scripts/check_prompt_locality.sh` exit 0 + `scripts/check_adapter_wraps.sh` exit 0 + Decision-Coverage Audit 27/27 (D-01..D-17 + CD-01..CD-10)

### Wave 0 Gaps

- [ ] `tests/test_prompt_locality.py` — covers GEN-01 (3 cases: green, planted violation, noqa escape)
- [ ] `tests/test_prompt_version_hash.py` — covers GEN-02 (3 cases: format, sensitivity, per-prompt exposure)
- [ ] `tests/test_generator_stub_determinism.py` — covers GEN-03 (3 cases: determinism, citation-subset, hallucination drop)
- [ ] `tests/test_generator_refusal.py` — covers GEN-04 (3 cases: hard refusal, LLM-driven refusal, zero-chunk warning)
- [ ] `tests/test_make_generator.py` — covers D-03 factory + lazy-import gate
- [ ] `tests/test_judge_structured_output.py` — covers D-09 migration (xfail until Wave 3)
- [ ] `tests/test_generator_search_integration.py` — covers D-14 + hero question end-to-end (stub)
- [ ] `tests/test_generator_telemetry.py` — covers D-16 14-field structlog emission
- [ ] `tests/test_generation_result_schema.py` — covers D-17 (frozen + extra=forbid)
- [ ] `tests/test_generator_real_hero.py` — covers hero question real-mode (xfail until workflow_dispatch run, like Phase 5 `test_reranker_canary_real_mode`)
- [ ] `tests/fixtures/prompt_locality_violations/` — fixture dir with planted violation file for `tests/test_prompt_locality.py` negative case
- [ ] `tests/fixtures/prompt_locality_violations_with_noqa/` — fixture dir with a violation that has `# noqa: prompt-locality` (must NOT trip the gate)

*Framework install: not needed — pytest already in workspace pins.*

## Security Domain

> Note: docintel `.planning/config.json` does not have an explicit `security_enforcement` key; treating as enabled per default. Phase 6 is composition over existing pinned + tenacity-wrapped SDKs; security surface is minimal compared to Phase 3 (fetch.py) or Phase 4 (Qdrant). Section kept lean.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface in Phase 6 (no HTTP endpoint); demo is single-user. Phase 13 ADR documents the deliberate decision. |
| V3 Session Management | no | Single-turn Q&A; no sessions. |
| V4 Access Control | no | Same as V2. |
| V5 Input Validation | yes | `query: str` parameter to `Generator.generate()` — passes through to retriever (which already truncates at 64 BGE tokens per Phase 5 D-11) and to the LLM SDK (which handles its own input validation). The `GenerationResult` Pydantic model with `ConfigDict(extra="forbid", frozen=True)` is the defense-in-depth at the boundary. |
| V6 Cryptography | yes | `hashlib.sha256` for prompt versioning — standard library, no custom crypto. NO secret derivation, NO HMAC, NO encryption. The hash is purely for manifest provenance, not security. |
| V7 Error Handling | yes | Structured-output deserialization failures emit `judge_structured_output_invalid` structlog warning + return sentinel `JudgeVerdict` (NOT raise) per Pitfall 6. Hallucinated chunk_ids emit `generator_hallucinated_chunk_id` + drop (NOT raise) per CD-07. Hard zero-chunk refusal emits `generator_refused_zero_chunks` + returns sentinel (NOT raise). All error paths are structured + observable + non-fatal. |
| V8 Data Protection | partial | `DOCINTEL_ANTHROPIC_API_KEY` + `DOCINTEL_OPENAI_API_KEY` already protected via `SecretStr` in Phase 1 Settings + read-once-at-SDK-construction in Phase 2 real adapters. Phase 6 does NOT touch the key handling — uses `bundle.llm.complete()` which is already gated. Prompt bodies are NOT secrets (they live in committed source). |
| V14 Configuration | yes | No new Settings fields (FND-11 preserved). All prompt parameters are module constants in `prompts.py` (compiled into the package). |

### Known Threat Patterns for {Phase 6 stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via user query | Tampering | Phase 5 query truncation at 64 BGE tokens (D-11) limits injection surface. Phase 6 wraps the query in a structured `Question: <query>` block AFTER the `<context>` block, instructing the LLM that the question is a discrete unit. The locked SYNTHESIS_PROMPT instruction "use ONLY the retrieved 10-K excerpts" is the structural mitigation. NOT bulletproof; mitigated to "best effort" for a portfolio artifact (not a production trust boundary). |
| Chunk_id forgery in LLM output | Tampering / Information Disclosure | D-13 step 4 validation: every cited chunk_id must be in `{c.chunk_id for c in retrieved_chunks}`. Forged IDs are dropped + logged. Defense at the boundary. |
| API key leak via log lines or error messages | Information Disclosure | Phase 2 SP-4 / T-02-05 mitigation already binding: `.get_secret_value()` called ONCE in adapter `_get_client()`, never logged. Phase 6's `generator_completed` log line does NOT include any API-key field. |
| Cost-runaway from retry storm | Denial of Service | CD-04 explicitly forbids new tenacity wraps. Phase 2 D-18 wraps the adapter; Pitfall 6 documents the no-double-wrap rule for structured-output deserialization failures. Per-request cost budget visible in `cost_usd` field of `generator_completed`. |
| Context-window-budget overflow | Denial of Service | CD-06 + Pitfall 4: monitor `prompt_tokens` on hero question; document K=20 budget guard for v2. |

[VERIFIED: Phase 2 D-18 tenacity wraps; Phase 5 D-11 query truncation; Phase 1 `SecretStr` pattern; OWASP ASVS V5/V7/V14 standard mappings]

## Sources

### Primary (HIGH confidence)

- [Anthropic SDK CHANGELOG.md](https://github.com/anthropics/anthropic-sdk-python/blob/main/CHANGELOG.md) — Verified `tools` API stable through 0.85 → 0.102 series; pinned `0.101.0` has the structured-output features Phase 6 needs.
- [OpenAI SDK CHANGELOG.md](https://github.com/openai/openai-python/blob/main/CHANGELOG.md) — Verified `response_format={"type": "json_schema", "json_schema": ...}` stable; pinned `2.36.0` is current and has the path.
- [PyPI anthropic package metadata](https://pypi.org/pypi/anthropic/json) — Confirmed `0.101.0` (2026-05-11 release) and `0.102.0` (2026-05-13 latest); range `>=0.101.0,<1` in `docintel-core/pyproject.toml` covers both.
- [PyPI openai package metadata](https://pypi.org/pypi/openai/json) — Confirmed `2.36.0` is the latest; range `>=2.36.0,<3` covers it.
- [Anthropic structured outputs documentation](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) — Verified two paths (tools + strict, `output_config`); chose tools+strict as the more stable recommendation.
- [Anthropic tool-use documentation](https://platform.claude.com/docs/en/docs/agents-and-tools/tool-use/implement-tool-use) — Verified `tool_choice={"type": "tool", "name": "X"}` API; response shape with `block.type == "tool_use"` + `block.input` extraction.
- [Anthropic XML-tag prompting documentation](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags) — Confirms `<context>` XML tag is the recommended RAG-prompting pattern.
- Repo source: `packages/docintel-core/src/docintel_core/adapters/protocols.py` — `LLMClient.complete(prompt, system)` contract verbatim.
- Repo source: `packages/docintel-core/src/docintel_core/adapters/types.py` — `CompletionResponse`, `JudgeVerdict`, `RerankedDoc`, `AdapterBundle` shapes verbatim.
- Repo source: `packages/docintel-core/src/docintel_core/adapters/factory.py` — Existing `make_adapters`, `make_index_stores`, `make_retriever` factory pattern + lazy-import gate.
- Repo source: `packages/docintel-core/src/docintel_core/adapters/real/llm_anthropic.py:102-108` — Existing tenacity wrap pattern (Phase 2 D-18).
- Repo source: `packages/docintel-core/src/docintel_core/adapters/real/judge.py` — Phase 2 placeholder being migrated by D-09.
- Repo source: `packages/docintel-core/src/docintel_core/adapters/stub/llm.py:23-37` — `_STUB_REFUSAL` + `_CHUNK_RE` Phase 2 D-16 anchors.
- Repo source: `packages/docintel-retrieve/src/docintel_retrieve/retriever.py:1-100` — Pipeline / structlog / single-seam template Phase 6 mirrors.
- Repo source: `scripts/check_adapter_wraps.sh`, `scripts/check_index_wraps.sh`, `scripts/check_ingest_wraps.sh` — Bash grep-gate template Phase 6 mirrors for `scripts/check_prompt_locality.sh`.
- Repo source: `.github/workflows/ci.yml` — Existing wrap-gate CI step pattern (the new prompt-locality step mirrors `Index wrap grep gate (D-21)` at lines 102-106).
- Repo source: `packages/docintel-core/src/docintel_core/types.py:148-191` — `RetrievedChunk` Pydantic precedent (Phase 5 CD-02) for `GenerationResult` shape.
- Repo source: `packages/docintel-core/src/docintel_core/log.py` — `merge_contextvars` already in the processor chain; Phase 12 `trace_id` propagation is automatic.

### Secondary (MEDIUM confidence)

- [Braintrust prompt versioning guide](https://www.braintrust.dev/articles/what-is-prompt-versioning) — Industry standard for SHA-based prompt versioning.
- [LaunchDarkly prompt management blog](https://launchdarkly.com/blog/prompt-versioning-and-management/) — Confirms manifest-style versioning with PROMPT_VERSION identifiers.
- [Judging the Judges paper (arxiv 2604.23178)](https://arxiv.org/html/2604.23178v1) — Cross-family bias mitigation in LLM-as-judge pipelines; supports Phase 2 D-04 design Phase 6 preserves.
- [FACTUM citation-hallucination paper (arxiv 2601.05866)](https://arxiv.org/pdf/2601.05866) — Mechanistic detection of citation hallucination; supports D-13 step 4 validation + CD-07 log-and-drop.
- [shshell.com Claude RAG prompting lesson](https://shshell.com/blog/multimodal-rag-module-16-lesson-1-prompting-claude) — Confirms `<context>` XML tag pattern + refusal-when-insufficient instruction approach.
- [OpenAI Structured Outputs announcement](https://openai.com/index/introducing-structured-outputs-in-the-api/) — 100% reliability on gpt-4o-2024-08-06+ in strict mode.
- [CallSphere OpenAI structured outputs guide](https://callsphere.ai/blog/openai-structured-outputs-response-format-json-schema) — Verified exact dict structure for `response_format`.
- [Citation-grounded code comprehension paper (arxiv 2512.12117)](https://arxiv.org/html/2512.12117v1) — Hybrid retrieval + graph-augmented context for citation grounding.

### Tertiary (LOW confidence — flag for validation in execution)

- [openai-python issue #1733 (response_format strict requirement)](https://github.com/openai/openai-python/issues/1733) — Documents the strict JSON Schema requirement; cited as caveat in Pitfall 6.
- [openai-python issue #1763 (.beta.parse ValidationError)](https://github.com/openai/openai-python/issues/1763) — Documents the `.beta.*.parse` instability that motivates using the stable `response_format` path.
- [anthropic-sdk-python issue #1204 (structured-output + thinking + tool use bugs)](https://github.com/anthropics/anthropic-sdk-python/issues/1204) — Documents edge cases; cited in Pitfall 6.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — every dep pinned in repo + verified against PyPI + GitHub CHANGELOG.
- Architecture: HIGH — single-seam Generator composition matches Phase 5 Retriever pattern verbatim; type/schema decisions are extensions of existing precedents (RetrievedChunk → GenerationResult).
- Pitfalls: HIGH — most pitfalls reference existing code surface (Phase 2 stub sentinel, Phase 5 query truncation, Phase 2 adapter wraps) + documented SDK behavior (issues #1733, #1763, #1204).
- Pitfall 1 (SDK drift): HIGH — concrete CHANGELOG verification.
- Pitfall 9 (import cycle): MEDIUM — recommendation may differ from D-12's literal wording; planner picks.
- Pitfall 10 (single-prompt comparative): MEDIUM — empirical question for Phase 9; deferred-idea seam documented.
- Validation architecture: HIGH — each Wave 0 test scaffold maps to a documented requirement ID (GEN-01..GEN-04) or decision (D-03, D-09, D-14, D-16, D-17); test commands runnable.

**Research date:** 2026-05-15
**Valid until:** 2026-06-14 (30 days for stable SDK pins) OR until `anthropic` or `openai` bumps to a major version, whichever comes first. The `tools=[{strict: true}]` + `response_format={"type": "json_schema", ...}` APIs are GA on both providers — low drift risk for the 30-day window.

---

## Wave Structure Recommendation (CD-10)

Per CD-10's "Recommend 5 waves matching Phase 5's shape" + the dependency analysis above:

| Wave | Plans | Scope | Parallel? | Rationale |
|------|-------|-------|-----------|-----------|
| **Wave 0** | 06-01, 06-02, (06-03) | Test scaffolds (xfail) + new package skeleton (pyproject.toml + module layout + py.typed + uv.lock regen) + the 5 doc-path updates (CLAUDE.md, config.json prompt_home, REQUIREMENTS GEN-01, ROADMAP, PROJECT.md) + new `scripts/check_prompt_locality.sh` (initially passes on still-empty prompts.py) | Parallel (06-01 = tests; 06-02 = skeleton + uv.lock; 06-03 = docs + grep gate). Disjoint files_modified. | Mirrors Phase 5 Wave 0 (Plans 05-01 + 05-02 parallel). Sets up CI gate before any prompt code lands so Wave 1 can run the gate against the new `prompts.py`. |
| **Wave 1** | 06-04 | `prompts.py` (3 module-level constants + per-prompt + combined `PROMPT_VERSION_HASH`) + `parse.py` (`_CHUNK_RE` + sentinel detection helpers); flip GEN-01 + GEN-02 tests from xfail → pass | Single plan | `parse.py` is tiny enough to live in the same plan as `prompts.py`; both flip the same Wave 0 xfail tests. |
| **Wave 2** | 06-05 | `Generator` class in `generator.py` + `make_generator(cfg)` 4th sibling factory in `docintel_core.adapters.factory` + `GenerationResult` Pydantic model in `docintel_core.types`; flip GEN-03 + GEN-04 + D-03 + D-14 + D-16 + D-17 tests from xfail → pass | Single plan | Generator + factory + result model are tightly coupled (Generator returns GenerationResult; factory constructs Generator). One atomic plan. |
| **Wave 3** | 06-06 | Judge migration: move `_JUDGE_SYSTEM_PROMPT` → `JUDGE_PROMPT` in `prompts.py`; replace heuristic `_SCORE_PATTERN` regex in `adapters/real/judge.py` with structured JSON-mode output (Anthropic tool-use / OpenAI `response_format`) deserializing into `JudgeVerdict`. Update stub `_STUB_REFUSAL` to mirror `REFUSAL_PROMPT`. Move `_CHUNK_RE` to `docintel_generate.parse._CHUNK_RE` + re-import in stub. Flip D-09 + D-12 tests from xfail → pass. | Single plan | Migration is one tightly-scoped commit; preserves Phase 2 D-04 cross-family wiring untouched. |
| **Wave 4** | 06-07 | CI wiring (`.github/workflows/ci.yml` adds the prompt-locality step); xfail removal sweep on the 5 test scaffolds (some flipped earlier; this wave confirms zero xfail remain); real-mode hero question test (`@pytest.mark.real`, workflow_dispatch-gated); Decision-Coverage Audit (D-01..D-17 + CD-01..CD-10 = 27/27); phase gate verification | Single plan | Mirrors Phase 5 Plan 05-07: final wave is CI + audit + xfail sweep + real-mode test promotion. |

Estimated plan count: **7 plans across 5 waves** (Wave 0 has 3 parallel plans; Waves 1-4 are single-plan each). Matches Phase 5's 7-plan / 4-wave shape with one extra wave for the judge migration.

[VERIFIED: matches CD-10 recommendation; sequencing analysis from CONTEXT.md `<decisions>` D-01..D-17 dependencies]
