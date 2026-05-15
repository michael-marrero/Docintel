# Phase 6: generation - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship the query-time generation layer that takes a user question + Phase 5's `list[RetrievedChunk]` and produces a grounded, cited answer (or an explicit refusal) ready for Phase 7's `Answer` wrapper. Three concrete artifacts: (1) a new 8th workspace package `docintel-generate` with a single `prompts.py` module that owns ALL canonical prompts (synthesis, refusal, judge) under a per-prompt + combined `PROMPT_VERSION_HASH`; (2) a `Generator` class wrapping `LLMClient` + `Retriever` exposed via a 4th sibling factory `make_generator(cfg)` in `docintel_core.adapters.factory`; (3) a `scripts/check_prompt_locality.sh` CI grep gate that mirrors the existing wrap-gate pattern (`check_adapter_wraps.sh`, `check_index_wraps.sh`, `check_ingest_wraps.sh`) and enforces GEN-01 (no inline prompts outside `prompts.py`). The phase also migrates the Phase 2 placeholder judge prompt (`_JUDGE_SYSTEM_PROMPT` + `_build_judge_prompt` + heuristic `_SCORE_PATTERN` parser) out of `adapters/real/judge.py` and into `prompts.py` + structured JSON-mode parsing so Phase 9 inherits a stable manifest hash.

Closes: GEN-01..GEN-04.

