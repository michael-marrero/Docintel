---
phase: 06-generation
plan: 07
subsystem: ci + audit + xfail-sweep
tags: [ci-yaml, grep-gate, gen-01, d-06, xfail-sweep, decision-coverage-audit, phase-gate, pitfall-9]

# Dependency graph
requires:
  - phase: 06-generation/plan/02
    provides: scripts/check_prompt_locality.sh (the script the CI YAML step runs); REFUSAL_TEXT_SENTINEL canonical home (Pitfall 9 resolution)
  - phase: 06-generation/plan/03
    provides: prompts.py + parse.py canonical homes (the audit's GEN-01/02 + Pitfall 9 evidence)
  - phase: 06-generation/plan/04
    provides: Generator + factory + GenerationResult (the audit's D-03/D-13/D-14/D-15/D-16/D-17 evidence)
  - phase: 06-generation/plan/05
    provides: stub adapter _STUB_REFUSAL + _CHUNK_RE re-import (the audit's D-11/D-12 cross-package link evidence)
  - phase: 06-generation/plan/06
    provides: judge migration to structured-output dispatch (the audit's D-09 + CD-09 evidence)
provides:
  - .github/workflows/ci.yml — new step `Check prompt locality (GEN-01)` after the three existing wrap-gate steps (D-06 closes the 4th CI grep gate)
  - tests/test_judge_structured_output.py — final Wave-4 xfail-strict marker removed (the remaining 1 of the 21 original xfails; the other 19 were swept early in Waves 0-3; the 21st on test_generator_real_hero.py is preserved per Phase 5 precedent)
  - .planning/phases/06-generation/06-DECISIONS-AUDIT.md — Decision-Coverage Audit with 17 D-XX + 10 CD-XX rows + 1 Pitfall 9 resolution row + Phase Gate checklist + Sign-off block
affects:
  - phase-6 merge to main (the audit IS the phase-gate artifact the developer reviews before merge)
  - phase-10 EVAL-02 manifest header reader (will source PROMPT_VERSION_HASH=dab1bcf7379f from docintel_generate.prompts)
  - workflow_dispatch real-mode hero promotion (post-merge — test_generator_hero_real_mode flips from xfail to PASSED on first successful real-mode run, mirroring Phase 5's test_reranker_canary_real_mode precedent)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - 4th-CI-grep-gate wiring (the new YAML step joins three Phase-2/4/5 analogs as a contiguous block)
    - Decision-Coverage Audit shape (informed by Phase 5's 05-VERIFICATION.md sectional structure; 27-row table is Phase-6-specific)
    - Wave-4 xfail-sweep as phase-close gate (the 19 early sweeps in Waves 0-3 + the 1 here brings the suite to 0 strict xfails on stub-mode tests; the preserved real-mode xfail is the empirical bite-point per Phase 5 precedent)
    - Empirical-PENDING-on-real-mode phase-close (Phase 6 ships with the real-mode hero test xfail-preserved; workflow_dispatch promotion is the post-merge developer action)

key-files:
  created:
    - .planning/phases/06-generation/06-DECISIONS-AUDIT.md (199 lines; 17 + 10 + 3 + 11 + 15 + 10 row tables)
    - .planning/phases/06-generation/06-07-SUMMARY.md (this file)
  modified:
    - .github/workflows/ci.yml (+8 lines — one new step block with name + 5-line comment + run line + blank-line separator)
    - tests/test_judge_structured_output.py (-1 line — single xfail decorator removed; the @pytest.mark.real OUTER marker preserved)

key-decisions:
  - "The Wave 4 xfail sweep is small (1 marker removed) because Waves 0-3 already removed 19 of the 21 markers inline as production code landed. Commits 8681559 (prompt_locality, Plan 06-02), 0eefc4a (prompt_version_hash, Plan 06-03), d2901ba (11 Generator-dependent tests, Plan 06-04), and 058b856 (judge sentinel, Plan 06-06) cumulatively swept 19 markers. Plan 06-07's sweep closes test_judge_returns_judgeverdict's xfail-strict; the @pytest.mark.real outer marker is preserved so the test stays deselected from default `-m \"not real\"` CI and only runs under workflow_dispatch -m real."
  - "The audit's Phase Gate Checklist shows 8 ✓ + 2 documented Pre-existing Anti-Patterns (ruff I001 in real/judge.py + 10 black reformat warnings across stub/llm.py + real/judge.py + 8 tests). The Pre-existing classification matches Phase 5's precedent at 05-VERIFICATION.md:124-132 — these are pre-existing tracked deferred items from earlier waves, not blockers for the phase gate. The Plan 06-07 commits did not introduce any new ruff/black diffs (verified by stashing and re-checking the pristine pre-edit file)."
  - "The audit shape is informed by 05-VERIFICATION.md but is NOT a copy of it. No 05-DECISIONS-AUDIT.md file exists; the 27-row decision-coverage table is Phase-6 specific. Sections mirrored from Phase 5: ## Goal Achievement / ### Observable Truths / ## Required Artifacts / ## Key Link Verification / Anti-Patterns Found / Sign-off. New sections specific to Phase 6: ## Decision Coverage / ## Claude's Discretion Coverage / ## Pitfall Resolutions / ## Phase Gate Checklist."
  - "The post-Wave-4 PROMPT_VERSION_HASH is stable at `dab1bcf7379f` since Plan 06-03 commit `90e0409`. Per-prompt hashes: _SYNTHESIS_HASH=ec466290503d, _REFUSAL_HASH=bf92b696078e, _JUDGE_HASH=8e563d5fbce2. This is the value Phase 10 EVAL-02 manifest will read. Recording it in the audit's frontmatter gives Phase 10 a single bisection point for prompt-version drift detection."

patterns-established:
  - "Phase-close audit template — header + ## Goal Achievement + ## Decision Coverage table (17 rows for D-XX) + ## Claude's Discretion Coverage table (10 rows for CD-XX) + ## Pitfall Resolutions (1+ rows for RESEARCH §Pitfalls that required a decision) + ## Required Artifacts + ## Key Link Verification + ## Phase Gate Checklist + ## Sign-off. Each row in the coverage tables cites: ID, Decision summary, Plan number, Landing artifact (file path + line number OR commit hash), Verification (test command or grep gate)."
  - "Pre-existing anti-pattern documentation pattern — when the audit's Phase Gate Checklist exposes a ruff/black diff, distinguish 'introduced by this plan' vs 'pre-existing tracked deferred item' by stashing this plan's edits and re-running the check on the pristine file. Document the result in an Anti-Patterns Found table inside the Phase Gate Checklist; classify as Pre-existing if the diff predates this plan; do NOT block the gate on Pre-existing items (Phase 5 precedent)."
  - "Empirical-PENDING-on-real-mode phase-close — when a phase has a real-mode test that cannot be empirically validated without API credits + workflow_dispatch, preserve its @pytest.mark.real + @pytest.mark.xfail(strict=True) markers, ship the phase, and document the post-merge developer action that will promote it. The phase gate is closed on stub-mode + audit; real-mode promotion is a follow-on empirical proof point. Mirrors Phase 5's test_reranker_canary_real_mode precedent precisely."

requirements-completed: [GEN-01, GEN-02, GEN-03, GEN-04]

# Metrics
duration: 25min
completed: 2026-05-15
tests-added: 0
tests-modified: 1
production-files-modified: 0
ci-yaml-files-modified: 1
audit-files-created: 1
total-phase-6-tests-net-delta: +19 (10 from Plan 06-01 Task A + 9 stub-mode from Task B; the 2 @pytest.mark.real tests deselected from default `-m \"not real\"` CI)
---

# Phase 6 Plan 07: Wave 4 — Phase-Close Summary

**Phase 6 closes: the 4th CI grep gate is wired (D-06), the Wave-4 xfail-sweep retires the last of the 21 Wave-0 scaffolding markers (only the real-mode hero xfail is preserved per Phase 5 precedent), and the Decision-Coverage Audit documents 27/27 ✓ across 17 D-XX + 10 CD-XX with the Pitfall 9 cycle-resolution traced end-to-end. Phase Gate green except for two Pre-existing tracked anti-patterns (ruff + black) that mirror Phase 5's documentation pattern. Ready for developer review then merge.**

## Performance

- **Duration:** ~25 min (read context + execute Tasks A-C + write SUMMARY)
- **Started:** 2026-05-15 (Wave 4 spawn)
- **Completed:** 2026-05-15 (3 atomic per-task commits + audit file + this SUMMARY)
- **Tasks:** 4 (A: CI wiring, B: xfail sweep, C: audit document, D: checkpoint pending)
- **Files modified:** 1 CI YAML + 1 test (`test_judge_structured_output.py`, 1-line deletion)
- **Files created:** 2 (the audit document + this SUMMARY)

## Task Commits

Per-task atomic commits via the executor protocol:

1. **Task A: Wire the GEN-01 grep-gate CI step in .github/workflows/ci.yml** — `426d2ad` (ci)
2. **Task B: Final Wave-4 xfail sweep — remove judge structured-output xfail** — `95d46a6` (test)
3. **Task C: Write the Decision-Coverage Audit (27/27 ✓ + Pitfall 9)** — `47da071` (docs)
4. **Task D: Checkpoint pending** — developer-review

## Files Created / Modified

### Created

- `.planning/phases/06-generation/06-DECISIONS-AUDIT.md` (199 lines) — the phase-gate audit. Sections: Header + Goal Achievement (paragraph + 13 Observable Truths) + Decision Coverage 17-row table + Claude's Discretion Coverage 10-row table + Pitfall Resolutions (Pitfalls 3 + 5 + 9) + Required Artifacts 15-row table + Key Link Verification 11-row table + Phase Gate Checklist (10 items; 8 ✓ + 2 tracked Anti-Patterns) + Sign-off block.
- `.planning/phases/06-generation/06-07-SUMMARY.md` — this file.

### Modified

- `.github/workflows/ci.yml` — new step `Check prompt locality (GEN-01)` placed AFTER the `Index wrap grep gate (D-21)` step at line 102-106 and BEFORE the `Chunk-idempotency gate (ING-04)` step. Step body: `run: bash scripts/check_prompt_locality.sh`. Comment block (5 lines) mirrors the three existing wrap-gate steps' convention verbatim. Net diff: +8 lines (one blank-line separator + name + 5 comment lines + run line). YAML still parses cleanly (`python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` → exit 0).
- `tests/test_judge_structured_output.py` — single 1-line deletion: removed `@pytest.mark.xfail(strict=True, reason="Wave 3 — Plan 06-06 ships structured-output dispatch + JudgeVerdict deserializer")` from above `test_judge_returns_judgeverdict`. The OUTER `@pytest.mark.real` marker is preserved (the test stays deselected by default `-m "not real"` CI; only `-m real` workflow_dispatch collects it).

## Acceptance Verification

All Plan 06-07 acceptance criteria verified at commit time:

### Task A
- `grep -c "Check prompt locality (GEN-01)" .github/workflows/ci.yml` → 1 ✓
- `grep -c "bash scripts/check_prompt_locality.sh" .github/workflows/ci.yml` → 1 ✓
- `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` → exit 0 ✓
- `bash scripts/check_prompt_locality.sh` → exit 0 ("OK: no inline prompts outside allowlist") ✓
- Step placed AFTER `Index wrap grep gate (D-21)` step (verified by `grep -B2 -A1 "Check prompt locality"`) ✓
- `git diff --stat .github/workflows/ci.yml` → exactly 1 file, +8/-0 lines ✓

### Task B
- `grep -rc "@pytest.mark.xfail" tests/test_{prompt_locality,prompt_version_hash,generator_stub_determinism,generator_refusal,make_generator,judge_structured_output,generator_search_integration,generator_telemetry,generation_result_schema}.py` → 0 each (9 files swept clean) ✓
- `grep -c "@pytest.mark.xfail" tests/test_generator_real_hero.py` → 1 (preserved per Phase 5 precedent) ✓
- All 21 test function names from Plan 06-01 still present (no test bodies deleted) ✓
- `uv run pytest tests/test_{...the_9_swept_files...}.py -ra -q -m "not real"` → 19 passed, 1 deselected ✓
- `uv run pytest -ra -q -m "not real"` → 140 passed, 0 failed, 0 xfailed, 0 xpassed, 2 skipped, 6 deselected ✓ (matches Wave 3 baseline)

### Task C
- `test -f .planning/phases/06-generation/06-DECISIONS-AUDIT.md` ✓
- `grep -c "^| D-" .planning/phases/06-generation/06-DECISIONS-AUDIT.md` → 17 ✓
- `grep -c "^| CD-" .planning/phases/06-generation/06-DECISIONS-AUDIT.md` → 10 ✓
- `grep -q "27 / 27" .planning/phases/06-generation/06-DECISIONS-AUDIT.md` → present (3 occurrences) ✓
- `grep -q "Pitfall 9" .planning/phases/06-generation/06-DECISIONS-AUDIT.md` → present (4 occurrences) ✓
- `grep -q "Phase Gate" .planning/phases/06-generation/06-DECISIONS-AUDIT.md` → present ✓
- `grep -q "Sign-off" .planning/phases/06-generation/06-DECISIONS-AUDIT.md` → present ✓
- All 4 CI grep gates exit 0 ✓
- `uv lock --check` exit 0 (122 packages) ✓
- `uv run pytest -ra -q -m "not real"` exit 0 ✓
- `uv run mypy --strict packages/*/src` exit 0 (51 source files) ✓

## Post-Wave-4 PROMPT_VERSION_HASH (informational)

The phase-stable PROMPT_VERSION_HASH (for Phase 10 EVAL-02 manifest header):

```
_SYNTHESIS_HASH     = ec466290503d    (971 bytes — SYNTHESIS_PROMPT)
_REFUSAL_HASH       = bf92b696078e    (63 bytes — REFUSAL_PROMPT == REFUSAL_TEXT_SENTINEL)
_JUDGE_HASH         = 8e563d5fbce2    (723 bytes — JUDGE_PROMPT)
PROMPT_VERSION_HASH = dab1bcf7379f    (combined = sha256[:12] of concat)
```

Stability: every hash above has been unchanged since Plan 06-03 commit `90e0409`. Plans 06-05 + 06-06 did not modify the prompt bodies (Plan 06-05 only re-aliased `_STUB_REFUSAL` to track the canonical sentinel value; Plan 06-06 swapped the heuristic regex parser for structured-output dispatch but the JUDGE_PROMPT body is unchanged from Plan 06-03).

This is the value Phase 10 EVAL-02 reads from `docintel_generate.prompts.PROMPT_VERSION_HASH`.

## Total Phase 6 Test Count Delta

Pre-Phase-6 baseline (per Plan 06-01 SUMMARY):
- Stub-mode `-m "not real"`: 121 passed + 2 skipped + 4 deselected

Post-Phase-6 (after Plan 06-07 close):
- Stub-mode `-m "not real"`: 140 passed + 2 skipped + 6 deselected
- Net delta: +19 passed + 2 additional deselected (the 2 `@pytest.mark.real` Phase 6 tests)

Math: 19 stub-mode test functions across 9 test files + 2 real-mode deselected tests (`test_generator_hero_real_mode`, `test_judge_returns_judgeverdict`) = 21 functions total from Plan 06-01 + Plan 06-04's early xfail-removal sweep brought 11 of them to passing inline.

## Phase 6 EMPIRICAL-PENDING Item (routed to workflow_dispatch)

Just one item per the Phase 5 precedent:

- **`tests/test_generator_real_hero.py::test_generator_hero_real_mode`** — the hero multi-hop comparative question end-to-end real-mode test with CD-06 cost (< $0.20) + context-window budget (< 8K prompt_tokens) + multi-COMPANY coverage (≥ 2 distinct cited tickers) assertions. Carries `@pytest.mark.real` + `@pytest.mark.xfail(strict=True, reason="Wave 4 — Plan 06-07 promotes after workflow_dispatch run lands")`.

The xfail marker is preserved on phase-merge per Phase 5's `test_reranker_canary_real_mode` precedent: the FIRST `gh workflow run ci.yml --ref main` post-merge will report PASSED directly (rather than XPASS-strict → developer-removes-marker → PASSED on a second run, which would be the verbose path).

## Hand-off Note for Post-Merge Real-Mode Promotion Run

After the developer approves the audit + the PR merges to `main`:

1. Trigger the real-mode workflow: `gh workflow run ci.yml --ref main`.
2. Wait for the `real-index-build` job to complete (~15-30 min per the Phase 5 precedent timing; CI bumped timeout to 30 min at commit `03023b9`).
3. Locate the `tests/test_generator_real_hero.py::test_generator_hero_real_mode` line in the pytest output:
   - **If PASSED:** Record the run URL + the exact `prompt_tokens` / `completion.cost_usd` / `cited_chunk_ids` values in this SUMMARY's `## Workflow_dispatch verification` section (the analog of Plan 05-07 SUMMARY's hand-off note about run `25896508029`). Phase 6 STRUCTURAL closure becomes EMPIRICAL closure. Phase 7 (Answer schema) can then proceed.
   - **If FAILED:** Apply the debug protocol — confirm the chunk_map loaded (n=6053 per `retriever_chunk_map_loaded`), confirm `SYNTHESIS_PROMPT` was used (verify `prompt_version_hash` field on the generator_completed log line matches `dab1bcf7379f`), confirm the LLM provider was set correctly (`DOCINTEL_LLM_PROVIDER=real`). Then iterate on prompt phrasing or hero-question content. The xfail marker can stay until the run lands PASSED.

The post-merge promotion is the developer's empirical proof point. The audit's Sign-off does not block on this; the strict bite-point lives in workflow_dispatch per the Phase 5 precedent.

## Workflow_dispatch verification

(To be filled in post-merge by the developer; see "Hand-off Note" above.)

## Self-Check

### Files claimed:

- ✓ FOUND: `.github/workflows/ci.yml` (modified; new step present)
- ✓ FOUND: `tests/test_judge_structured_output.py` (modified; xfail decorator removed)
- ✓ FOUND: `.planning/phases/06-generation/06-DECISIONS-AUDIT.md` (created; 199 lines)
- ✓ FOUND: `.planning/phases/06-generation/06-07-SUMMARY.md` (this file)

### Commits claimed:

- ✓ FOUND: `426d2ad` (Task A)
- ✓ FOUND: `95d46a6` (Task B)
- ✓ FOUND: `47da071` (Task C)

## Self-Check: PASSED

All claimed files exist; all claimed commits exist. Phase 6 ready for developer review of the Decision-Coverage Audit, then merge to `main`, then post-merge workflow_dispatch promotion of `test_generator_hero_real_mode`.
