# Phase 6: generation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-15
**Phase:** 6-generation
**Areas discussed:** Package home + prompts path, Prompt structure + judge migration, Generator API + return shape, Refusal triggers + citation format

---

## Package home + prompts path

### Q1 — Where should Phase 6's code physically live?

| Option | Description | Selected |
|--------|-------------|----------|
| 8th workspace package `docintel-generate` | `packages/docintel-generate/src/docintel_generate/`. Matches Phase 3/4/5 precedent. Most consistent long-term. | ✓ |
| Literal spec path `src/docintel/generation/` | Honors CLAUDE.md verbatim. Breaks workspace pattern; first non-package source file at repo root. | |
| Inside `docintel-core` | Next to placeholder judge prompts. Zero new packages but blurs core's "shared types/protocols/adapters" scope. | |

**User's choice:** 8th workspace package `docintel-generate`.
**Notes:** Aligns with the project-wide one-package-per-phase pattern (Phase 3 ingest / Phase 4 index / Phase 5 retrieve). Eliminates the need for the literal `src/docintel/` directory that never existed in this repo.

### Q2 — How should we reconcile CLAUDE.md / config.json / ROADMAP saying `src/docintel/generation/prompts.py`?

| Option | Description | Selected |
|--------|-------------|----------|
| Update docs to new path | Phase 6 plan also updates CLAUDE.md, config.json prompt_home, REQUIREMENTS GEN-01, ROADMAP, PROJECT.md. Single source of truth. | ✓ |
| Keep docs as-is, add note | Preserves historical pointer; invites confusion. | |
| Add path constant in `docintel_core` | Constant-based indirection; more plumbing for a sed-able problem. | |

**User's choice:** Update docs to new path.
**Notes:** Phase 6 plan rolls in one consolidated doc-update commit (planner picks the wave).

### Q3 — How should the CI grep gate (GEN-01) be enforced?

| Option | Description | Selected |
|--------|-------------|----------|
| `scripts/check_prompt_locality.sh` | Mirrors check_adapter_wraps.sh / check_index_wraps.sh / check_ingest_wraps.sh pattern. | ✓ |
| Pure regex grep in CI workflow | Inline grep step in ci.yml. Harder to evolve when false positives surface. | |
| AST-based check via small python tool | Walks ast.Constant in module-level assignments. Overkill at this scale. | |

**User's choice:** `scripts/check_prompt_locality.sh`.
**Notes:** Pattern-set finalised during planning; matches the 3-existing-wrap-gate convention.

### Q4 — What's the right exclusion policy for the prompt-locality grep?

| Option | Description | Selected |
|--------|-------------|----------|
| Allowlist by path + sentinel comment | Default-exclude prompts.py + tests/ + conftest.py; per-line `# noqa: prompt-locality` escape. | ✓ |
| Allowlist by path only | No per-line escape hatch; forces discipline but needs explicit carve-outs for stubs. | |
| Wholesale exclude all stub adapters | Looser; some stubs may drift into real-prompt territory. | |

**User's choice:** Allowlist by path + sentinel comment.
**Notes:** Outstanding exceptions remain grep-able via `grep -rn 'noqa: prompt-locality' packages/`.

---

## Prompt structure + judge migration

### Q1 — How should the prompts be structured in prompts.py?

| Option | Description | Selected |
|--------|-------------|----------|
| Three named prompts: synthesis, refusal, judge | Single synthesis covers factual + comparative; refusal explicit; judge migrates now. | ✓ |
| Single combined prompt with sections | One SYSTEM_PROMPT + USER_PROMPT_TEMPLATE. Refusal instructed inline. Less granular versioning. | |
| Per-question-type templates | FACTUAL/COMPARATIVE/REFUSAL/JUDGE. Routing machinery; premature when one prompt works. | |

**User's choice:** Three named prompts.
**Notes:** Single SYNTHESIS_PROMPT handles both factual and comparative; the LLM is instructed to ground and refuse if context insufficient. Judge migration deferred to be tracked in this same phase.

### Q2 — How should PROMPT_VERSION_HASH be computed and exposed?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-prompt + combined; SHA256 truncated to 12 hex | _SYNTHESIS_HASH/_REFUSAL_HASH/_JUDGE_HASH + combined PROMPT_VERSION_HASH. | ✓ |
| Single combined hash only | Simpler; loses signal when single prompt changes. | |
| Per-prompt hashes only, no combined | Most granular but bloats manifest header. | |

**User's choice:** Per-prompt + combined.
**Notes:** EVAL-02 manifest uses combined; ablation reports + structlog can isolate per-prompt. Computed at module import time.

