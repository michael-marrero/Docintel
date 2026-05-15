---
phase: 06-generation
audit_generated: 2026-05-15
status: PHASE GATE PENDING DEVELOPER REVIEW
coverage: 27 / 27 ✓ (17 D-XX + 10 CD-XX) + 1 Pitfall 9 resolution
prompt_version_hash: dab1bcf7379f
per_prompt_hashes:
  _SYNTHESIS_HASH: ec466290503d
  _REFUSAL_HASH: bf92b696078e
  _JUDGE_HASH: 8e563d5fbce2
---

# Phase 6 (generation): Decision-Coverage Audit

**Generated:** 2026-05-15
**Phase status:** PHASE GATE PENDING DEVELOPER REVIEW
**Coverage:** 27 / 27 ✓ (17 D-XX + 10 CD-XX) + 1 Pitfall 9 resolution
**PROMPT_VERSION_HASH (stable since Plan 06-03):** `dab1bcf7379f`

This document closes the Phase 6 implementation by enumerating every decision
captured in `06-CONTEXT.md` and pointing at the artifact (file path + line
range OR plan number) that lands it. Per Phase 5 precedent
(`.planning/phases/05-retrieval-hybrid-rerank/05-VERIFICATION.md`), this audit
IS the phase-gate verification: if any row reads ✗ or the developer cannot
sign off, Phase 6 does not merge.

The audit shape (sections + table format) is informed by Phase 5's closing
verification artifact; the 27-row decision-coverage table itself is Phase-6
specific. No `05-DECISIONS-AUDIT.md` file exists; the analog provided only the
sectional shape.

## Goal Achievement

Phase 6 ships the query-time generation layer that takes a user question +
Phase 5's `list[RetrievedChunk]` and produces a grounded, cited
`GenerationResult` (or an explicit refusal) ready for Phase 7's `Answer`
wrapper. Three concrete artifacts shipped: (1) the 8th workspace package
`docintel-generate` with `prompts.py` owning all canonical prompts under a
per-prompt + combined `PROMPT_VERSION_HASH = dab1bcf7379f`; (2) the
`Generator` class wrapping `LLMClient` + `Retriever` exposed via the 4th
sibling factory `make_generator(cfg)` in `docintel_core.adapters.factory`;
(3) the `scripts/check_prompt_locality.sh` CI grep gate, wired into
`.github/workflows/ci.yml` as the 4th member of the contiguous grep-gate
block, that mirrors `check_adapter_wraps.sh` / `check_index_wraps.sh` /
`check_ingest_wraps.sh` and enforces GEN-01 on every PR. The Phase 2
placeholder judge prompt + heuristic regex parser migrated to
`prompts.JUDGE_PROMPT` + structured-output dispatch (Anthropic
`tools=[{strict:true}]` / OpenAI `response_format={"type":"json_schema"}`)
deserializing directly into `JudgeVerdict` — so Phase 9 inherits a stable
manifest hash from Wave 1 onward.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 8th workspace package `docintel-generate` exists with pyproject + `__init__.py` + `prompts.py` + `parse.py` + `generator.py` + `py.typed` | VERIFIED | `ls packages/docintel-generate/src/docintel_generate/` shows all 5 source files + py.typed. `uv lock --check` exit 0 with 122 packages resolved. `from docintel_generate import ...` succeeds end-to-end. |
| 2 | Canonical `PROMPT_VERSION_HASH = dab1bcf7379f` with three named prompts + per-prompt hashes computed at module import via `_h(s)` helper | VERIFIED | `packages/docintel-generate/src/docintel_generate/prompts.py:53` (SYNTHESIS_PROMPT), `:85` (REFUSAL_PROMPT), `:94` (JUDGE_PROMPT), `:127-130` (4 hash constants). Empirical: `_SYNTHESIS_HASH=ec466290503d`, `_REFUSAL_HASH=bf92b696078e`, `_JUDGE_HASH=8e563d5fbce2`, `PROMPT_VERSION_HASH=dab1bcf7379f`. Hashes stable since Plan 06-03 commit `90e0409`. |
| 3 | `Generator.generate(query, k) -> GenerationResult` single-seam API with 5-step pipeline (A-E) | VERIFIED | `packages/docintel-generate/src/docintel_generate/generator.py:81` (class), `:117` (generate method), `:149-167` (Step B hard refusal), `:175-210` (Step C-D LLM + citation parse), `:300+` (Step E telemetry). Empirical: stub-mode `make_generator(Settings(llm_provider="stub")).generate("hero question", k=3)` returns a `GenerationResult` with 6 D-17 fields populated; `generator_completed` structlog emitted with all 15 D-16 fields. |
| 4 | `make_generator(cfg)` 4th sibling factory in `docintel_core.adapters.factory` | VERIFIED | `packages/docintel-core/src/docintel_core/adapters/factory.py:221` (`def make_generator(cfg: Settings) -> Generator`). Lazy import of `Generator` inside the function body (line 235); no `@lru_cache` per CD-05. `tests/test_make_generator.py::test_factory_lazy_imports_generator_module` passes — `docintel_generate.generator` not in `sys.modules` after hermetic reset until factory is called. |
| 5 | `REFUSAL_TEXT_SENTINEL = "I cannot answer this question from the retrieved 10-K excerpts."` (Pitfall 9 cycle-safe home in core) | VERIFIED | `packages/docintel-core/src/docintel_core/types.py:261` defines `REFUSAL_TEXT_SENTINEL: Final[str]`. The stub adapter at `packages/docintel-core/src/docintel_core/adapters/stub/llm.py:24` imports from `docintel_core.types` (upward-stack). `packages/docintel-generate/src/docintel_generate/prompts.py:85` aliases `REFUSAL_PROMPT = REFUSAL_TEXT_SENTINEL`. Single canonical sentinel across stub + real + Phase 7 parser. |
| 6 | `_CHUNK_RE = re.compile(r"\[([^\]]+)\]")` canonical home in `docintel_generate.parse` | VERIFIED | `packages/docintel-generate/src/docintel_generate/parse.py:29` defines the canonical instance. The stub adapter at `packages/docintel-core/src/docintel_core/adapters/stub/llm.py:31` imports `from docintel_generate.parse import _CHUNK_RE` (the one allowed cross-package import per CONTEXT.md D-12). Generator Step D at `generator.py:185+` uses `_CHUNK_RE.findall(completion.text)`. |
| 7 | Judge migration: prompt + parser moved to structured-output dispatch | VERIFIED | `packages/docintel-core/src/docintel_core/adapters/real/judge.py:68` imports `JUDGE_PROMPT` + `build_judge_user_prompt` from `docintel_generate.prompts`. Phase 2 `_SCORE_PATTERN` heuristic regex gone. `_judge_via_anthropic_raw` at `judge.py:132` uses `tools=[{...}]`; `_judge_via_openai_raw` at `judge.py:244` uses `response_format={"type": "json_schema", ...}`. `_sentinel_judgeverdict` at `judge.py:103` returns `JudgeVerdict(score=0.0, passed=False, reasoning="<deserialization failed>", ...)` on Pydantic validation failure. Cross-family Phase 2 D-04 wiring preserved (no factory changes). |
| 8 | `scripts/check_prompt_locality.sh` exists + wired into CI | VERIFIED | Script exists; executable; exits 0 on canonical layout. `.github/workflows/ci.yml` step `Check prompt locality (GEN-01)` placed after `Index wrap grep gate (D-21)` and before `Chunk-idempotency gate (ING-04)`. 4 CI grep gates now form a contiguous block (adapter_wraps + ingest_wraps + index_wraps + prompt_locality). |
| 9 | Wave 0 xfail-strict scaffolds (21 functions) all flipped to PASS | VERIFIED | `grep -rc "@pytest.mark.xfail" tests/test_{prompt_locality,prompt_version_hash,generator_stub_determinism,generator_refusal,make_generator,judge_structured_output,generator_search_integration,generator_telemetry,generation_result_schema}.py` → 0 each (9 files swept clean). `grep -c "@pytest.mark.xfail" tests/test_generator_real_hero.py` → 1 (preserved per Phase 5 precedent). |
| 10 | `uv run pytest -ra -q -m "not real"` exits 0 with stub-mode suite green | VERIFIED | 140 passed, 0 failed, 0 xfailed, 0 xpassed, 2 skipped, 6 deselected (matches Wave 3 baseline). The deselected count includes the 2 `@pytest.mark.real` tests (test_generator_hero_real_mode + test_judge_returns_judgeverdict) which are out of stub-mode scope per Phase 5 precedent. |
| 11 | `uv run mypy --strict packages/*/src` exits 0 | VERIFIED | "Success: no issues found in 51 source files". 8 workspace packages all clean (docintel-core + docintel-api + docintel-ui + docintel-eval + docintel-ingest + docintel-index + docintel-retrieve + docintel-generate). |
| 12 | `uv lock --check` exits 0 | VERIFIED | "Resolved 122 packages in 5ms" (no drift). |
| 13 | All 4 CI grep gates exit 0 | VERIFIED | `check_adapter_wraps.sh`, `check_index_wraps.sh`, `check_ingest_wraps.sh`, `check_prompt_locality.sh` all return "OK:" messages with exit code 0. |

