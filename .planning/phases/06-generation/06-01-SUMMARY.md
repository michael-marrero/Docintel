---
phase: 06-generation
plan: 01
subsystem: testing
tags: [pytest, xfail-strict, structlog-capture-logs, prompt-locality-grep-gate]

# Dependency graph
requires:
  - phase: 05-retrieval-hybrid-rerank
    provides: RetrievedChunk shape; capture_logs canonical pattern in tests/test_retriever_search.py; dual-mode marker pattern in tests/test_reranker_canary.py:44-50
provides:
  - 10 xfail-strict test scaffolds (21 functions total) targeting every Phase 6 GEN-01..04 requirement + every D-03/D-08/D-09/D-13/D-14/D-15/D-16/D-17 contract
  - 2 prompt-locality fixture directories (negative offender + positive noqa escape) for the GEN-01 grep gate (Plan 06-02 ships the script)
  - Wave 0 green stub-mode pytest run (121 passed + 19 xfailed + 2 skipped + 6 deselected; exit 0)
affects:
  - 06-02 (gate script flips 2 prompt_locality xfails to xpass)
  - 06-03 (prompts.py flips 3 prompt_version_hash xfails to xpass)
  - 06-04 (Generator + factory + GenerationResult flips 9 xfails to xpass)
  - 06-05 (stub adapter sync — no test change)
  - 06-06 (judge migration flips 1 stub-mockable xfail; real-mode test stays xfail)
  - 06-07 (xfail-removal sweep + Decision-Coverage Audit; real-mode hero gets workflow_dispatch promotion)

# Tech tracking
tech-stack:
  added: []  # no new dependencies — pytest + structlog already in workspace pins (FND-09)
  patterns:
    - "xfail-strict-with-reason scaffold pattern (in-function imports → ImportError-as-xfail)"
    - "dual-mode marker pattern (function-level @pytest.mark.real + @pytest.mark.xfail INNER; rationale at tests/test_reranker_canary.py:52-65)"
    - "CI grep-gate test analog (Phase 4 tests/test_index_wraps_gate.py shape applied to GEN-01)"
    - "structlog.testing.capture_logs(...) as the canonical log-capture pattern (Phase 5 D-12 analog reused for generator_completed + generator_refused_zero_chunks + generator_hallucinated_chunk_id)"

key-files:
  created:
    - "tests/test_prompt_locality.py (GEN-01 + D-04 + D-05 — 3 xfail tests)"
    - "tests/test_prompt_version_hash.py (GEN-02 + D-08 — 3 xfail tests)"
    - "tests/test_make_generator.py (D-03 + D-12 — 2 xfail tests)"
    - "tests/test_generation_result_schema.py (D-17 — 2 xfail tests)"
    - "tests/test_generator_stub_determinism.py (GEN-03 + D-13 + CD-07 — 3 xfail tests)"
    - "tests/test_generator_refusal.py (GEN-04 + D-10 + D-11 + D-15 — 3 xfail tests)"
    - "tests/test_judge_structured_output.py (D-09 — 2 xfail tests; one real-mode + one stub-mockable)"
    - "tests/test_generator_search_integration.py (D-14 + hero stub end-to-end — 1 xfail test)"
    - "tests/test_generator_telemetry.py (D-16 15-field structlog — 1 xfail test)"
    - "tests/test_generator_real_hero.py (hero real-mode + CD-06 guards — 1 dual-mode xfail test)"
    - "tests/fixtures/prompt_locality_violations/offender.py (negative fixture)"
    - "tests/fixtures/prompt_locality_violations_with_noqa/allowed.py (positive noqa fixture)"
  modified: []

key-decisions:
  - "make_generator lazy-import test must also assert hasattr(factory, 'make_generator') — without this guard, the test passes trivially under Wave 0 (XPASS-strict → FAIL) because docintel_generate.generator is never in sys.modules. The AttributeError flip ensures the test xfails meaningfully under Wave 0 and naturally promotes when Plan 06-04 lands make_generator."
  - "Test imports happen INSIDE test bodies, not at module top. This converts ImportError on the not-yet-existing docintel_generate.* modules into pytest-counted xfail (rather than a module-load collection error which would block discovery)."
  - "Dual-mode @pytest.mark.real tests use FUNCTION-LEVEL markers, not module-level pytestmark — pytest's marker-collection evaluates `not real` deselection BEFORE applying xfail, so the test is deselected from default CI and only collected under `-m real`. Module-level pytestmark would gate the whole file and break stub-CI."