**Out of scope (do not invent here):**
- The `Answer` / `Citation` Pydantic schema with quote-span enrichment + `confidence` field — Phase 7 (ANS-01..03). Phase 6 returns `GenerationResult`; Phase 7 maps it into `Answer`.
- Hit@K / MRR / faithfulness / citation accuracy / latency / $/query metrics — Phase 9 (MET-01..06). Phase 6 emits per-query telemetry (`generator_completed` structlog line); Phase 9 aggregates.
- Eval harness CLI + report writer + manifest header consumption — Phase 10 (EVAL-01..04). The `PROMPT_VERSION_HASH` exposed here is what Phase 10's report manifest reads; Phase 6 does NOT write reports.
- Ablation experiments — Phase 11 (ABL-01..02). Phase 6 lays no new ablation seam (Phase 5 D-08's null-adapter pattern already covers retrieval-side ablations; generation-side ablation is "swap the LLM provider", already at Phase 2 D-03).
- `trace_id` propagation via `structlog.contextvars` — Phase 12 (OBS-01). Phase 6 emits structured log lines so Phase 12 only binds `trace_id` upstream — no retrofit.
- HTTP `/query` endpoint, Streamlit UI rendering — Phase 13 (UI-01..06). Phase 13's API consumes `Generator.generate()`.
- Cross-family judge wiring + `Settings.llm_real_provider` complement-selection — Phase 2 D-04 contract preserved. Phase 6 migrates the judge PROMPT + PARSER only; the factory dispatch stays untouched.
- Multi-turn / chat-style conversation — explicitly out of scope per PROJECT.md "Chat-style multi-turn UI" exclusion.
- Streaming generation / async API — Phase 2 D-08 locked sync-only for v1.
- Per-question-type prompt routing (factual / comparative / refusal templates) — single synthesis prompt handles factual + comparative; deferred (see below) if eval shows the single prompt underperforms.

</domain>

<decisions>
## Implementation Decisions

### Package home + prompts path

- **D-01:** **New 8th workspace package `docintel-generate`** at `packages/docintel-generate/`. Mirrors the Phase 3 (`docintel-ingest`), Phase 4 (`docintel-index`), Phase 5 (`docintel-retrieve`) precedents — every phase that ships a query-time or build-time domain owns its own workspace package. Module layout (planner refines):
  - `packages/docintel-generate/pyproject.toml` — pins `docintel-core` (workspace dep — transitive `anthropic`/`openai` via core's adapter deps); pins `docintel-retrieve` (workspace dep — `Retriever` + `RetrievedChunk`).
  - `packages/docintel-generate/src/docintel_generate/__init__.py` — re-exports `Generator`, `GenerationResult`, the three `*_PROMPT` constants, `PROMPT_VERSION_HASH`.
  - `packages/docintel-generate/src/docintel_generate/prompts.py` — the ONLY home of `SYNTHESIS_PROMPT`, `REFUSAL_PROMPT`, `JUDGE_PROMPT`, their per-prompt hashes, and combined `PROMPT_VERSION_HASH`. Grep-gate-protected per D-04.
  - `packages/docintel-generate/src/docintel_generate/generator.py` — `Generator` class implementing the `.generate(query, k) -> GenerationResult` seam.
  - `packages/docintel-generate/src/docintel_generate/parse.py` — `_CHUNK_RE` regex parser + sentinel detection (extracted so stub adapter + tests share the same parser).
  - `packages/docintel-generate/src/docintel_generate/py.typed` (PEP 561).
  - Workspace pyproject's `packages/*` glob picks it up automatically; `uv.lock` regenerated as part of Phase 6.

- **D-02:** **Docs reconciliation — Phase 6 plan updates `CLAUDE.md`, `.planning/config.json` (`prompt_home`), `.planning/REQUIREMENTS.md` (GEN-01 path), `.planning/ROADMAP.md` (Phase 6 `Provides:`), and `.planning/PROJECT.md` (Constraints "Prompts are versioned")** to reference `packages/docintel-generate/src/docintel_generate/prompts.py`. The original spec path `src/docintel/generation/prompts.py` does NOT exist in this repo and was a reconstruction artifact; the workspace package layout has been the de-facto convention since Phase 3. Single source of truth from now on; one consolidated doc-update commit in Wave 0 or Wave 5 (planner picks the wave).

- **D-03:** **`make_generator(cfg) -> Generator` factory in `docintel_core.adapters.factory`** — 4th sibling factory alongside `make_adapters(cfg)`, `make_index_stores(cfg)`, `make_retriever(cfg)`. Reads `cfg` for lazy-import discipline (Phase 2 D-12), internally calls `make_adapters(cfg)` for the `AdapterBundle` and `make_retriever(cfg)` for the `Retriever`, then constructs `Generator(bundle=adapters, retriever=retriever)`. Phase 10 + 13 use the factory; tests construct `Generator(bundle, retriever)` directly so the bundle can be assembled with stubbed components. Factory lives in `docintel_core.adapters.factory` (NOT in `docintel-generate`) so the import direction matches every prior phase: `docintel-generate` imports from `docintel-core`, never the reverse. Lazy import of `from docintel_generate.generator import Generator` lives inside the factory function body, not at module top.

### CI grep gate (GEN-01)

- **D-04:** **`scripts/check_prompt_locality.sh`** — mirrors `scripts/check_adapter_wraps.sh` / `check_index_wraps.sh` / `check_ingest_wraps.sh`. Scans `packages/**/*.py` for prompt-like patterns and fails if any are found outside the allowed paths. Pattern set (planner finalises during execution):
  - Triple-quoted string literals at module level whose content matches `\b(You are|Based on the|<context>|<chunks>|cite|grounded|chunk_id)\b` AND length > 80 chars.
  - String constants whose name matches `_*PROMPT*` / `_*INSTRUCTION*` / `_*SYSTEM*` outside the allowlisted paths.

- **D-05:** **Exclusion policy = path allowlist + per-line `# noqa: prompt-locality` escape hatch.** Default-excluded paths:
  - `packages/docintel-generate/src/docintel_generate/prompts.py` (the canonical home).
  - `packages/docintel-generate/src/docintel_generate/parse.py` (regex + sentinel only — short literal strings).
  - `tests/**`, `**/conftest.py`, `**/test_*.py` (test fixtures legitimately quote prompts for assertion).
  - `packages/docintel-core/src/docintel_core/adapters/stub/llm.py` — the existing `_STUB_REFUSAL` constant + `_CHUNK_RE` regex (Phase 2 D-16) are pre-existing structural fixtures. **Phase 6 D-12 updates `_STUB_REFUSAL` to the new canonical refusal sentinel** (D-11 below); the constant remains in the stub but mirrors `REFUSAL_PROMPT`.
  - Per-line escape: appending `# noqa: prompt-locality` to a line silences the check for that line (mirrors `# noqa: E501` / `# type: ignore`). Outstanding exceptions are grep-able via `grep -rn 'noqa: prompt-locality' packages/`.

- **D-06:** **CI wiring** — `.github/workflows/ci.yml` gains one new step (parallel to the existing three wrap-checks):
  ```yaml
  - name: Check prompt locality (GEN-01)
    run: bash scripts/check_prompt_locality.sh
  ```
  The check runs in stub mode (no env vars required) on every PR. Exit code 1 fails the build with a message that names the offending file + line + matched pattern.

### Prompt module structure

- **D-07:** **Three named module-level prompts in `prompts.py`:**
  - `SYNTHESIS_PROMPT: Final[str]` — the main answer-with-citations system prompt. Handles single-doc factual AND multi-hop comparative under one prompt (the LLM is instructed to ground every claim and refuse if context is insufficient). Includes a fenced citation example to lock the bracket format.
  - `REFUSAL_PROMPT: Final[str]` — the canonical refusal sentinel text (D-11) the LLM is instructed to emit verbatim when retrieved context cannot answer the question. Also returned directly (bypassing the LLM) when `retrieved_chunks` is empty (D-10 hard-floor path).
  - `JUDGE_PROMPT: Final[str]` — the cross-family faithfulness judging system prompt. Migrated from Phase 2's placeholder `_JUDGE_SYSTEM_PROMPT` in `adapters/real/judge.py`. Includes a structured-output schema (Anthropic tool-use / OpenAI `response_format`) so `JudgeVerdict.unsupported_claims` populates without regex heuristics.

- **D-08:** **Per-prompt + combined `PROMPT_VERSION_HASH`**, all computed at module import time:
  ```python
  import hashlib

  def _h(s: str) -> str:
      return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]

  _SYNTHESIS_HASH: Final[str] = _h(SYNTHESIS_PROMPT)
  _REFUSAL_HASH: Final[str]   = _h(REFUSAL_PROMPT)
  _JUDGE_HASH: Final[str]     = _h(JUDGE_PROMPT)
  PROMPT_VERSION_HASH: Final[str] = _h(_SYNTHESIS_HASH + _REFUSAL_HASH + _JUDGE_HASH)
  ```
  Phase 10's eval report manifest (EVAL-02) carries the combined `PROMPT_VERSION_HASH` only. Ablation reports + the `generator_completed` structlog line carry per-prompt hashes so a regression can be localised. Hashing happens at import time — no runtime cost per query; constants are validated by mypy as `Final[str]`.

- **D-09:** **Judge migration scope — prompt + parser, not the dispatch.**
  - Move `_JUDGE_SYSTEM_PROMPT` + the body of `_build_judge_prompt(prediction, reference, rubric)` into `prompts.py` as `JUDGE_PROMPT` + a small `build_judge_user_prompt(...)` helper alongside.
  - **Replace** the heuristic `_SCORE_PATTERN` regex parser with structured JSON-mode output: Anthropic calls use `tools=[{...}]` to bind the response to a JSON schema (`{"score": float, "passed": bool, "reasoning": str, "unsupported_claims": list[str]}`); OpenAI calls use `response_format={"type": "json_schema", ...}`. Both adapter paths deserialize directly into `JudgeVerdict`.
  - **Preserve** the Phase 2 D-04 cross-family wiring in `adapters/real/judge.py` — the `CrossFamilyJudge` class, the `Settings.llm_real_provider` complement-selection in the factory, the tenacity-delegation-to-the-underlying-LLM pattern. Those are Phase 2 contracts; Phase 6 does not touch them.
  - The `adapters/real/judge.py` file shrinks: the prompt is gone (import from `docintel_generate.prompts`), the parser is gone (replaced by the structured-output deserializer), the cross-family wiring stays.

### Citation format + faithfulness contract

- **D-10:** **Inline `[chunk_id]` brackets with a locked fenced example in `SYNTHESIS_PROMPT`.** The prompt body includes a verbatim example:
  ```
  Example:
  Apple highlighted supplier concentration in China and Taiwan as a key
  risk in its FY2024 10-K [AAPL-FY2024-Item-1A-018]. NVIDIA disclosed
  revenue concentration with a single hyperscaler customer
  [NVDA-FY2024-Item-7-042].
  ```
  Explicit rule in the prompt: "Every factual sentence MUST end with one or more `[chunk_id]` citations referencing the chunks I provided. Do not invent chunk_ids; only cite from the `<context>` block. If you cannot ground a claim in the provided context, omit it." Matches the existing stub `_CHUNK_RE = re.compile(r"\[([^\]]+)\]")` (Phase 2 D-16) verbatim — single regex across stub + real; Phase 7's `Citation` parser uses the same regex out of `GenerationResult.text`.

- **D-11:** **Canonical refusal sentinel = `"I cannot answer this question from the retrieved 10-K excerpts."`** Exactly this string, no trailing punctuation variation. Stored in `REFUSAL_PROMPT` (also the LLM-instruction body that tells the model "emit the following exact string verbatim if you cannot ground an answer in the provided context: ..."). The generator post-hoc checks if `generation_text.startswith(REFUSAL_TEXT_SENTINEL)` to set `GenerationResult.refused = True`. The Phase 2 stub `_STUB_REFUSAL = "[STUB REFUSAL] No evidence found in retrieved context."` is updated to emit this new sentinel verbatim — single canonical refusal text across stub + real.

- **D-12:** **Stub adapter update.** `packages/docintel-core/src/docintel_core/adapters/stub/llm.py` is amended:
  - `_STUB_REFUSAL` constant value changes to match `REFUSAL_PROMPT_SENTINEL` from `docintel_generate.prompts` (single source of truth). The `_STUB_REFUSAL` name is retained for backward-compatibility of any tests already importing it; the value tracks `prompts.py`. **One stub import** is allowed to cross into `docintel-generate` (stub → generate is upward-stack, acceptable; the generator never imports the stub).
  - The `[STUB ANSWER citing ...]` template continues to emit `[chunk_id]` markers verbatim — no change needed.
  - The chunk_id regex `_CHUNK_RE` is moved to `docintel_generate.parse._CHUNK_RE` and re-imported by the stub for consistency. Single regex across stub + real + Phase 7 parser.

- **D-13:** **Faithfulness enforcement = prompt-instructed + post-hoc parse, NO blocking.** The generator's pipeline:
  1. Build user prompt by formatting `retrieved_chunks` into the D-14 context block.
  2. Call `bundle.llm.complete(prompt=user_prompt, system=SYNTHESIS_PROMPT)` — already tenacity-wrapped at the adapter layer (Phase 2 D-18). NO new wrap site.
  3. Run `_CHUNK_RE.findall(response.text)` to extract `cited_chunk_ids`.
  4. **Validate every cited chunk_id is in `{c.chunk_id for c in retrieved_chunks}`.** Hallucinated IDs (LLM invented a chunk_id) are dropped from `cited_chunk_ids` with a structlog `generator_hallucinated_chunk_id` warning. The response text is NOT modified — Phase 9 MET-04 (citation accuracy) measures the failure rate as part of the eval contract; we don't paper over it.
  5. Check `response.text.startswith(REFUSAL_TEXT_SENTINEL)` to set `refused = True`.
  6. Return `GenerationResult(...)`.

  **No re-prompting on missing citations; no sentence-stripping.** Faithfulness is a measurement, not an enforcement — Phase 9 MET-03 makes that measurement first-class.

### Generator API + return shape

- **D-14:** **Chunk formatting inside the user prompt = numbered `<context>` blocks with metadata header.**
  ```
  <context>
  [chunk_id: AAPL-FY2024-Item-1A-018 | company: AAPL | fiscal_year: 2024 | section: Item 1A]
  <actual chunk.text>
  ---
  [chunk_id: NVDA-FY2024-Item-7-042 | company: NVDA | fiscal_year: 2024 | section: Item 7]
  <actual chunk.text>
  ---
  ...
  </context>

  Question: <user query>
  ```
  Metadata header surfaces `chunk_id` (reinforces the bracket-pattern instruction), `company` (ticker), `fiscal_year`, `item_code` — exactly the four fields the hero question needs to disambiguate multi-hop comparatives ("Which of these companies grew R&D while margins shrank in 2023?"). All four come straight from `RetrievedChunk` (Phase 5 D-03). The `<context>` tag is XML-style for both Claude and GPT — both models reliably parse and reference XML-like tags in instructions.

- **D-15:** **`Generator.generate(query: str, k: int = 5) -> GenerationResult`** is the single seam (D-02 of Phase 5 in spirit — one callable, end-to-end). Internal pipeline:
  - **Step A:** call `self._retriever.search(query, k=k)` — already truncates queries (Phase 5 D-11), already emits `retriever_search_completed`.
  - **Step B:** if `retrieved_chunks` is empty → **hard refusal path**: return `GenerationResult(text=REFUSAL_TEXT_SENTINEL, cited_chunk_ids=[], refused=True, retrieved_chunks=[], completion=None, prompt_version_hash=PROMPT_VERSION_HASH)` with a `generator_refused_zero_chunks` structlog warning. Skip the LLM entirely (saves a call when retrieval already said "I have nothing").
  - **Step C:** format `retrieved_chunks` into the D-14 context block. Call `bundle.llm.complete(prompt=user_prompt, system=SYNTHESIS_PROMPT)`.
  - **Step D:** parse citations (D-13 step 3-4), detect refusal sentinel (D-13 step 5), build `GenerationResult`.
  - **Step E:** emit `generator_completed` structlog (D-16) and return.

- **D-16:** **Per-query telemetry = single `generator_completed` structlog line** mirroring Phase 5's `retriever_search_completed`:
  ```python
  log.info(
      "generator_completed",
      query_tokens=q_tokens,
      n_chunks_retrieved=len(retrieved_chunks),
      n_chunks_cited=len(cited_chunk_ids),
      refused=refused,
      prompt_version_hash=PROMPT_VERSION_HASH,
      synthesis_hash=_SYNTHESIS_HASH,
      refusal_hash=_REFUSAL_HASH,
      judge_hash=_JUDGE_HASH,
      prompt_tokens=completion.usage.prompt_tokens if completion else 0,
      completion_tokens=completion.usage.completion_tokens if completion else 0,
      cost_usd=completion.cost_usd if completion else 0.0,
      retrieval_ms=retrieval_ms,
      generation_ms=generation_ms,
      total_ms=total_ms,
      model=completion.model if completion else "stub-refusal",
  )
  ```
  Phase 9 MET-05 ($/query + p50/p95 latency) reads `cost_usd` + `total_ms`; Phase 9 MET-03 (faithfulness) reads `refused`; Phase 12 binds `trace_id` via `contextvars` — Phase 6 inherits automatically when OBS-01 lands.

- **D-17:** **`GenerationResult` is a new Pydantic model in `docintel_core.types`** with `ConfigDict(extra="forbid", frozen=True)`:
  ```python
  class GenerationResult(BaseModel):
      """Phase 6 generation output. Phase 7 wraps into Answer."""
      model_config = ConfigDict(extra="forbid", frozen=True)
      text: str                              # raw LLM output (or REFUSAL_TEXT_SENTINEL on hard refusal)
      cited_chunk_ids: list[str]             # de-duplicated, validated against retrieved_chunks set
      refused: bool                          # True if hard zero-chunk path OR LLM emitted refusal sentinel
      retrieved_chunks: list[RetrievedChunk] # the K chunks Phase 5 returned (frozen, immutable)
      completion: CompletionResponse | None  # None on hard refusal (LLM not called); otherwise the LLM's return
      prompt_version_hash: str               # combined PROMPT_VERSION_HASH at generation time
  ```
  Home: `docintel_core.types` (matches `RetrievedChunk` precedent CD-02 of Phase 5 — Phase 7 imports without depending on `docintel-generate`; the schema is a contract). `frozen=True` matches `RetrievedChunk` — downstream callers can't mutate. The `completion: CompletionResponse | None` carries the LLM's native shape so Phase 10 sources `cost_usd` / `latency_ms` / `model` per-call without re-introspecting the generator.

### Claude's Discretion

These are intentionally left to the researcher/planner:

- **CD-01:** **Exact SYNTHESIS_PROMPT wording.** The decisions above lock the structure (system + user with `<context>` blocks), the citation example, the refusal sentinel, and the explicit faithfulness rule. The exact phrasing (formality, length, system-prompt vs user-prompt distribution) is planner's discretion — researcher should pull current best-practices for RAG prompting from Anthropic / OpenAI docs (cf. Phase 5 RESEARCH §1 pattern). Whatever phrasing lands needs to satisfy the hero question ("Which of these companies grew R&D while margins shrank in 2023?") in real-mode eval.

- **CD-02:** **Exact JUDGE_PROMPT wording + structured-output JSON schema.** The decisions above lock the migration (move from `adapters/real/judge.py` into `prompts.py`) and the parser switch (heuristic regex → structured output via Anthropic tools / OpenAI `response_format`). The exact schema fields are `{"score": float, "passed": bool, "reasoning": str, "unsupported_claims": list[str]}` (matching `JudgeVerdict`); the prompt phrasing is planner's discretion. Researcher should pull current best-practices for cross-family judging — bias mitigation, calibration. The Phase 2 D-04 cross-family wiring is preserved as-is.

- **CD-03:** **Whether `Generator.__init__` lazy-loads or eager-loads.** Recommend eager (matches Phase 5 CD-01 `Retriever` precedent — `make_retriever(cfg)` eager-loads on instantiation). `Generator` instantiation is cheap (just stashes `bundle` + `retriever`); first-call cost is the underlying LLM SDK init, which is already lazy in `AnthropicAdapter._get_client` (Phase 2 lazy SDK init, commit `9ec4d36`).

- **CD-04:** **Tenacity retry on the LLM call.** None added at Phase 6. The Phase 5 CD-04 pattern carries over verbatim: `bundle.llm.complete(...)` is already tenacity-wrapped at the adapter layer (Phase 2 D-18 — see `adapters/real/llm_anthropic.py:102-108`). Phase 6 does NOT add a second wrap layer. `scripts/check_adapter_wraps.sh` continues to enforce the rule; the new `check_prompt_locality.sh` is independent.

- **CD-05:** **`make_generator(cfg)` caching.** Recommend NO factory-level cache (mirrors Phase 5 CD-08). Phase 13's FastAPI will `lru_cache` the constructed `Generator`; Phase 10 eval harness constructs once per run.

- **CD-06:** **Context-window budget verification.** K=5 chunks × ~500 BGE tokens ≈ 2500 tokens of chunk text + ~400 tokens of system prompt + ~100 tokens of question + ~200 tokens of context-block scaffolding ≈ 3200-3500 tokens total. Claude Sonnet 4.6 has 200K context, GPT-4-class has ≥128K — both safely accommodate. Planner verifies during execution by logging actual `prompt_tokens` on the hero question and confirming < 8K.

- **CD-07:** **Hallucinated chunk_id handling — log + drop vs raise.** Recommend log + drop (D-13 step 4). Phase 9 MET-04 measures citation accuracy as a fraction; raising on hallucination would convert a measurable failure mode into a hard crash, hurting eval signal. The structlog `generator_hallucinated_chunk_id` warning fires once per offending ID per query.

- **CD-08:** **Test layout for `docintel-generate`.** Recommend test scaffolds (xfail) in Wave 0 mirroring Phase 5's pattern: one test file per requirement (GEN-01 grep gate, GEN-02 hash exposure, GEN-03 stub determinism, GEN-04 refusal path) + integration tests for `Generator.generate()` end-to-end (stub mode runs in CI on every PR; real-mode marked `@pytest.mark.real` and gated by workflow_dispatch).

- **CD-09:** **JSON-mode SDK call signature.** Anthropic's `tools=[{"name": "submit_verdict", "input_schema": {...}}]` vs `response_format={"type": "json_schema", "json_schema": ...}` (newer messages API). OpenAI's `response_format={"type": "json_schema", "json_schema": ...}`. Researcher pulls current docs (anthropic-python SDK + openai-python SDK) and pins the exact call signature; planner may need to bump dep pins in `docintel-core/pyproject.toml` if Phase 2's pinned versions don't expose the structured-output APIs.

- **CD-10:** **Wave structure.** Recommend 5 waves matching Phase 5's shape: Wave 0 (test scaffolds + new package skeleton + uv.lock + doc updates + new scripts/check_prompt_locality.sh), Wave 1 (prompts.py with three constants + per-prompt + combined hashes; parse.py with _CHUNK_RE), Wave 2 (Generator class + make_generator factory + GenerationResult model in docintel_core.types), Wave 3 (judge migration: prompts.py JUDGE_PROMPT + structured-output parser in adapters/real/judge.py + stub _STUB_REFUSAL sync), Wave 4 (CI wiring + xfail removal + Decision-Coverage Audit). Planner refines.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher + planner) MUST read these before planning or implementing.**

### Project-level (always)
- `CLAUDE.md` — Operating rules. Specifically: "All prompts live in `src/docintel/generation/prompts.py`, versioned with a hash. Grep for inline string-literal prompts must return zero matches." This is GEN-01's source. **Phase 6 plan updates this file** per D-02 (path becomes `packages/docintel-generate/src/docintel_generate/prompts.py`). Also: "No silent retries on LLM calls" — Phase 6's CD-04 carries Phase 2 D-18 forward verbatim. "Offline-first / `LLM_PROVIDER=stub` default" — Phase 6's stub adapter update (D-12) preserves stub-mode determinism end-to-end.
- `.planning/PROJECT.md` — Constraints section "Prompts are versioned: all prompts live in `src/docintel/generation/prompts.py` with a hash." **Phase 6 plan updates the path** per D-02. Out-of-Scope row "Chat-style multi-turn UI" is the rationale for Phase 6 staying single-turn.
- `.planning/REQUIREMENTS.md` §"Generation (Phase 6)" — GEN-01..04 verbatim; the success-criteria language is what `gsd-verifier` will grep for. GEN-01 path reference **updated by Phase 6 plan** per D-02. §"Answer Schema (Phase 7)" ANS-01..03 — the `prompt_version_hash` field on `Answer` is sourced from Phase 6's `GenerationResult.prompt_version_hash`. §"Metrics (Phase 9)" MET-03 (faithfulness) + MET-04 (citation accuracy) — both read `GenerationResult.cited_chunk_ids` and the `generator_completed` telemetry. §"Eval Harness (Phase 10)" EVAL-02 — manifest header carries `prompt_version_hash`; Phase 6 must expose it as a module-level constant.
- `.planning/ROADMAP.md` §"Phase 6: generation" — success criteria verbatim. Path reference **updated by Phase 6 plan** per D-02. §"Phase 7: answer-schema" — Phase 7 consumes `GenerationResult`. §"Phase 13: api-ui-polish" — hero question is the multi-hop comparative; Phase 6's single SYNTHESIS_PROMPT must handle it (CD-01).
- `.planning/STATE.md` §"Hard Gates To Remember" — Phase 6 opens the LLM call path (real-mode); the lazy SDK init in `9ec4d36` defers `DOCINTEL_ANTHROPIC_API_KEY` / `DOCINTEL_OPENAI_API_KEY` to `.complete()` first-call. §"How to Resume" line 95 explicitly anticipates Phase 6 starting next.
- `.planning/config.json` — `constraints.prompt_home = "src/docintel/generation/prompts.py"`. **Phase 6 plan updates this field** per D-02.

### Phase 2 + 4 + 5 ground truth (existing code surface)
- `packages/docintel-core/src/docintel_core/config.py` — Phase 1 Settings. Phase 6 adds NO new fields (single env reader rule preserved; provider switching uses existing `llm_provider` + `llm_real_provider`). FND-11 grep gate stays green.
- `packages/docintel-core/src/docintel_core/types.py` — `Chunk` + `RetrievedChunk` already shipped. **Phase 6 adds `GenerationResult`** per D-17 (sibling Pydantic model, `frozen=True`).
- `packages/docintel-core/src/docintel_core/adapters/protocols.py` — `LLMClient.complete(prompt, system)` is the seam Phase 6 calls. `LLMJudge.judge(prediction, reference, rubric)` is what Phase 9 calls; Phase 6 only changes the JUDGE_PROMPT consumed by the underlying LLM call (D-09).
- `packages/docintel-core/src/docintel_core/adapters/types.py` — `CompletionResponse` (text, usage, cost_usd, latency_ms, model) is what Phase 6 embeds in `GenerationResult.completion`. `JudgeVerdict` shape (score, passed, reasoning, unsupported_claims) is the structured-output JSON schema target (D-09).
- `packages/docintel-core/src/docintel_core/adapters/factory.py` — `make_adapters(cfg)` + `make_index_stores(cfg)` + `make_retriever(cfg)`. **Phase 6 adds `make_generator(cfg)`** as the FOURTH sibling factory per D-03. Lazy-import discipline (`from docintel_generate.generator import Generator` inside the function body).
- `packages/docintel-core/src/docintel_core/adapters/real/llm_anthropic.py` — `AnthropicAdapter.complete(prompt, system)`. Already tenacity-wrapped (`@retry` lines 102-108). Phase 6 passes `system=SYNTHESIS_PROMPT` (or `JUDGE_PROMPT` for judge calls); structured-output for the judge path needs SDK pin verification (CD-09). The `system or "You are a helpful assistant."` fallback in line 134 is the placeholder Phase 6 replaces.
- `packages/docintel-core/src/docintel_core/adapters/real/llm_openai.py` — same shape as the Anthropic adapter. Phase 6 must verify `response_format={"type": "json_schema", ...}` is available in the pinned `openai` SDK version (CD-09).
- `packages/docintel-core/src/docintel_core/adapters/real/judge.py` — placeholder home for `_JUDGE_SYSTEM_PROMPT` (line 44), `_build_judge_prompt` (line 55), heuristic `_SCORE_PATTERN` (line 52). **Phase 6 D-09 migrates the prompt + replaces the parser.** The cross-family `CrossFamilyJudge` class + `Settings.llm_real_provider` complement-selection in the factory (Phase 2 D-04) stay.
- `packages/docintel-core/src/docintel_core/adapters/stub/llm.py` — `_STUB_REFUSAL` constant (line 23), `_CHUNK_RE` regex (line 31), templated synthesis (lines 80-84). **Phase 6 D-12 updates `_STUB_REFUSAL` to mirror `REFUSAL_PROMPT`** (single canonical sentinel). The `_CHUNK_RE` regex moves to `docintel_generate.parse._CHUNK_RE` and is re-imported by the stub.
- `packages/docintel-retrieve/src/docintel_retrieve/retriever.py` — `Retriever.search(query, k) -> list[RetrievedChunk]` is what `Generator.generate()` calls in Step A (D-15). Already eager-loads the chunk_map; already emits `retriever_search_completed` telemetry; already truncates queries at 64 BGE tokens (Phase 5 D-11). Phase 6's `Generator.__init__` takes a constructed `Retriever` instance (NOT a `cfg`) — factory composes them.
- `packages/docintel-core/src/docintel_core/log.py` — `configure_logging` + `merge_contextvars`. Phase 6 emits `generator_completed` (D-16). Phase 12's `trace_id` binding via `contextvars` is OBS-01 — Phase 6's log line gains a `trace_id` field automatically when Phase 12 lands; no Phase 6 retrofit.
- `scripts/check_adapter_wraps.sh` — Phase 2 grep gate. Pattern reference for D-04's new `scripts/check_prompt_locality.sh`. The wrap-gate script structure (BASH_DIR, allowlist files, grep pattern, exit code) is the implementation template for the prompt-locality gate.
- `scripts/check_index_wraps.sh`, `scripts/check_ingest_wraps.sh` — additional patterns to mirror.
- `.planning/phases/02-adapters-protocols/02-CONTEXT.md` — D-03 (dual Anthropic + OpenAI real adapters), D-04 (cross-family judge — Phase 6 preserves), D-16 (stub LLM templated synthesis + `[chunk_id]` bracket pattern + `_STUB_REFUSAL` sentinel — Phase 6 D-12 updates the sentinel value, preserves the regex), D-17 (stub judge schema-check — Phase 9 path; Phase 6 doesn't touch). D-18 (tenacity wrap at adapter layer — Phase 6 CD-04 inherits).
- `.planning/phases/05-retrieval-hybrid-rerank/05-CONTEXT.md` — D-02 (Retriever single seam — Phase 6 calls verbatim), D-03 (RetrievedChunk shape — Phase 6 D-14 reads `text`, `chunk_id`, `ticker`, `fiscal_year`, `item_code`), D-04 (`make_retriever(cfg)` factory pattern — Phase 6 mirrors with `make_generator(cfg)`), D-11 (query truncation — already in place), D-12 (per-stage structlog — Phase 6 D-16 mirrors the schema), CD-04 (no new tenacity wraps — Phase 6 inherits verbatim).
- `.github/workflows/ci.yml` — Phase 6 adds one step (D-06). Reference: the 3 existing wrap-gate steps for the YAML pattern.

### External docs (for the researcher)
- **anthropic-python SDK** — `messages.create(...)` API; `tools=[{"name": ..., "input_schema": ...}]` for structured output (judge path D-09); `system` parameter usage (already exercised in `adapters/real/llm_anthropic.py:131`). Researcher pulls the pinned SDK version's docs to confirm `tools` is available; if not, bump the pin.
- **openai-python SDK** — `chat.completions.create(...)` API; `response_format={"type": "json_schema", "json_schema": ...}` for structured output (judge path D-09). Same pin-verification note as Anthropic.
- **Anthropic prompt engineering guide** (claude.ai/docs) — RAG-prompting best practices: `<context>` XML tags (Phase 6 D-14 uses this); explicit citation rules; refusal instructions. Use for CD-01 prompt phrasing.
- **OpenAI structured outputs docs** — `response_format` with JSON schema; reliability characteristics; latency overhead. Use for CD-09 SDK call signature.
- **Python `hashlib`** — `sha256().hexdigest()[:12]` for D-08 truncated hashes.
- **structlog `merge_contextvars` docs** — Phase 12 will bind `trace_id` here; Phase 6's log lines automatically inherit. Already wired in Phase 1's `configure_logging`.
- **pytest marker docs** — `@pytest.mark.real` is defined in Phase 4's conftest; CD-08 reuses for real-mode generator tests.
- **uv workspace docs** — `packages/*` glob picks up the new `docintel-generate` package; `uv lock` regenerates. Already exercised in Phases 3/4/5.

[No additional spec/ADR files were referenced by the user during discussion — canonical refs derived from the project-level docs, prior CONTEXT.md files, the existing code surface, and the wrap-gate scripts.]

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`AdapterBundle`** (`docintel_core.adapters.types`) — Phase 2 container with `embedder`, `reranker`, `llm`, `judge`. Phase 6's `Generator(bundle, retriever)` takes this verbatim. The `llm` field is what `.complete()` is called on; the `judge` field is what Phase 9 will use (Phase 6 only migrates the judge PROMPT consumed by it).
- **`Retriever`** (`docintel_retrieve.retriever`) — Phase 5's class. `Generator.__init__` takes a constructed instance; `Generator.generate()` calls `.search(query, k)` once per query (Step A of D-15). Already eager-loads chunk_map; already truncates queries; already emits per-stage telemetry — Phase 6 inherits all of it.
- **`make_adapters(cfg)` + `make_index_stores(cfg)` + `make_retriever(cfg)`** (`docintel_core.adapters.factory`) — Phase 6's `make_generator(cfg)` is the FOURTH sibling factory here per D-03. Lazy-import discipline extends: `from docintel_generate.generator import Generator` inside the factory function body.
- **`LLMClient.complete(prompt, system)`** (Protocol in `docintel_core.adapters.protocols`) — Phase 6 calls with `system=SYNTHESIS_PROMPT` (synthesis) or `system=JUDGE_PROMPT` (judge migration). Both real adapters (Anthropic + OpenAI) already implement; both are already tenacity-wrapped.
- **`CompletionResponse`** (`docintel_core.adapters.types`) — embedded in `GenerationResult.completion` (D-17). Phase 10 sources `cost_usd` / `latency_ms` / `model` per-call directly.
- **`RetrievedChunk`** (`docintel_core.types`) — Phase 5 D-03 shape. Phase 6 D-14 reads `text`, `chunk_id`, `ticker`, `fiscal_year`, `item_code` for the context block.
- **`JudgeVerdict`** (`docintel_core.adapters.types`) — shape `{score: float, passed: bool, reasoning: str, unsupported_claims: list[str]}` is the structured-output JSON schema target for D-09.
- **`_STUB_REFUSAL` + `_CHUNK_RE` in `adapters/stub/llm.py`** — Phase 2 D-16 already locks the bracket regex and the refusal-sentinel pattern. Phase 6 D-12 updates the sentinel VALUE to the new canonical text; D-11 keeps the regex pattern but moves the canonical definition to `docintel_generate.parse._CHUNK_RE`.
- **`_JUDGE_SYSTEM_PROMPT` + `_build_judge_prompt` + `_SCORE_PATTERN` in `adapters/real/judge.py`** — Phase 2 placeholder. Phase 6 D-09 migrates the prompt + replaces the parser with structured output.
- **`structlog.stdlib.get_logger(__name__)`** — every adapter / retriever module uses this pattern. Phase 6's `Generator` follows verbatim.
- **`packages/docintel-retrieve/pyproject.toml`** — minimal pyproject template for the new `docintel-generate` package (one workspace dep, `numpy` re-pin if needed, hatchling build backend).
- **`configure_logging` + `merge_contextvars`** — Phase 12 binds `trace_id` here later. Phase 6 emits structured fields so OBS-01 lands without retrofit.

### Established Patterns

- **One package per workspace concern** — `docintel-generate` is the 8th package (core / api / ui / eval / ingest / index / retrieve / generate). Workspace pyproject's `packages/*` glob picks it up automatically.
- **Lazy imports for heavy deps in the `real` branch** (Phase 2 D-12) — `Generator` itself imports only from `docintel-core` + `docintel-retrieve` (cheap modules). Heavy deps (anthropic/openai SDKs) ride inside `bundle.llm`, which the factory caller already constructed.
- **Single env reader (FND-11)** — Phase 6 adds NO new Settings fields. Provider switching reuses `llm_provider` + `llm_real_provider` (Phase 2 D-09).
- **`.name` property on every adapter** — Phase 6's `Generator` does NOT need `.name` (it's not stored in the manifest; the manifest sources `generator.name` from `bundle.llm.name`, plus `prompt_version_hash` from `docintel_generate.prompts.PROMPT_VERSION_HASH`).
- **Per-package Dockerfile target** (Phase 1) — `docintel-generate` is library-only (no CLI in v1); imported by `docintel-api` (Phase 13) and `docintel-eval` (Phase 10). No new Dockerfile target.
- **Pinned deps + uv.lock regen + uv lock --check CI gate** (FND-09) — `docintel-generate/pyproject.toml` pins `docintel-core` + `docintel-retrieve` workspace deps. `uv.lock` regenerated as part of Phase 6.
- **Tenacity wrap discipline** — Phase 6 adds NO new wrap sites. `bundle.llm.complete()` is already wrapped (Phase 2 D-18). `scripts/check_adapter_wraps.sh` continues to enforce; `scripts/check_prompt_locality.sh` (D-04) is a NEW independent gate.
- **CI grep gates** — Phase 6 is the FOURTH grep gate (`check_adapter_wraps.sh`, `check_index_wraps.sh`, `check_ingest_wraps.sh`, `check_prompt_locality.sh`). Pattern + exit codes + allowlist policy are all consistent.
- **JSONL fixture / data layout** (Phase 3 D-15) — Phase 6 has no on-disk data layout. Stub-mode tests embed prompts inline (allowlisted via `tests/**` in D-05).
- **Pydantic v2 + `frozen=True` for shared contracts** — `RetrievedChunk` (Phase 5 CD-02), `IndexManifest` polymorphic validator (Phase 4 D-13). `GenerationResult` (D-17) follows.

### Integration Points

- **`Settings.llm_provider`** → `make_generator(cfg)` factory dispatch (the seam). Already wired in `make_adapters(cfg)` + `make_index_stores(cfg)` + `make_retriever(cfg)` — `make_generator` composes them.
- **`AdapterBundle.llm.complete(prompt, system) -> CompletionResponse`** → Phase 6's synthesis call path. The `system` parameter carries `SYNTHESIS_PROMPT`; the `prompt` parameter carries the formatted `<context>` block + question.
- **`AdapterBundle.judge.judge(prediction, reference, rubric) -> JudgeVerdict`** → Phase 9's path. Phase 6 only changes what's IN the prompt the judge LLM is called with (D-09 migration); the protocol stays.
- **`Retriever.search(query, k) -> list[RetrievedChunk]`** → Phase 6's retrieval seam in `Generator.generate` Step A. Already exists; Phase 6 just calls it.
- **`GenerationResult` (NEW)** → consumed by Phase 7 `Answer` wrapper, Phase 9 metrics, Phase 10 eval reports, Phase 13 API+UI. Lives in `docintel_core.types` so every later phase imports without depending on `docintel-generate`.
- **`PROMPT_VERSION_HASH`** (NEW, in `docintel_generate.prompts`) → Phase 10 eval-report manifest header per EVAL-02. Per-prompt hashes (`_SYNTHESIS_HASH` etc.) → emitted in `generator_completed` structlog for ablation localisation.
- **`structlog` `generator_completed` log line** (NEW) → Phase 9 MET-05 (per-stage latency p50/p95 + $/query); Phase 9 MET-03 (faithfulness rate); Phase 11 ablation reports diff fields across runs; Phase 12 binds `trace_id` via `contextvars`.
- **`scripts/check_prompt_locality.sh`** (NEW) → CI grep gate enforcing GEN-01 every PR. Independent of the three existing wrap gates.

</code_context>

<specifics>
## Specific Ideas

- **`docintel-generate` is intentionally the LAST workspace package added before Phase 13.** Phases 7 (Answer schema), 8 (Ground truth), 9 (Metrics), 10 (Eval harness) all live inside existing packages (`docintel-core` for schemas, `docintel-eval` for the CLI + report writer). The 8-package count holds steady from Phase 6 through Phase 13. This is a deliberate stop on package proliferation — the workspace shape is the artifact, not a backlog.
- **The single-prompt-handles-both-comparative-and-factual choice is load-bearing for the demo.** The hero question ("Which of these companies grew R&D while margins shrank in 2023?") is multi-hop comparative across companies — the synthesis prompt has to handle that AND the single-doc factual case from Phase 8's ground-truth set under the same template. Phase 9 measurement will tell us if this holds; if not, the deferred-idea "per-question-type prompt routing" is the lever.
- **The refusal sentinel `I cannot answer this question from the retrieved 10-K excerpts.` is intentionally professional, not playful.** The demo is for recruiters + senior AI engineers. The refusal must read as "the system is being careful" not "the system is broken." This is also why Phase 2's `[STUB REFUSAL]`-bracketed sentinel doesn't ship — that looks like debug output in a hero GIF.
- **The judge migration (D-09) happens at Phase 6 specifically because of the manifest hash.** EVAL-02's report manifest carries `prompt_version_hash` — every report written before Phase 9's faithfulness work would have a different hash than every report after, making bisection harder. Migrating now stabilizes the hash before Phase 8/9/10 start generating reports.
- **`GenerationResult` carries `retrieved_chunks` and `completion` as full objects, not summaries.** This is intentional. Phase 7's `Answer.citations` needs `RetrievedChunk.char_span_in_section` (the citation anchor); Phase 13's UI needs `RetrievedChunk.text` for the hover; Phase 10's report needs `completion.cost_usd` + `completion.latency_ms` + `completion.model`. Carrying the full objects (frozen, immutable) means downstream phases never have to re-retrieve or re-call the LLM to enrich the result.
- **The dual-layer refusal (D-10 + D-11) cashes the two failure modes the demo has to handle.** Hard zero-chunk fires when retrieval genuinely returns nothing (cold-start vocab, OOC topic that BM25 + dense both whiff on). LLM-driven refusal fires when retrieval returns plausibly-relevant chunks but the LLM correctly recognises they don't answer the question. The hero GIF's out-of-corpus question demo is the LLM-driven path — it's the more impressive failure mode to surface in a recruiting context (it says "the LLM is grounded, not just templating").

</specifics>

<deferred>
## Deferred Ideas

- **Per-question-type prompt routing** (`FACTUAL_PROMPT`, `COMPARATIVE_PROMPT`, `REFUSAL_PROMPT`). Considered but not picked — single synthesis prompt handles both factual and comparative if the prompt is well-engineered (CD-01). Tracked here as the lever if Phase 9 faithfulness or citation-accuracy metrics show the single prompt underperforms on comparative questions. The seam to retrofit: add a `prompt_template` parameter to `Generator.generate()` with a default of `SYNTHESIS_PROMPT`.
- **Footnote-style `[1]` citations with mapping section.** Considered for D-10. Not picked — adds two-pass parsing (text + reference block) that Phase 7's Citation parser would have to mirror. The bracket pattern Phase 2 D-16 locked is the simplest contract. Phase 13 UI can layer a presentational transform on `[chunk_id]` if needed without changing the eval contract.
- **Score-threshold refusal gate.** Considered for D-10. Not picked — rerank scores are not calibrated across stub vs real (stub cosine over hash-vectors vs bge-reranker-base logits); a threshold that works for stub doesn't work for real. The hard zero-chunk + LLM-driven dual layer is provider-agnostic.
- **Question-aware refusal text** (refusal echoes the topic). Considered for D-11. Not picked — LLM occasionally hallucinates the echo when refusing, defeating the refusal. Single sentinel string is grep-detectable and Phase 7-parseable.
- **Re-prompting on missing citations** (validator that asks the LLM to re-emit with citations). Considered for D-13. Not picked — blows up `cost_usd` + `latency_ms`; defeats Phase 9's faithfulness measurement (you can't measure what you're forcing the model to fix).
- **Stripping uncited sentences from the response.** Considered for D-13. Not picked — hides faithfulness regressions; user sees mysteriously-truncated answers.
- **Generator owning retrieval AND generation as a single `.answer(query)` seam.** Considered for D-15. Not picked — collapses Phase 5's `.search()` seam, which is used by Phase 10 (eval reports the retrieval signal separately from the generation signal) and Phase 11 (ablation experiments swap retrievers). The seam is more valuable than the API ergonomics gain.
- **Already-shaped `Answer` (Phase 7 schema) as the Phase 6 return shape.** Considered for D-17. Not picked — ROADMAP locks Phase 7 as a separate phase (ANS-01..03 with quote-span Citation enrichment + `confidence` field). Folding Phase 7 into Phase 6 widens scope and complicates the confidence-field design (confidence is a Phase 7 concern, sourced partially from Phase 9 metrics retrofitted onto the schema).
- **`make_generator(cfg)` factory-level cache.** Considered for CD-05. Not picked — Phase 13 FastAPI will `lru_cache` the constructed `Generator`; Phase 10 eval harness constructs once per run. Mirrors `make_adapters(cfg)` precedent (no factory cache).
- **Async / streaming generator API.** Out of scope for v1 — Phase 2 D-08 locked sync-only. The eval harness is batch; FastAPI in Phase 13 wraps sync calls in a thread pool. Async / streaming is explicit v2 work.
- **Three-provider judge rotation** (e.g., add a third judge family). Out of scope for Phase 6; deferred from Phase 2 already.
- **Re-tokenize check on the synthesis-prompt context-window budget.** Considered for CD-06. Not picked — K=5 × 500 tokens is well under any frontier model's context; planner verifies during execution by logging actual `prompt_tokens`. Tracked here if a future expansion of K (Phase 11 ablation) ever bumps into a window limit.

</deferred>

---

*Phase: 6-generation*
*Context gathered: 2026-05-15*