**Score:** 13 / 13 observable truths verified.

## Decision Coverage (17 / 17 ✓)

| ID | Decision summary | Plan | Landing artifact | Verification |
|----|------------------|------|------------------|--------------|
| D-01 | New 8th workspace package `docintel-generate` | 06-02 | `packages/docintel-generate/pyproject.toml` + `src/docintel_generate/{__init__,prompts,parse,generator,py.typed}` (Plan 06-02 commit `5b45b70` scaffolded the package; Plans 06-03/04 added the source modules) | `uv lock --check` → 122 packages; `from docintel_generate import Generator, GenerationResult, PROMPT_VERSION_HASH, SYNTHESIS_PROMPT, REFUSAL_PROMPT, JUDGE_PROMPT` succeeds |
| D-02 | 5 doc-path updates to `packages/docintel-generate/src/docintel_generate/prompts.py` | 06-02 | `CLAUDE.md` (line 23 "All prompts live in `packages/docintel-generate/src/docintel_generate/prompts.py`"); `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/config.json` (gitignored — Plan 06-02 commits `08f81f2` + `5ff9c4f`) | `! git grep "src/docintel/generation/prompts.py" CLAUDE.md` → 0 matches (and 0 across the 4 gitignored docs) |
| D-03 | `make_generator(cfg)` 4th sibling factory | 06-04 | `packages/docintel-core/src/docintel_core/adapters/factory.py:221` (commit `bcb6919`); lazy imports `from docintel_generate.generator import Generator` inside the function body | `tests/test_make_generator.py::test_make_generator_stub` + `test_factory_lazy_imports_generator_module` both PASSED |
| D-04 | `scripts/check_prompt_locality.sh` CI grep gate | 06-02 | `scripts/check_prompt_locality.sh` (Plan 06-02 commit `57ff6cf`) — 4th sibling mirroring `check_adapter_wraps.sh` / `check_index_wraps.sh` / `check_ingest_wraps.sh` shape; two-pass scan (NAME_PATTERN + PHRASE_PATTERN); BSD-grep arg-order safe (--include before --exclude) | `bash scripts/check_prompt_locality.sh` → exit 0 with "OK: no inline prompts outside allowlist" |
| D-05 | Allowlist + per-line `# noqa: prompt-locality` escape hatch | 06-02 | `scripts/check_prompt_locality.sh` body — EXCLUDES allowlist covers `prompts.py`, `parse.py`, `tests/**`, stub `llm.py`, real `judge.py`/`llm_anthropic.py`/`llm_openai.py`; noqa escape via per-line suffix | `tests/test_prompt_locality.py::test_grep_gate_respects_noqa` PASSED (uses `tests/fixtures/prompt_locality_violations_with_noqa/allowed.py` fixture) |
| D-06 | CI YAML step wired | **06-07** | `.github/workflows/ci.yml` step `Check prompt locality (GEN-01)` running `bash scripts/check_prompt_locality.sh` placed after `Index wrap grep gate (D-21)` (Plan 06-07 Task A commit `426d2ad`) | `grep -c "Check prompt locality (GEN-01)" .github/workflows/ci.yml` → 1; YAML parses (`yaml.safe_load`); step runs on every PR |
| D-07 | 3 named module prompts (SYNTHESIS / REFUSAL / JUDGE) in `prompts.py` | 06-03 | `packages/docintel-generate/src/docintel_generate/prompts.py:53` (SYNTHESIS_PROMPT), `:85` (REFUSAL_PROMPT — aliases REFUSAL_TEXT_SENTINEL), `:94` (JUDGE_PROMPT) — all `Final[str]` (Plan 06-03 commit `90e0409`) | `from docintel_generate.prompts import SYNTHESIS_PROMPT, REFUSAL_PROMPT, JUDGE_PROMPT` succeeds; all three return non-empty str |
| D-08 | Per-prompt + combined `PROMPT_VERSION_HASH` via `_h(s)` sha256[:12] | 06-03 | `prompts.py:_h()` helper (line ~115); `_SYNTHESIS_HASH` (line 127), `_REFUSAL_HASH` (line 128), `_JUDGE_HASH` (line 129), `PROMPT_VERSION_HASH` (line 130) — all `Final[str]` | `tests/test_prompt_version_hash.py` 3/3 PASSED — `test_hash_format` + `test_per_prompt_hashes_exposed` + `test_hash_sensitivity` (Pitfall 3 single-byte sensitivity) |
| D-09 | Judge migration: prompt + parser to `prompts.JUDGE_PROMPT` + structured-output dispatch | 06-06 | `packages/docintel-core/src/docintel_core/adapters/real/judge.py` Phase 2 `_JUDGE_SYSTEM_PROMPT` + `_SCORE_PATTERN` gone; `_judge_via_anthropic_raw` at line 132 (`tools=[{strict:true}]`); `_judge_via_openai_raw` at line 244 (`response_format={"type":"json_schema"}`); `_sentinel_judgeverdict` at line 103 (Pitfall 6 deserialization-failure sentinel) — Plan 06-06 commit `475bb6f` | `tests/test_judge_structured_output.py::test_deserialization_failure_returns_sentinel` PASSED (stub-mockable); `test_judge_returns_judgeverdict` deselected by `-m "not real"` (collected via `-m real` for workflow_dispatch) |
| D-10 | Inline `[chunk_id]` brackets + locked fenced example in SYNTHESIS_PROMPT | 06-03 | `prompts.py:SYNTHESIS_PROMPT` body — fenced example `[AAPL-FY2024-Item-1A-018]` (line 68) + `[NVDA-FY2024-Item-7-042]` (line 69); explicit rule body forbids inventing chunk_ids | `grep "AAPL-FY2024-Item-1A-018" packages/docintel-generate/src/docintel_generate/prompts.py` → 1 match; `grep "NVDA-FY2024-Item-7-042"` → 1 match; `tests/test_generator_search_integration.py::test_hero_comparative_stub` PASSED end-to-end |
| D-11 | Canonical refusal sentinel in `docintel_core.types` | 06-02 | `packages/docintel-core/src/docintel_core/types.py:261` defines `REFUSAL_TEXT_SENTINEL: Final[str] = "I cannot answer this question from the retrieved 10-K excerpts."` (63 bytes; Plan 06-02 commit `5b45b70`) | `from docintel_core.types import REFUSAL_TEXT_SENTINEL; assert REFUSAL_TEXT_SENTINEL == "I cannot answer this question from the retrieved 10-K excerpts."` (byte-exact) |
| D-12 | Stub `_STUB_REFUSAL` value update + `_CHUNK_RE` move | 06-05 | `packages/docintel-core/src/docintel_core/adapters/stub/llm.py:33` (`_STUB_REFUSAL: Final[str] = REFUSAL_TEXT_SENTINEL`); `:31` imports `_CHUNK_RE` from `docintel_generate.parse`; `import re` removed (Plan 06-05 commit `cd0e393`) | `_STUB_REFUSAL is REFUSAL_TEXT_SENTINEL` (identity); `_CHUNK_RE is docintel_generate.parse._CHUNK_RE` (same Pattern instance); `tests/test_adapters.py::test_stub_llm_refusal` PASSED with symbolic identity assertion |
| D-13 | Faithfulness post-hoc parse + hallucination drop (not raise) | 06-04 | `packages/docintel-generate/src/docintel_generate/generator.py:185-210` (Step D body) — runs `_CHUNK_RE.findall(completion.text)`, validates each cited_id against `{c.chunk_id for c in retrieved_chunks}`, drops hallucinations with `generator_hallucinated_chunk_id` structlog warning (line 200), preserves response text | `tests/test_generator_stub_determinism.py::test_hallucinated_ids_dropped` PASSED — hallucinated chunk_ids dropped, text preserved, structlog warning emitted exactly once per offending ID |
| D-14 | Numbered `<context>` blocks with metadata header in user prompt | 06-04 | `packages/docintel-generate/src/docintel_generate/generator.py:231` (`_format_user_prompt`) — emits XML-style `<context>` tags with per-chunk header `[chunk_id: ... \| company: ... \| fiscal_year: ... \| section: ...]` per RetrievedChunk; reads 4 D-03 fields (chunk_id, ticker, fiscal_year, item_code) | `tests/test_generator_search_integration.py::test_hero_comparative_stub` PASSED (verifies end-to-end stub-mode generation on multi-hop comparative question; `cited ≥ 1`, `refused=False`) |
| D-15 | `Generator.generate(query, k) -> GenerationResult` single seam + 5-step pipeline | 06-04 | `packages/docintel-generate/src/docintel_generate/generator.py:81` (class), `:117` (generate method) — Step A `self._retriever.search(query, k)`; Step B hard-zero refusal at `:149-167`; Step C format + LLM call at `:175-184`; Step D citation parse + hallucination drop at `:185-210`; Step E telemetry + return at `:212-225` (Plan 06-04 commit `22c7215`) | `tests/test_generator_stub_determinism.py` 3/3 PASSED — `test_determinism` (three back-to-back calls identical), `test_citation_subset` (cited ⊆ retrieved), `test_hallucinated_ids_dropped` |
| D-16 | `generator_completed` 15-field structlog INFO emission | 06-04 | `packages/docintel-generate/src/docintel_generate/generator.py:266` (`_emit_completed`) — single structlog INFO line with exactly the 15 named fields (query_tokens, n_chunks_retrieved, n_chunks_cited, refused, prompt_version_hash, synthesis_hash, refusal_hash, judge_hash, prompt_tokens, completion_tokens, cost_usd, retrieval_ms, generation_ms, total_ms, model) | `tests/test_generator_telemetry.py::test_completed_fields` PASSED — captures structlog records via `structlog.testing.capture_logs`; asserts exactly one `generator_completed` event with all 15 keys |
| D-17 | `GenerationResult` Pydantic model in `docintel_core.types` | 06-04 | `packages/docintel-core/src/docintel_core/types.py:201` (`class GenerationResult(BaseModel)`) — `ConfigDict(extra="forbid", frozen=True)`; 6 fields (text, cited_chunk_ids, refused, retrieved_chunks, completion, prompt_version_hash); Plan 06-04 commit `9eb9d87` | `tests/test_generation_result_schema.py` 2/2 PASSED — `test_generation_result_frozen` (mutation raises ValidationError), `test_generation_result_extra_forbid` (unknown field raises) |