patterns-established:
  - "xfail-strict-scaffold-with-reason: every test function carries @pytest.mark.xfail(strict=True, reason='Wave N — Plan 06-XX ships <feature>') on a single line for grep-discoverability. Wave 1-4 plans flip xfails to xpass as production code lands; Plan 06-07's xfail-removal sweep is the final acceptance gate."
  - "hermetic-reset-then-import: lazy-import-gate tests drop docintel_generate.* + the factory module from sys.modules BEFORE the import (mirrors tests/test_make_retriever.py:67-100) so a prior test that pulled in docintel_generate does not contaminate the assertion."
  - "single-canonical-structlog-capture: every log-capture test uses `from structlog.testing import capture_logs` + `with capture_logs() as records:`; no monkeypatch of logger configuration. Inherits Phase 5's D-12 analog at tests/test_retriever_search.py:27/43/107-127."

requirements-completed: [GEN-01, GEN-02, GEN-03, GEN-04]
# Note: requirement IDs land here for tracking; the requirements are only PARTIALLY satisfied
# at Wave 0 (scaffolds exist, xfail). Plan 06-07's xfail-removal sweep is the final acceptance.

# Metrics
duration: 32min
completed: 2026-05-15
---

# Phase 6 Plan 01: Test scaffolds (Wave 0) Summary

**21 xfail-strict test scaffolds + 2 prompt-locality fixtures landed across 3 atomic commits; stub-mode pytest stays green (121 passed + 19 xfailed + 2 skipped, exit 0) and every Phase 6 GEN-01..04 + D-03/D-08/D-09/D-13/D-14/D-15/D-16/D-17 contract has a collectable pytest target before any production code ships.**

## Performance

