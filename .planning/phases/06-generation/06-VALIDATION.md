---
phase: 6
slug: generation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-15
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Sourced from `.planning/phases/06-generation/06-RESEARCH.md` §"Validation Architecture" (lines 1087-1145).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (workspace pin — already installed via Phase 1 `docintel-core/pyproject.toml`) |
| **Config file** | workspace-level `pyproject.toml [tool.pytest.ini_options]` (pre-existing) |
| **Quick run command** | `uv run pytest tests/test_prompt_locality.py tests/test_prompt_version_hash.py tests/test_generator_stub_determinism.py tests/test_generator_refusal.py -ra -q -m "not real"` |
| **Full suite command** | `uv run pytest -ra -q -m "not real"` (stub-only; matches existing CI) |
| **Real-mode hero question** | `uv run pytest -m real -ra -q -k "generator and hero"` (workflow_dispatch-only, like `real-index-build`) |
| **Estimated runtime** | ~5 s (quick) / ~30 s (full stub suite incremental over current 121-test baseline) |

---

## Sampling Rate

- **After every task commit:** Run the targeted test file for that task (e.g., `uv run pytest tests/test_prompt_locality.py -x`)
- **After every plan wave:** Run `uv run pytest -ra -q -m "not real"` (full stub suite)
- **Before `/gsd-verify-work`:** Full stub suite must be green + `scripts/check_prompt_locality.sh` exit 0 + `scripts/check_adapter_wraps.sh` exit 0 + Decision-Coverage Audit 27/27 (D-01..D-17 + CD-01..CD-10)
- **Max feedback latency:** 30 s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-* | 01 | 0 | GEN-01..04 | — | test scaffolds with `@pytest.mark.xfail` | unit | `uv run pytest tests/test_prompt_locality.py tests/test_prompt_version_hash.py tests/test_generator_stub_determinism.py tests/test_generator_refusal.py -ra -q` | ❌ W0 | ⬜ pending |
| 06-02-* | 02 | 0 | scaffold | — | new package skeleton + docs path updates + `scripts/check_prompt_locality.sh` (initially green on empty `prompts.py`) | unit | `bash scripts/check_prompt_locality.sh` | ❌ W0 | ⬜ pending |
| 06-03-* | 03 | 1 | GEN-02 | — | `PROMPT_VERSION_HASH` 12-char hex; per-prompt + combined; module-import-time computation | unit | `uv run pytest tests/test_prompt_version_hash.py -x` | ❌ W0 | ⬜ pending |
| 06-04-* | 04 | 2 | GEN-03 + D-03 + D-17 | — | `Generator(bundle, retriever)` + `make_generator(cfg)` + `GenerationResult` (frozen) | unit + integration | `uv run pytest tests/test_generator_stub_determinism.py tests/test_make_generator.py tests/test_generation_result_schema.py tests/test_generator_search_integration.py -ra -q` | ❌ W0 | ⬜ pending |
| 06-05-* | 05 | 3 | D-09 (judge migration) + D-12 (stub refusal sync) | — | judge prompt + parser migrated; structured-output deserializes to `JudgeVerdict`; stub `_STUB_REFUSAL` matches `REFUSAL_PROMPT` sentinel | unit | `uv run pytest tests/test_judge_structured_output.py -x` | ❌ W0 | ⬜ pending |
| 06-06-* | 06 | 4 | GEN-04 + D-16 | — | `generator_completed` 14-field structlog; dual-layer refusal; hero question end-to-end | unit + integration | `uv run pytest tests/test_generator_refusal.py tests/test_generator_telemetry.py -ra -q` | ❌ W0 | ⬜ pending |
| 06-07-* | 07 | 4 | phase gate | — | xfail removal sweep + CI wiring + Decision-Coverage Audit | unit | `uv run pytest -ra -q -m "not real" && bash scripts/check_prompt_locality.sh && bash scripts/check_adapter_wraps.sh` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Plan-level task IDs (`06-NN-MM-…`) are filled in by `gsd-planner` next. The map above is the per-plan sampling skeleton.

---

## Wave 0 Requirements

Test scaffolds (xfail markers; promoted as task-level work consumes each requirement):

- [ ] `tests/test_prompt_locality.py` — covers GEN-01 (3 cases: clean tree → exit 0; planted violation → exit 1; `# noqa: prompt-locality` escape respected)
- [ ] `tests/test_prompt_version_hash.py` — covers GEN-02 (3 cases: format = 12-char hex; monkeypatch sensitivity; per-prompt hashes `_SYNTHESIS_HASH` / `_REFUSAL_HASH` / `_JUDGE_HASH` exposed)
- [ ] `tests/test_generator_stub_determinism.py` — covers GEN-03 (3 cases: determinism, `cited_chunk_ids ⊆ retrieved set`, hallucinated ids dropped with structlog warning)
- [ ] `tests/test_generator_refusal.py` — covers GEN-04 (3 cases: hard zero-chunk → `refused=True`/`completion is None`; LLM-driven sentinel → `refused=True`; `generator_refused_zero_chunks` warning fires)
- [ ] `tests/test_make_generator.py` — covers D-03 (factory returns `Generator` for stub Settings; lazy-import gate — `import docintel_core.adapters.factory` does NOT load `docintel_generate.generator`)
- [ ] `tests/test_judge_structured_output.py` — covers D-09 (judge structured-output deserializes into `JudgeVerdict`; deserialization-failure sentinel `JudgeVerdict(score=0.0, passed=False, …)`)
- [ ] `tests/test_generator_search_integration.py` — covers D-14 + hero (end-to-end stub: comparative question → non-empty `cited_chunk_ids` covering multiple tickers)
- [ ] `tests/test_generator_telemetry.py` — covers D-16 (`generator_completed` structlog emits all 14 fields)
- [ ] `tests/test_generation_result_schema.py` — covers D-17 (`GenerationResult` is frozen + `extra="forbid"`)
- [ ] `tests/test_generator_real_hero.py` — covers hero question real-mode (xfail until `workflow_dispatch` lands; mirrors Phase 5 `test_reranker_canary_real_mode`)
- [ ] `tests/fixtures/prompt_locality_violations/` — fixture dir with a planted violation file for the GEN-01 negative case
- [ ] `tests/fixtures/prompt_locality_violations_with_noqa/` — fixture dir with a violation line that carries `# noqa: prompt-locality` (must NOT trip the gate)

*Framework install: not needed — pytest already in workspace pins (FND-09).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Hero GIF recording: multi-hop comparative question + OOC refusal demo | UI-03 (Phase 13) | Visual artifact; not automatable in Phase 6 scope | Phase 13 records `/Query` tab against `/gsd-verify-work` UAT walkthrough. Phase 6 ships only the underlying `Generator.generate()`; the GIF is Phase 13's deliverable. |
| Real-mode workflow_dispatch run of `tests/test_generator_real_hero.py` | hero question / Phase 9 readiness | Costs API credits; gated behind manual trigger like Phase 4 `real-index-build` and Phase 5 `test_reranker_canary_real_mode` | `gh workflow run ci.yml --ref phase/6-generation` after merge; verify `test_generator_real_hero` PASSES. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies (filled by `gsd-planner`)
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references in the table above
- [ ] No watch-mode flags (CI runs `-ra -q`)
- [ ] Feedback latency < 30 s (incremental over the existing 121-test baseline)
- [ ] `nyquist_compliant: true` set in frontmatter after Wave 4 xfail-removal sweep
- [ ] Decision-Coverage Audit 27/27 — D-01..D-17 + CD-01..CD-10

**Approval:** pending (gsd-plan-checker will validate after gsd-planner produces the PLAN.md files)