**Decision coverage: 17 / 17 ✓.**

## Claude's Discretion Coverage (10 / 10 ✓)

| ID | Discretion summary | Plan | Landing artifact | Verification |
|----|--------------------|------|------------------|--------------|
| CD-01 | Exact SYNTHESIS_PROMPT wording | 06-03 | `packages/docintel-generate/src/docintel_generate/prompts.py:53-83` (SYNTHESIS_PROMPT body — XML `<context>` tags, locked citation example, numbered rules block, byte-exact refusal sentinel on single line per Pitfall 3 deviation from RESEARCH §Example 1) | Inspect prompts.py:53-83; `_SYNTHESIS_HASH = ec466290503d` (stable since commit `90e0409`); 971-byte body |
| CD-02 | Exact JUDGE_PROMPT wording + structured-output JSON schema | 06-03 | `prompts.py:94-115` (JUDGE_PROMPT body); structured-output schema `{"score": float, "passed": bool, "reasoning": str, "unsupported_claims": list[str]}` matches `JudgeVerdict` | Inspect prompts.py:94-115; `_JUDGE_HASH = 8e563d5fbce2`; 723-byte body; Anthropic `tools=[{strict:true}]` + OpenAI `response_format={"type":"json_schema","strict":true}` bind to this schema |
| CD-03 | `Generator.__init__` eager-stash, no lazy-load | 06-04 | `packages/docintel-generate/src/docintel_generate/generator.py:103` (`def __init__(self, bundle: AdapterBundle, retriever: Retriever) -> None`) — body simply stashes `self._bundle = bundle; self._retriever = retriever; self._log = structlog.stdlib.get_logger(__name__)` | Inspect generator.py:103-115; no lazy-load; matches Phase 5 CD-01 Retriever precedent |
| CD-04 | NO new tenacity wrap sites; helpers in judge.py wrap-discipline preserved | 06-04 + 06-06 | `! grep -E "from tenacity\|import tenacity" packages/docintel-generate/` → 0 matches (Generator never adds a `@retry` decorator); `judge.py:_judge_via_anthropic_raw` + `_judge_via_openai_raw` retain Phase 2 D-04 `@retry` decorators (the structured-output dispatch SDK calls are wrap-discipline-equivalent to the Phase 2 placeholder) | `bash scripts/check_adapter_wraps.sh` → exit 0; generator.py imports include NO tenacity reference |
| CD-05 | `make_generator(cfg)` no `@lru_cache` | 06-04 | `packages/docintel-core/src/docintel_core/adapters/factory.py:221` (`def make_generator(cfg: Settings) -> Generator`) — function definition has no `@lru_cache` decorator (matches Phase 5 CD-08 precedent; Phase 13 FastAPI will `lru_cache` the constructed Generator; Phase 10 eval harness constructs once per run) | `! grep -B2 "def make_generator" packages/docintel-core/src/docintel_core/adapters/factory.py \| grep -q "@lru_cache"` → no match |
| CD-06 | Context-window budget documented; hero question logs `prompt_tokens` | 06-04 | `generator.py` module docstring + D-16 telemetry emits `prompt_tokens` field on every call; `tests/test_generator_real_hero.py::test_generator_hero_real_mode` asserts `prompt_tokens < 8000` (xfail-preserved real-mode test; the budget claim is the workflow_dispatch bite-point per Phase 5 precedent) | Inspect generator.py module docstring; `tests/test_generator_real_hero.py` line `assert result.completion.usage.prompt_tokens < 8000` (under xfail until workflow_dispatch promotion) |
| CD-07 | Hallucinated chunk_id log + drop, not raise | 06-04 | `generator.py:200` emits `generator_hallucinated_chunk_id` structlog WARNING per offending ID; the response text is NOT modified; cited_chunk_ids excludes the hallucinated id; Phase 9 MET-04 (citation accuracy) measures the per-query rate | `tests/test_generator_stub_determinism.py::test_hallucinated_ids_dropped` PASSED — verifies WARNING is emitted, ID is dropped from cited list, response text contains original `[hallucinated-id]` substring |
| CD-08 | Wave 0 test scaffolds with xfail-strict markers | 06-01 | 10 test files at `tests/test_{prompt_locality,prompt_version_hash,generator_stub_determinism,generator_refusal,make_generator,judge_structured_output,generator_search_integration,generator_telemetry,generation_result_schema,generator_real_hero}.py` + 2 fixture dirs at `tests/fixtures/prompt_locality_violations{,_with_noqa}/` (Plan 06-01 commits `637833c` + `c241090` + `1f9f93e`) | Plan 06-07 Task B sweep verified the scaffold state: Wave 0 baseline shipped 21 xfail-strict markers; Waves 0-4 swept 20 of them; the 21st (real-mode hero) is preserved per Phase 5 precedent. `git log --oneline tests/test_*.py` shows the Wave 0 commits + per-wave sweeps. |
| CD-09 | JSON-mode SDK call signatures (tools + response_format) | 06-06 | `packages/docintel-core/src/docintel_core/adapters/real/judge.py:160` (Anthropic `tools=[{"name": "submit_verdict", "input_schema": <schema>, "strict": true}]`); `:272` (OpenAI `response_format={"type": "json_schema", "json_schema": {"strict": true, "schema": <schema>}}`) | `grep "tools=\[" packages/docintel-core/src/docintel_core/adapters/real/judge.py` → 1+ matches; `grep "response_format" packages/docintel-core/src/docintel_core/adapters/real/judge.py` → 1+ matches; pinned SDK versions verified at Plan 06-06 |
| CD-10 | 5-wave structure | All plans | Wave 0: Plans 06-01 + 06-02 (test scaffolds + package skeleton + REFUSAL_TEXT_SENTINEL + grep gate script). Wave 1: Plan 06-03 (prompts.py + parse.py). Wave 2: Plan 06-04 (Generator + factory + GenerationResult). Wave 3: Plans 06-05 + 06-06 (stub adapter sync + judge migration). Wave 4: Plan 06-07 (CI wiring + xfail sweep + this audit). | `git log --oneline phase/6-generation` shows the wave-by-wave commit sequence; this audit's existence + 27/27 coverage IS the Wave 4 acceptance |