- **Duration:** ~32 min
- **Started:** 2026-05-15T (Wave 0 spawn)
- **Completed:** 2026-05-15T (3 atomic commits + SUMMARY)
- **Tasks:** 3 (Task 0 + Task A + Task B)
- **Files created:** 12 (10 test files + 2 fixture files)
- **Files modified:** 0 (no production code touched — Wave 0 is tests + fixtures only per the plan's verification line 310)

## Accomplishments

- 10 new test files under `tests/` (21 xfail-strict test functions total) covering every Phase 6 behavior named in `.planning/phases/06-generation/06-VALIDATION.md` Per-Task Verification Map.
- 2 prompt-locality fixture directories (negative offender + positive `# noqa: prompt-locality` escape) for the GEN-01 grep gate that Plan 06-02 ships.
- Wave 0 baseline: `uv run pytest -ra -q -m "not real"` exits 0 with **121 passed + 19 xfailed + 2 skipped + 6 deselected** — exactly the Phase 5 baseline plus 19 new xfails (the 2 real-mode tests are deselected by `-m "not real"`).
- Lazy-import-gate test for `make_generator` correctly fails under Wave 0 (AttributeError on missing factory function) and naturally promotes to passing when Plan 06-04 lands.

## Task Commits

Each task was committed atomically:

1. **Task 0: Create the two prompt-locality fixture directories** — `637833c` (chore)
2. **Task A: Create the four protocol-locality + version-hash + factory test scaffolds** — `c241090` (test)
3. **Task B: Create the six generator-behavior + judge-migration + hero test scaffolds** — `1f9f93e` (test)

## Files Created/Modified

### Created (12 files, all under `tests/`)

**Task 0 — Fixtures (2 files):**
- `tests/fixtures/prompt_locality_violations/offender.py` — negative fixture; contains `_INLINE_SYNTHESIS_PROMPT` triple-quoted string with the four PHRASE_PATTERN substrings (`You are` / `<context>` / `cite` / `chunk_id`) the GEN-01 gate must catch. No `# noqa: prompt-locality` anywhere.
- `tests/fixtures/prompt_locality_violations_with_noqa/allowed.py` — positive escape-hatch fixture; same offending shape but the offending line carries `# noqa: prompt-locality`. The `noqa` comment appears exactly ONCE in this file (acceptance criterion).

**Task A — 4 test files (10 xfail functions):**
- `tests/test_prompt_locality.py` (3 tests, GEN-01 + D-04 + D-05) — subprocess invocation of `scripts/check_prompt_locality.sh` against canonical layout, negative fixture, positive noqa fixture. Analog: `tests/test_index_wraps_gate.py`.
- `tests/test_prompt_version_hash.py` (3 tests, GEN-02 + D-08) — hash format (12-char lowercase hex), per-prompt distinctness (`_SYNTHESIS_HASH` / `_REFUSAL_HASH` / `_JUDGE_HASH`), single-byte sensitivity (Pitfall 3 defense).
- `tests/test_make_generator.py` (2 tests, D-03 + D-12) — factory dispatch + lazy-import gate (asserts `factory.make_generator` exists AND `docintel_generate.generator` not in `sys.modules` after hermetic reset). Analog: `tests/test_make_retriever.py`.
- `tests/test_generation_result_schema.py` (2 tests, D-17) — `frozen=True` rejects mutation; `extra='forbid'` rejects unknown fields. Analog: `tests/test_retrieved_chunk_schema.py`.

**Task B — 6 test files (11 xfail functions):**
- `tests/test_generator_stub_determinism.py` (3 tests, GEN-03 + D-13 + CD-07) — three back-to-back `generate()` calls identical; `cited_chunk_ids ⊆ retrieved` set; hallucinated chunk_ids dropped + text preserved + `generator_hallucinated_chunk_id` structlog warning. Uses `_FakeRetriever` test double for isolation.
- `tests/test_generator_refusal.py` (3 tests, GEN-04 + D-10 + D-11 + D-15) — hard zero-chunk refusal (Step B) → `REFUSAL_TEXT_SENTINEL` + `completion is None`; LLM-driven refusal (Step D) → `refused=True` + `completion is not None`; `generator_refused_zero_chunks` structlog on Step B.
- `tests/test_judge_structured_output.py` (2 tests, D-09) — real-mode structured-output returns `JudgeVerdict` (4 fields populated); deserialization failure returns sentinel `JudgeVerdict(score=0.0, passed=False, reasoning='<deserialization failed>')`. Real-mode test uses `@pytest.mark.real` (OUTER) + xfail-strict (INNER) function-level pattern.
- `tests/test_generator_search_integration.py` (1 test, D-14 + hero stub) — `make_generator(Settings(llm_provider="stub"))` end-to-end on hero comparative question → `cited ≥ 1`, `refused=False`, `completion.model="stub"`.
- `tests/test_generator_telemetry.py` (1 test, D-16) — `generator_completed` emits exactly once with all 15 named fields (`query_tokens`, `n_chunks_retrieved`, `n_chunks_cited`, `refused`, `prompt_version_hash`, `synthesis_hash`, `refusal_hash`, `judge_hash`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `retrieval_ms`, `generation_ms`, `total_ms`, `model`). Uses `structlog.testing.capture_logs` (canonical analog at `tests/test_retriever_search.py:27/43/107-127`).
- `tests/test_generator_real_hero.py` (1 test, hero real-mode + CD-06 guards) — dual-mode marker (`@pytest.mark.real` OUTER + xfail-strict INNER, function-level not module-level). Hero comparative question end-to-end + CD-06 cost (< $0.20) + context-window budget (< 8K prompt_tokens) + multi-COMPANY coverage (≥2 distinct cited tickers).

### Modified: NONE

No production code, no source-module changes, no config edits. Wave 0 is pure test + fixture scaffolds.

## Wave-Flip Mapping

| Test file | xfail count | Flipped by |
|-----------|-------------|------------|
| `tests/test_prompt_locality.py::test_grep_gate_fails_on_violation` | 1 | Plan 06-02 (gate script) |
| `tests/test_prompt_locality.py::test_grep_gate_respects_noqa` | 1 | Plan 06-02 (gate script noqa handling) |
| `tests/test_prompt_locality.py::test_grep_gate_passes_on_canonical_layout` | 1 | Plan 06-07 (xfail-removal sweep after Waves 1-3) |
| `tests/test_prompt_version_hash.py` (3 tests) | 3 | Plan 06-03 (`docintel_generate.prompts`) |
| `tests/test_make_generator.py` (2 tests) | 2 | Plan 06-04 (`make_generator` + `Generator`) |
| `tests/test_generation_result_schema.py` (2 tests) | 2 | Plan 06-04 (`GenerationResult` in `docintel_core.types`) |
| `tests/test_generator_stub_determinism.py` (3 tests) | 3 | Plan 06-04 (Generator + Step D validation + CD-07 structlog) |
| `tests/test_generator_refusal.py` (3 tests) | 3 | Plan 06-04 (Step B hard-refusal + Step D `.startswith` + Step B structlog) |
| `tests/test_judge_structured_output.py::test_deserialization_failure_returns_sentinel` | 1 | Plan 06-06 (judge structured-output + sentinel fallback) |
| `tests/test_judge_structured_output.py::test_judge_returns_judgeverdict` (real-mode) | 1 (xfail preserved) | Plan 06-07 + workflow_dispatch real-mode promotion |
| `tests/test_generator_search_integration.py::test_hero_comparative_stub` | 1 | Plan 06-04 (`make_generator(cfg)` integration) |
| `tests/test_generator_telemetry.py::test_completed_fields` | 1 | Plan 06-04 (`generator_completed` 15-field emit) |
| `tests/test_generator_real_hero.py::test_generator_hero_real_mode` (real-mode) | 1 (xfail preserved) | Plan 06-07 + workflow_dispatch real-mode promotion |

**Total xfail count:** 21 (19 stub-mode xfail under default CI; 2 real-mode xfail collected only under `-m real`).

## Decisions Made

1. **`structlog.testing.capture_logs` is the canonical log-capture pattern.** Mirrors `tests/test_retriever_search.py:27 + 43 + 107-127 + 208` verbatim. No monkeypatching of logger configuration. Same context-manager shape across `generator_completed` (D-16), `generator_refused_zero_chunks` (D-15 Step B), and `generator_hallucinated_chunk_id` (CD-07).

2. **`test_factory_lazy_imports_generator_module` adds an `assert hasattr(factory, "make_generator")` guard.** Without this guard, the test passes trivially under Wave 0 (no module ever imports `docintel_generate.generator`) → XPASS-strict → FAIL. Adding the `hasattr` assertion ensures the test xfails meaningfully on Wave 0 (AttributeError on the missing factory function) and naturally promotes to passing when Plan 06-04 ships `make_generator` with the lazy-import discipline. Documented in the test docstring + the per-task commit message.

3. **Test imports happen INSIDE test bodies, not at module top.** Converts ImportError on the not-yet-existing `docintel_generate.*` modules into pytest-counted xfail (rather than a module-load collection error which would block discovery). Inherits the Phase 5 pattern from `tests/test_retrieved_chunk_schema.py:54-55`.

4. **Dual-mode `@pytest.mark.real` tests use FUNCTION-LEVEL markers, not module-level `pytestmark`.** pytest's marker-collection evaluates `not real` deselection BEFORE applying xfail; function-level keeps stub-mockable siblings (e.g., `test_deserialization_failure_returns_sentinel` in `test_judge_structured_output.py`) running in default CI. Module-level `pytestmark = pytest.mark.real` would gate the whole file and break stub-CI (06-PATTERNS.md anti-pattern flag at lines 868-869).

5. **All decorator markers placed on a single line.** Acceptance-criterion `grep -c "@pytest.mark.xfail(strict=True"` requires exact counts (3/3/2/2 for Task A; 3/3/2/1/1/1 for Task B). Line-wrapping the decorator across multiple lines would break the substring count. Adopted single-line form even when it exceeds 100 chars (ruff's E501 is configured as ignored — `pyproject.toml` line: `ignore = ["E501"]`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Added `hasattr(factory, "make_generator")` guard to `test_factory_lazy_imports_generator_module`**

- **Found during:** Task A
- **Issue:** The plan body specified the test should `assert "docintel_generate.generator" not in sys.modules` after a hermetic `sys.modules` reset followed by `import docintel_core.adapters.factory`. Under Wave 0 (when no production code imports `docintel_generate.generator` anywhere), the assertion was trivially TRUE → XPASS-strict → FAILED test. The strict-xfail marker correctly flipped the unexpected pass into a hard failure.
- **Fix:** Added a preceding `assert hasattr(factory, "make_generator"), ...` guard. Under Wave 0 this fails with AttributeError (the function does not exist yet) so the whole test fails → xfail-strict holds. Under Wave 2+ (after Plan 06-04 lands `make_generator`), the `hasattr` check passes AND the lazy-import assertion meaningfully verifies the import discipline.
- **Files modified:** `tests/test_make_generator.py`
- **Verification:** `uv run pytest tests/test_make_generator.py -ra -q` shows both tests as XFAIL (was 1 xfail + 1 XPASS-strict-FAIL before the fix).
- **Committed in:** `c241090` (Task A commit, post-fix).

**2. [Rule 1 — Bug] Removed `@pytest.mark.xfail(strict=True)` and `@pytest.mark.real` LITERAL substrings from docstrings**

- **Found during:** Task A + Task B
- **Issue:** The plan's acceptance criteria use `grep -c "@pytest.mark.xfail(strict=True"` and `grep -c "@pytest.mark.real"` with EXACT count expectations (e.g., 3/3/2/2/1/1/1/1). Including the literal marker strings in docstrings inflates the substring counts above the expected values (e.g., `test_generator_real_hero.py` showed 3 occurrences when criterion requires exactly 1; `test_judge_structured_output.py` showed 4 occurrences of `@pytest.mark.xfail(strict=True` when criterion requires exactly 2).
- **Fix:** Rewrote docstring text to refer to "the xfail-strict marker (INNER)" and "the real-mode marker (OUTER)" instead of the literal decorator syntax. The decorator is now grep-able exactly at the actual decorator sites.
- **Files modified:** `tests/test_judge_structured_output.py`, `tests/test_generator_real_hero.py`
- **Verification:** All six grep-count acceptance criteria now match exactly (3/3/2/1/1/1 for Task B xfail decorators; 1 occurrence of `@pytest.mark.real` in `test_generator_real_hero.py`).
- **Committed in:** `1f9f93e` (Task B commit, post-fix).

**3. [Rule 1 — Bug] Removed redundant `noqa: prompt-locality` substring from `allowed.py` docstring**

- **Found during:** Task 0
- **Issue:** The plan's acceptance criterion `grep -c "noqa: prompt-locality" tests/fixtures/prompt_locality_violations_with_noqa/allowed.py returns 1`. My first draft mentioned the literal escape-hatch token in the docstring AND on the offending line → count = 2.
- **Fix:** Rewrote the docstring to refer to "the per-line escape-hatch comment defined in D-05" instead of the literal token. Token now appears exactly once (on the offending line).
- **Files modified:** `tests/fixtures/prompt_locality_violations_with_noqa/allowed.py`
- **Verification:** `grep -c "noqa: prompt-locality" tests/fixtures/prompt_locality_violations_with_noqa/allowed.py` → 1.
- **Committed in:** `637833c` (Task 0 commit, post-fix).

**4. [Rule 1 — Bug] Replaced Unicode `×` MULTIPLICATION SIGN with ASCII `x`**

- **Found during:** Task B (ruff lint)
- **Issue:** `tests/test_generator_real_hero.py` referenced "K=5 × ~500 BGE tokens" in docstring and an assertion message. ruff flags RUF001/RUF002 (ambiguous Unicode `×`).
- **Fix:** Replaced `×` with `x` in both occurrences.
- **Files modified:** `tests/test_generator_real_hero.py`
- **Verification:** `uv run ruff check tests/test_generator_real_hero.py` → "All checks passed!"
- **Committed in:** `1f9f93e` (Task B commit, post-fix).

---

**Total deviations:** 4 auto-fixed (4 Rule 1 bugs — all were author-introduced regressions on first-draft test files that the plan's source-assertion acceptance criteria caught at verification time).

**Impact on plan:** All four auto-fixes are scoped to the test files themselves; no production code touched. The fixes resolve gaps between the plan's behavior-assertion ("all 21 tests collected; 19 xfailed under stub mode") and source-assertion (exact grep counts) acceptance criteria. The plan's net deliverable (10 test files + 2 fixtures + green stub-mode pytest) lands unchanged.

## Issues Encountered

- **Flaky pre-existing BM25 test-ordering bug.** The first full-suite `uv run pytest -ra -q -m "not real"` after Task B landed reported `2 failed, 119 passed` — `tests/test_bm25_store.py::test_chunk_ids_aligned_with_rows` + `test_bm25_artifacts_present`. Running `uv run pytest tests/test_bm25_store.py` in isolation passes; running the full suite WITHOUT the 10 new test files passes (`121 passed`); re-running the full suite WITH the new test files later also passes (`121 passed + 19 xfailed`). Root cause: a pre-existing test-ordering effect involving filesystem state for `data/indices/`. Not introduced by Plan 06-01 (the new test files are pure xfail scaffolds that don't touch `data/indices/`). Documented here for traceability but no fix attempted — out of scope for Plan 06-01 (executor scope boundary rule).

- **`.planning/` is gitignored.** The PLAN.md execution context says "planning artifacts in `.planning/phases/06-generation/` are gitignored but tracked via `git add -f` and visible". The SUMMARY.md is written into the worktree's `.planning/phases/06-generation/06-01-SUMMARY.md` and staged via `git add -f` for inclusion on the worktree branch.

## User Setup Required

None — Wave 0 is pure test + fixture scaffolds. No external service config, no env vars, no API keys.

## Next Phase Readiness

- **Plan 06-02 unblocked:** can land `scripts/check_prompt_locality.sh` + doc updates against the negative + positive fixtures from Task 0. Two of the three `test_prompt_locality.py` xfails will flip to passing in that wave.
- **Plan 06-03 unblocked:** can land `packages/docintel-generate/src/docintel_generate/prompts.py` against the three `test_prompt_version_hash.py` xfails.
- **Plan 06-04 unblocked:** can land `Generator` + `make_generator` + `GenerationResult` against the nine xfails in `test_make_generator.py` + `test_generation_result_schema.py` + `test_generator_stub_determinism.py` + `test_generator_refusal.py` + `test_generator_search_integration.py` + `test_generator_telemetry.py`.
- **Plan 06-06 unblocked:** can land the judge structured-output migration against `test_judge_structured_output.py::test_deserialization_failure_returns_sentinel`.
- **Plan 06-07 final acceptance:** will sweep the xfail markers, run the full workspace stub-mode pytest, and confirm exit 0. The two real-mode xfails (`test_judge_returns_judgeverdict` and `test_generator_hero_real_mode`) stay xfail through Phase 6 per the Phase 5 precedent on `test_reranker_canary_real_mode`; promotion happens after a workflow_dispatch run records the real-mode numbers.

## Self-Check: PASSED

All 12 created files verified to exist on disk; all 3 task commits verified to exist in `git log`.

- `tests/test_prompt_locality.py` — FOUND
- `tests/test_prompt_version_hash.py` — FOUND
- `tests/test_make_generator.py` — FOUND
- `tests/test_generation_result_schema.py` — FOUND
- `tests/test_generator_stub_determinism.py` — FOUND
- `tests/test_generator_refusal.py` — FOUND
- `tests/test_judge_structured_output.py` — FOUND
- `tests/test_generator_search_integration.py` — FOUND
- `tests/test_generator_telemetry.py` — FOUND
- `tests/test_generator_real_hero.py` — FOUND
- `tests/fixtures/prompt_locality_violations/offender.py` — FOUND
- `tests/fixtures/prompt_locality_violations_with_noqa/allowed.py` — FOUND
- Commit `637833c` (Task 0) — FOUND
- Commit `c241090` (Task A) — FOUND
- Commit `1f9f93e` (Task B) — FOUND

---
*Phase: 06-generation*
*Completed: 2026-05-15*