### Q3 — Judge prompt migration scope?

| Option | Description | Selected |
|--------|-------------|----------|
| Migrate prompt + parser; defer rubric/scoring logic | Move _JUDGE_SYSTEM_PROMPT + _build_judge_prompt into prompts.py; replace heuristic _SCORE_PATTERN with structured JSON-mode output. | ✓ |
| Migrate prompt only; keep parser placeholder | Smaller Phase 6 scope but destabilizes manifest hash. | |
| Defer judge migration entirely to Phase 9 | Phase 6 ships only SYNTHESIS + REFUSAL; allowlist carve-out for judge.py. | |

**User's choice:** Migrate prompt + parser.
**Notes:** Cross-family wiring (Phase 2 D-04) untouched. Structured-output via Anthropic tool-use / OpenAI response_format populates JudgeVerdict.unsupported_claims directly.

### Q4 — How does the synthesis prompt instruct the LLM to produce citations?

| Option | Description | Selected |
|--------|-------------|----------|
| Inline `[chunk_id]` brackets, locked example in the prompt | Matches existing stub `_CHUNK_RE`. Single regex across stub + real. | ✓ |
| Structured JSON output via tool-use | Two parsing paths (stub regex vs real JSON); splits CI fidelity. | |
| Footnote-style `[1]` with mapping section | Cleaner inline UI but two-pass extraction. | |

**User's choice:** Inline `[chunk_id]` brackets with fenced example.
**Notes:** Phase 7 Citation parser uses the same regex; no two-path parsing.

---

## Generator API + return shape

### Q1 — What's the shape of Phase 6's generator entry point?

| Option | Description | Selected |
|--------|-------------|----------|
| `Generator` class + `make_generator(cfg)` factory | Mirrors Phase 5 exactly; 4th sibling factory in docintel_core.adapters.factory. | ✓ |
| Thin module-level function | Simpler; loses factory + lru-cache seam Phase 13 needs. | |
| Generator owns retrieval AND generation | Blurs Phase 5 `.search()` seam; harder for Phase 11 ablations. | |

**User's choice:** Generator class + factory.
**Notes:** Phase 10 and Phase 13 instantiate via the factory; tests construct directly with stubbed bundles.

### Q2 — What does Generator.generate() return?

| Option | Description | Selected |
|--------|-------------|----------|
| Interim `GenerationResult` with parsed citations + refused bool | `(text, cited_chunk_ids, refused, retrieved_chunks, completion, prompt_version_hash)`. | ✓ |
| Raw `CompletionResponse` (lossless passthrough) | Pushes citation parsing onto Phase 7; duplicates work across stub-mode tests. | |
| Already-shaped `Answer` (Phase 7 schema) | Collapses Phase 7 into Phase 6; widens scope and complicates confidence field. | |

**User's choice:** Interim `GenerationResult`.
**Notes:** Phase 7's Answer maps directly; Phase 10 reports source cost/latency from completion field; Phase 13 UI renders text + hovers chunks.

### Q3 — Where should `GenerationResult` live?

| Option | Description | Selected |
|--------|-------------|----------|
| `docintel_core.types` + `frozen=True` | Same home as Chunk, RetrievedChunk, IndexManifest. Phase 7 imports without docintel-generate dep. | ✓ |
| `docintel_generate.types` | Lives next to Generator class; inconsistent with RetrievedChunk precedent. | |
| `docintel_core.types`, mutable | Allows Phase 7 in-place mutation; weaker contract. | |

**User's choice:** `docintel_core.types` + frozen=True.
**Notes:** Matches Phase 5 CD-02 precedent; canary against silent mutation downstream.

### Q4 — How should Generator.generate() emit telemetry?

| Option | Description | Selected |
|--------|-------------|----------|
| Single `generator_completed` structlog line | Mirrors Phase 5 retriever_search_completed; Phase 9 MET-05 reads cost_usd + total_ms. | ✓ |
| Per-stage log lines (retrieval, generation, post-processing) | Redundant; Phase 5 already emits retrieval line. | |
| No new log lines, rely on adapter logs | Phase 9 MET-05 has to stitch per-call logs; can't aggregate refused rate. | |

**User's choice:** Single `generator_completed` line.
**Notes:** Includes per-prompt hashes for ablation localisation; Phase 12 binds trace_id via contextvars (no Phase 6 retrofit).

---

## Refusal triggers + citation format

### Q1 — When does Generator.generate() produce a refusal?