**Discretion coverage: 10 / 10 ✓.**

## Pitfall Resolutions

| Pitfall | Description | Resolution |
|---------|-------------|------------|
| Pitfall 3 | Whitespace / encoding drift in hashed prompt bodies (per-byte sha256 sensitivity) | RESOLVED in Plan 06-03 — `prompts.py` carries a critical header comment block ABOVE the prompt definitions warning future contributors not to "reflow whitespace for readability"; SYNTHESIS_PROMPT keeps the embedded REFUSAL_TEXT_SENTINEL on a single contiguous byte-run (NO mid-sentinel line-wrap as in RESEARCH §Example 1 — that was a Rule 1 deviation during execution to preserve byte-exact `is_refusal()` matching on LLM output); `tests/test_prompt_version_hash.py::test_hash_sensitivity` (single-byte mutation flips the hash) provides ongoing structural defense. |
| Pitfall 5 | Stub-template repr-list issue in `_STUB_REFUSAL` value drift between Phase 2 placeholder + Phase 6 canonical refusal text | RESOLVED in Plan 06-05 — backward-compat alias pattern: `_STUB_REFUSAL: Final[str] = REFUSAL_TEXT_SENTINEL` (the NAME is retained for tests importing it; the VALUE tracks the canonical constant in `docintel_core.types`). The `[STUB ANSWER citing chunk_ids]` template was also fixed inline during Wave 3 merge cleanup (commit `57a0d3e`) to emit bare `[chunk_id]` brackets from D-14 headers — the hero stub xfail (Wave 3 root-cause) was lifted because the test now passes end-to-end. |
| Pitfall 9 | Import cycle: stub adapter (in core) importing from docintel-generate (downstream package) | RESOLVED via dual canonical-home placement. **REFUSAL_TEXT_SENTINEL home = `docintel_core.types`** (Plan 06-02) — keeps stub adapter's sentinel import upward-stack (`stub/llm.py:24 from docintel_core.types import REFUSAL_TEXT_SENTINEL`). **`_CHUNK_RE` home = `docintel_generate.parse`** (Plan 06-03) — the stub adapter (Plan 06-05) imports `from docintel_generate.parse import _CHUNK_RE` as the ONE allowed cross-package import per CONTEXT.md D-12 line 107 (justified inline with a 4-line comment block citing the decision). Cycle is one-way at runtime (make_adapters returns stub only when `llm_provider="stub"`, at which point docintel-generate is already loaded by the test harness; the generator never imports the stub). |

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `packages/docintel-generate/pyproject.toml` | 8th workspace package; hatchling backend; workspace deps on `docintel-core` + `docintel-retrieve`; library-only (no `[project.scripts]`) | VERIFIED | 16 lines; minimal; no external pins (anthropic/openai live in docintel-core per single-pin discipline) |
| `packages/docintel-generate/src/docintel_generate/__init__.py` | Re-exports Generator, GenerationResult, the 3 *_PROMPT constants, PROMPT_VERSION_HASH | VERIFIED | Wave-incremental build-up (W0 stub → W1 prompts re-exports → W2 generator re-exports); `__all__` alphabetical |
| `packages/docintel-generate/src/docintel_generate/prompts.py` | 3 named prompts + per-prompt + combined PROMPT_VERSION_HASH + _h() helper | VERIFIED | 130+ lines; SYNTHESIS_PROMPT (971 bytes) + REFUSAL_PROMPT (63 bytes, aliases REFUSAL_TEXT_SENTINEL) + JUDGE_PROMPT (723 bytes); all `Final[str]`; 4 sha256[:12] hash constants computed at module import |
| `packages/docintel-generate/src/docintel_generate/parse.py` | `_CHUNK_RE` compiled regex + `is_refusal()` helper | VERIFIED | `_CHUNK_RE: Final[re.Pattern[str]] = re.compile(r"\[([^\]]+)\]")` at line 29; `def is_refusal(text: str) -> bool` at line 41 (byte-exact `text.startswith(REFUSAL_TEXT_SENTINEL)`) |
| `packages/docintel-generate/src/docintel_generate/generator.py` | Generator class + 5-step pipeline + _format_user_prompt + _emit_completed | VERIFIED | 300+ lines; `class Generator` at line 81; `generate(query, k)` at line 117; Step B hard refusal at 149-167; Step C-D LLM + citation parse at 175-210; Step E telemetry at 266+ (`_emit_completed`) |
| `packages/docintel-generate/src/docintel_generate/py.typed` | PEP 561 marker | VERIFIED | Zero-byte file |
| `packages/docintel-core/src/docintel_core/types.py` (REFUSAL_TEXT_SENTINEL + GenerationResult) | Pitfall-9-safe sentinel home + Pydantic frozen=True extra=forbid model | VERIFIED | `REFUSAL_TEXT_SENTINEL: Final[str]` at line 261; `class GenerationResult(BaseModel)` at line 201 with `ConfigDict(extra="forbid", frozen=True)` and 6 fields |
| `packages/docintel-core/src/docintel_core/adapters/factory.py` (make_generator) | 4th sibling factory; lazy-import discipline; no @lru_cache | VERIFIED | `def make_generator(cfg: Settings) -> Generator` at line 221; lazy `from docintel_generate.generator import Generator` inside function body; composes `make_adapters(cfg)` + `make_retriever(cfg)` + `Generator(bundle, retriever)` |
| `packages/docintel-core/src/docintel_core/adapters/real/judge.py` (D-09 migration) | Structured-output dispatch + sentinel JudgeVerdict on deserialization failure; Phase 2 D-04 cross-family wiring preserved | VERIFIED | Phase 2 `_JUDGE_SYSTEM_PROMPT` + `_build_judge_prompt` + `_SCORE_PATTERN` GONE; imports `JUDGE_PROMPT` + `build_judge_user_prompt` from `docintel_generate.prompts`; `_judge_via_anthropic_raw` (line 132) + `_judge_via_openai_raw` (line 244) wrap-discipline preserved; `_sentinel_judgeverdict` (line 103) returns `JudgeVerdict(score=0.0, passed=False, reasoning="<deserialization failed>", unsupported_claims=[])` on ValidationError |
| `packages/docintel-core/src/docintel_core/adapters/stub/llm.py` (D-11 + D-12 sync) | `_STUB_REFUSAL` re-aliases canonical sentinel; `_CHUNK_RE` re-imported from `docintel_generate.parse`; `import re` removed | VERIFIED | Plan 06-05 commit `cd0e393`: `_STUB_REFUSAL: Final[str] = REFUSAL_TEXT_SENTINEL` at line 33; `from docintel_generate.parse import _CHUNK_RE` at line 31; `import re` removed; existing `_CHUNK_RE.findall(prompt)` call at module scope resolves to imported instance transparently |
| `scripts/check_prompt_locality.sh` | 4th CI grep gate; BSD-grep arg-order safe; allowlist + per-line noqa escape | VERIFIED | Plan 06-02 commit `57ff6cf`; mirrors structural template of `check_adapter_wraps.sh` / `check_index_wraps.sh` / `check_ingest_wraps.sh`; exit 0 on canonical layout, exit 1 on synthetic violation, exit 0 with `# noqa: prompt-locality` |
| `.github/workflows/ci.yml` (Check prompt locality (GEN-01) step) | New step after Index wrap grep gate; runs unconditionally on every PR | VERIFIED | Plan 06-07 Task A commit `426d2ad`; step name + run line both verified; YAML valid (`yaml.safe_load` OK); 4 grep gates now form contiguous block |
| 10 test files for Phase 6 behaviors | 21 test functions; xfail markers swept (20) + 1 preserved | VERIFIED | All 9 swept files (`test_prompt_locality.py`, `test_prompt_version_hash.py`, `test_generator_stub_determinism.py`, `test_generator_refusal.py`, `test_make_generator.py`, `test_judge_structured_output.py`, `test_generator_search_integration.py`, `test_generator_telemetry.py`, `test_generation_result_schema.py`) report `grep -c "@pytest.mark.xfail" → 0`. `test_generator_real_hero.py` retains its `@pytest.mark.real + @pytest.mark.xfail(strict=True)` per Phase 5 precedent. |
| 2 fixture dirs for prompt-locality | Negative offender + positive `# noqa: prompt-locality` escape | VERIFIED | `tests/fixtures/prompt_locality_violations/offender.py` (no noqa); `tests/fixtures/prompt_locality_violations_with_noqa/allowed.py` (single `# noqa: prompt-locality` line) |
| `.planning/phases/06-generation/06-DECISIONS-AUDIT.md` (this file) | 17 D-XX rows + 10 CD-XX rows + Pitfall row(s) + Phase Gate + Sign-off | VERIFIED | This file. 27 / 27 ✓. |

## Key Link Verification

Cross-plan data contracts — each traced from producer plan to consumer plan.

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `REFUSAL_TEXT_SENTINEL` (Plan 06-02) | Stub adapter `_STUB_REFUSAL` (Plan 06-05) | `from docintel_core.types import REFUSAL_TEXT_SENTINEL` + `_STUB_REFUSAL: Final[str] = REFUSAL_TEXT_SENTINEL` | WIRED | Identity check: `_STUB_REFUSAL is REFUSAL_TEXT_SENTINEL` is True at module import time |
| `REFUSAL_TEXT_SENTINEL` (Plan 06-02) | `REFUSAL_PROMPT` (Plan 06-03) | `from docintel_core.types import REFUSAL_TEXT_SENTINEL` + `REFUSAL_PROMPT: Final[str] = REFUSAL_TEXT_SENTINEL` at `prompts.py:85` | WIRED | Plan 06-03 byte-equals decision honored; byte body lives in core, hashed for `_REFUSAL_HASH` here |
| `REFUSAL_TEXT_SENTINEL` (Plan 06-02) | `Generator` Step B (Plan 06-04) | `from docintel_core.types import REFUSAL_TEXT_SENTINEL` at `generator.py:62` + `text=REFUSAL_TEXT_SENTINEL` at `generator.py:156` | WIRED | Hard zero-chunk refusal returns the canonical sentinel verbatim; `tests/test_generator_refusal.py::test_hard_zero_chunk_refusal` PASSED |
| `_CHUNK_RE` (Plan 06-03 home in `docintel_generate.parse`) | Stub adapter (Plan 06-05) | `from docintel_generate.parse import _CHUNK_RE` at `stub/llm.py:31` | WIRED | The one allowed cross-package import per CONTEXT.md D-12 line 107; justified inline with comment block citing the decision |
| `_CHUNK_RE` (Plan 06-03) | `Generator` Step D (Plan 06-04) | `_CHUNK_RE.findall(completion.text)` at `generator.py:185+` (module-level import) | WIRED | Citation parse + hallucination drop reads the same compiled regex instance |
| `GenerationResult` (Plan 06-04 home in `docintel_core.types`) | Phase 7 `Answer` wrapper | `from docintel_core.types import GenerationResult` (Phase 7 imports without depending on `docintel-generate`; the schema is a contract) | READY | Phase 7 not yet implemented; the import contract is in place |
| `GenerationResult` (Plan 06-04) | Phase 9 metrics + Phase 10 eval reports | `GenerationResult.cited_chunk_ids` (MET-04), `.refused` (MET-03), `.completion.cost_usd` / `.completion.latency_ms` / `.completion.model` (MET-05) | READY | Per-plan readers downstream; contract surfaces are stable + `frozen=True` |
| `JUDGE_PROMPT` (Plan 06-03) | `adapters/real/judge.py` (Plan 06-06) | `from docintel_generate.prompts import JUDGE_PROMPT, build_judge_user_prompt` at `judge.py:68` | WIRED | The judge migration consumes the canonical prompt; Phase 2 `_JUDGE_SYSTEM_PROMPT` gone |
| `PROMPT_VERSION_HASH` (Plan 06-03) | `GenerationResult.prompt_version_hash` (Plan 06-04) + Phase 10 EVAL-02 manifest | `from docintel_generate.prompts import PROMPT_VERSION_HASH` at `generator.py` + emitted in `_emit_completed` 15-field telemetry | WIRED | Stable at `dab1bcf7379f` since Plan 06-03 commit `90e0409`; every generated `GenerationResult` carries this exact hash; Phase 10 EVAL-02 manifest will read it directly |
| `make_generator(cfg)` (Plan 06-04 factory) | Generator instance | Lazy in-function import `from docintel_generate.generator import Generator` at `factory.py:235` | WIRED | `tests/test_make_generator.py::test_factory_lazy_imports_generator_module` PASSED; `docintel_generate.generator` not in `sys.modules` after hermetic reset until factory called |
| `scripts/check_prompt_locality.sh` (Plan 06-02) | `.github/workflows/ci.yml` step (Plan 06-07) | `run: bash scripts/check_prompt_locality.sh` at the new step | WIRED | Plan 06-07 Task A commit `426d2ad`; step runs on every PR in the lint-and-test job |