| Option | Description | Selected |
|--------|-------------|----------|
| LLM-driven via prompt + hard zero-chunk floor | Dual layer: hard refusal on zero chunks (skip LLM); LLM emits canonical sentinel otherwise. | ✓ |
| Hard zero-chunks only | BM25+dense on 6k chunks always returns something; demo refusal won't trip. | |
| Score-threshold gate | Rerank scores not calibrated across stub vs real; threshold differs per provider. | |

**User's choice:** Dual-layer (hard + LLM-driven).
**Notes:** Demo's out-of-corpus refusal triggers the LLM-driven path; hero GIF shows grounded behavior, not template.

### Q2 — What's the canonical refusal sentinel string?

| Option | Description | Selected |
|--------|-------------|----------|
| `I cannot answer this question from the retrieved 10-K excerpts.` | Plain, professional, recruiter-readable. Replaces Phase 2 stub sentinel everywhere. | ✓ |
| Keep existing `[STUB REFUSAL] No evidence found in retrieved context.` | Looks like debug output in hero GIF. | |
| Question-aware refusal | LLM hallucinates the echo; defeats refusal grep. | |

**User's choice:** `I cannot answer this question from the retrieved 10-K excerpts.`
**Notes:** Stub `_STUB_REFUSAL` updates to match. Single canonical refusal text across stub + real.

### Q3 — How does the synthesis prompt format the retrieved chunks?

| Option | Description | Selected |
|--------|-------------|----------|
| Numbered blocks with chunk_id + metadata header | `<context>[chunk_id | company | fiscal_year | section]<text>---...</context>`. | ✓ |
| Plain text concatenation, citation map appended | LLM has to map text back to citation IDs; citation accuracy may suffer. | |
| JSON-structured input | LLMs over-fixate on JSON formatting; doubles token budget. | |

**User's choice:** Numbered blocks with metadata header.
**Notes:** Four-field header (chunk_id, company, fiscal_year, item_code) disambiguates multi-hop comparatives like the hero question.

### Q4 — How does Phase 6 enforce "every factual claim has at least one [chunk_id] citation"?

| Option | Description | Selected |
|--------|-------------|----------|
| Prompt-instructed + post-hoc parse, no enforcement | Synthesis prompt instructs; generator parses + validates IDs against retrieved set; hallucinated IDs logged + dropped. | ✓ |
| Validator that re-prompts on missing citations | Blows up cost + latency; defeats Phase 9 faithfulness measurement. | |
| Validator that strips uncited sentences | Hides regressions; user sees truncated answers. | |

**User's choice:** Prompt-instructed + post-hoc parse, no enforcement.
**Notes:** Faithfulness is a measurement (Phase 9 MET-03/MET-04), not an enforcement. Hallucinated chunk_ids drop from cited_chunk_ids with a structlog warning; text is not modified.

---

## Claude's Discretion

Per CD-01..CD-10 in CONTEXT.md — exact wordings of SYNTHESIS_PROMPT and JUDGE_PROMPT, JSON-schema field exact names, eager-vs-lazy Generator init (recommended eager), no new tenacity wraps (Phase 2 D-18 + Phase 5 CD-04 inherited), no factory-level cache (Phase 2 / Phase 5 precedent), context-window-budget verification at execution time, hallucinated-chunk-id log-and-drop policy, test layout per Phase 5 Wave 0 pattern, SDK call signatures for structured-output (researcher pulls current docs), 5-wave plan structure mirroring Phase 5.

## Deferred Ideas

- Per-question-type prompt routing (FACTUAL/COMPARATIVE/REFUSAL templates) — tracked if single synthesis prompt underperforms on comparatives in Phase 8/9 eval.
- Footnote-style `[1]` citations with mapping section — Phase 13 UI can layer presentational transform on `[chunk_id]` without changing the eval contract.
- Score-threshold refusal gate — not provider-agnostic; reranker scores not calibrated across stub vs real.
- Question-aware refusal text — LLM hallucinates the echo; defeats refusal grep.
- Re-prompting on missing citations — defeats faithfulness measurement.
- Stripping uncited sentences — hides regressions.
- Generator owning retrieval AND generation — blurs Phase 5 `.search()` seam needed by Phase 10 + 11.
- Already-shaped `Answer` (Phase 7 schema) as Phase 6 return — widens scope; Phase 7's `confidence` field is its own design.
- `make_generator(cfg)` factory-level cache — Phase 13 lru-caches the constructed Generator.
- Async / streaming generator API — Phase 2 D-08 locked sync-only for v1.
- Three-provider judge rotation — Phase 2 deferred already.
- Re-tokenize check on synthesis-prompt context-window budget — K=5 well under frontier-model windows; tracked if Phase 11 K-sweep ablation bumps the limit.