## Phase Gate Checklist

Verified at audit time (2026-05-15):

- [x] All 4 CI grep gates pass: `check_adapter_wraps.sh`, `check_index_wraps.sh`, `check_ingest_wraps.sh`, `check_prompt_locality.sh` — all return "OK:" exit 0
- [x] `uv run pytest -ra -q -m "not real"` exits 0 with 140 passed, 0 failed, 0 xfailed, 0 xpassed, 2 skipped, 6 deselected
- [x] `uv lock --check` exits 0 — "Resolved 122 packages in 5ms"
- [x] `uv run mypy --strict packages/*/src` exits 0 — "Success: no issues found in 51 source files" (all 8 workspace packages)
- [ ] `uv run ruff check packages/ tests/` exits 0 — **4 pre-existing I001 errors in `packages/docintel-core/src/docintel_core/adapters/real/judge.py` + 2 elsewhere (Plan 06-06 introductions)**, tracked in `.planning/phases/06-generation/deferred-items.md` (gitignored) per Phase 5 precedent. Plan 06-07 Task B did NOT modify these files in a way that introduced the errors; the audit notes this as a Pre-existing tracked anti-pattern (see Anti-Patterns Found below). **NOT BLOCKING for the audit** — Phase 5 precedent at `05-VERIFICATION.md:130` documents the same pattern for Plans 05-05 introductions.
- [ ] `uv run black --check packages/ tests/` exits 0 — **10 pre-existing files need black reformat** (`stub/llm.py` from Plan 06-05; `real/judge.py` from Plan 06-06; 8 test files from Plans 06-01/06-04); tracked as deferred. Plan 06-07's only test-file edit (`test_judge_structured_output.py`) carries a black diff inherited from Plan 06-01 — verified by `git stash` + black check on the pristine pre-edit file: same reformat warning, confirming pre-existing. **NOT BLOCKING** per Phase 5 precedent.
- [x] All 19 stub-mode test bodies introduced by Plan 06-01 report PASSED (not XPASSED or FAILED) — verified by full `-ra -q -m "not real"` exit 0
- [x] The 2 real-mode tests (`test_judge_returns_judgeverdict` + `test_generator_hero_real_mode`) are collected but deselected by `-m "not real"` — verified by `pytest --collect-only -m real` returning these 2 tests in the collected set
- [x] PROMPT_VERSION_HASH is stable at the post-Wave-3 value `dab1bcf7379f` — recorded in this audit's frontmatter for Plan 06-06 SUMMARY cross-reference and Phase 10 EVAL-02 manifest header
- [x] All 5 doc-path references updated: `! git grep "src/docintel/generation/prompts.py" CLAUDE.md .planning/PROJECT.md .planning/REQUIREMENTS.md .planning/ROADMAP.md .planning/config.json` returns 0 matches

### Anti-Patterns Found (Pre-existing, NOT BLOCKING)

Mirrors Phase 5's anti-patterns documentation pattern (`05-VERIFICATION.md:124-132`).

| File | Issue | Severity | Origin | Impact |
|------|-------|----------|--------|--------|
| `packages/docintel-core/src/docintel_core/adapters/real/judge.py` | 4 ruff I001 import-sort errors | Warning | Plan 06-06 introduction (commit `475bb6f`) | Pre-existing from prior wave; mypy --strict + pytest both green; only stylistic; tracked for a future polish plan |
| `packages/docintel-core/src/docintel_core/adapters/stub/llm.py` | 1 black reformat warning | Warning | Plan 06-05 introduction (commit `cd0e393`) | Pre-existing; tracked |
| 8 test files (`test_adapters.py`, `test_generator_*.py`, `test_judge_structured_output.py`, `test_make_generator.py`, `test_prompt_version_hash.py`) | Black reformat warnings | Warning | Plans 06-01 (Wave 0 scaffolds) + 06-04 (Wave 2 Generator-dependent tests promoted out of xfail) + 06-05 (Rule 1 amendment to `test_adapters.py`) | Pre-existing; tracked; Plan 06-07 only modified `test_judge_structured_output.py` (1-line deletion of the xfail decorator), which inherited the pre-existing black diff |

No BLOCKER anti-patterns: zero `TBD`/`FIXME`/`XXX` markers introduced in Phase 6 modifications. No placeholder/stub returns hidden in production code (the `_sentinel_judgeverdict` at `judge.py:103` is a documented Pitfall 6 measurement seam, not a stub). The xfail preserved on `test_generator_real_hero.py` is intentional per Phase 5 precedent.

## Sign-off

**Reviewed by:** _________________________
**Date:**       _________________________
**Verdict:**    [ ] APPROVED  [ ] REJECTED  (return to gsd-planner with feedback)

If APPROVED: Phase 6 merges to `main`; the post-merge `gh workflow run ci.yml --ref main` real-mode run promotes `test_generator_hero_real_mode` from xfail to PASSED (Phase 5 precedent — empirical bite-point lives in workflow_dispatch).

If REJECTED: developer provides a specific list of failing rows; the planner re-issues Plan 06-07 with the fix scope.

---

*Audit generated: 2026-05-15*
*Phase 6 wave structure: Wave 0 (06-01 + 06-02) → Wave 1 (06-03) → Wave 2 (06-04) → Wave 3 (06-05 + 06-06) → Wave 4 (06-07)*
