---
phase: 14-empirical-closure
plan: 2
subsystem: eval-set freeze + ADR codification
tags: [phase-14, wave-1, emp-04, rename, sha256-freeze, adr-013]
requirements: [EMP-04]
dependency_graph:
  requires:
    - 14-01 (Wave-0 xfail-strict scaffold at tests/test_eval_set_frozen.py with EVAL_SET_SHA256 placeholder constant)
    - data/eval/ground_truth/questions.jsonl (32-record committed dataset; renamed in this plan)
    - DECISIONS.md (12 prior ADRs; ADR-013 appended)
  provides:
    - frozen-eval-set-sha256:5d9f879207c6b8a0c363804eebb9add4babefaa63beadcea7dc80dbd8db88d82
    - eval-set-path:data/eval/ground_truth/eval_set.jsonl
    - mutation-policy:DECISIONS.md ADR-013 (4-step protocol)
    - test-gate-green:tests/test_eval_set_frozen.py::test_eval_set_sha256_matches_frozen_constant
  affects:
    - "Phase 14 plans 14-03..14-07: any further code touching the eval set reads eval_set.jsonl, not questions.jsonl"
    - "Phase 17 paired-bootstrap deltas: ADR-013 supersession protocol now codified; mid-dev mutations require an explicit ADR-014/015/... allocation"
    - "data/eval/baseline.json (per D-07): Phase 17 plans cross-check the frozen SHA256 declaratively"
tech_stack:
  added: []
  patterns:
    - "git mv (not delete+create) preserves history across rename — git log --follow finds the pre-rename commits"
    - "Module-scope hardcoded constant pattern (mirrors 5 CI grep-gate constants) for SHA256 freeze"
    - "Single ADR template (Context / Decision / Consequences with `+` and `-` bullets) extended ADR-001 through ADR-013"
key_files:
  created:
    - .planning/phases/14-empirical-closure/14-02-SUMMARY.md
  modified:
    - data/eval/ground_truth/eval_set.jsonl (renamed from questions.jsonl via git mv; bytes unchanged)
    - packages/docintel-eval/src/docintel_eval/runner.py (line 167 + 353 + 364 — path constant + local var + log key)
    - packages/docintel-eval/src/docintel_eval/ablate.py (line 79-81 + 461 — _QUESTIONS_PATH renamed to _EVAL_SET_PATH)
    - packages/docintel-eval/src/docintel_eval/validate.py (6 sites — 4 docstring/comment + 1 path constant + 1 local var)
    - tests/test_eval_dataset_schema.py (11 sites — module-level constant + fixture + docstrings + assertion strings)
    - tests/test_eval_harness.py (line 36 — _QUESTIONS_PATH renamed to _EVAL_SET_PATH)
    - tests/test_eval_traces.py (line 63 — local Path call)
    - tests/test_eval_set_frozen.py (placeholder backfilled with real SHA256; xfail-strict decorator removed; module docstring + unused pytest import cleaned up)
    - DECISIONS.md (ADR-013 appended — 71 net new lines)
decisions:
  - "D-01 rename: applied via git mv (preserves history). Bytes unchanged → existing data/eval/reports/stub-sample/results.json manifest.dataset_hash stays valid (sha256 of bytes, not path string)."
  - "D-02 SHA256 storage: backfilled module-scope constant in tests/test_eval_set_frozen.py with the real 64-char hex 5d9f879207c6b8a0c363804eebb9add4babefaa63beadcea7dc80dbd8db88d82."
  - "D-03 mutation policy: codified verbatim in DECISIONS.md ADR-013 with explicit cross-references to EVAL_SET_SHA256, baseline.json, and Phase 17."
  - "Function name load_questions left unchanged (per RESEARCH §Runtime State Inventory lines 537-538) — only the path argument + the local var/constant names rename. The exported API stays stable so downstream callers (validate, ablate, runner, tests) only see the path change."
  - "runner.py also got 2 secondary edits at lines 353/364 (dataset_hash call + structlog key) for consistency with the new local var name eval_set_path. The plan's 9-site enumeration captured the first (line 167); the 2 follow-on sites in the same function are intrinsic to renaming the local var per the plan's '...consistently through the rest of that function' clause."
metrics:
  duration: "~6 minutes wall-clock (3 read + 2 commit waves)"
  completed_date: "2026-05-31"
  tasks_completed: "2/2"
  files_changed: 9
  lines_added: 117
  lines_removed: 58
---

# Phase 14 Plan 02: Eval-set rename + SHA256 freeze + ADR-013 Summary

Atomic rename of `data/eval/ground_truth/questions.jsonl` → `eval_set.jsonl` (D-01) + 9-site grep-replace cascade (RESEARCH Pitfall 2) + EVAL_SET_SHA256 constant backfilled with the real 64-char hex of the renamed file (D-02) + DECISIONS.md ADR-013 codifying the D-03 4-step mutation policy. After this plan: `grep -rn 'questions\.jsonl' packages tests docs scripts` returns empty, the Wave-0 xfail-strict test runs green, and Phase 17 paired-bootstrap deltas have a written supersession protocol.

## What This Plan Delivered

- **Atomic rename via `git mv`** — `data/eval/ground_truth/questions.jsonl` → `eval_set.jsonl`. Bytes preserved, history followable via `git log --follow`.
- **9-site grep cascade** — 1 source path (`runner.py:167`), 1 module constant (`ablate.py:81`), 5 sites in `validate.py` (4 docstring/comment + 1 path constant + 1 local var), 4 test files (`test_eval_traces.py:63`, `test_eval_dataset_schema.py` 11 occurrences, `test_eval_harness.py:36`, `test_eval_set_frozen.py`). Plus 2 follow-on renames in `runner.py` lines 353/364 for local-var consistency.
- **SHA256 backfill** — `tests/test_eval_set_frozen.py::EVAL_SET_SHA256` set to the actual `sha256(eval_set.jsonl)` hex `5d9f879207c6b8a0c363804eebb9add4babefaa63beadcea7dc80dbd8db88d82`. The `<TO_BE_FILLED_IN_AT_FREEZE_TIME>` placeholder and the `@pytest.mark.xfail(strict=True, reason="xfail until 14-02: ...")` decorator are gone. The test runs green; any future byte-level mutation flips it red with a pointer at ADR-013.
- **DECISIONS.md ADR-013** — codifies the D-03 4-step mutation policy (ADR + EVAL_SET_SHA256 update + fresh `representative: true` real-eval report + `data/eval/baseline.json` update per D-07) with explicit cross-references to the test file, the baseline pointer, and Phase 17. Brings the ADR count to 13 (the `test_docs_gates.py` ≥ 8 floor stays comfortable).

## Frozen SHA256

```
EVAL_SET_SHA256 = "5d9f879207c6b8a0c363804eebb9add4babefaa63beadcea7dc80dbd8db88d82"
```

This is the byte-identical sha256 of `data/eval/ground_truth/eval_set.jsonl` after the `git mv`. It also matches the `dataset_hash` field in `data/eval/reports/stub-sample/results.json` (the rename doesn't change the file bytes, only the path).

## ADR-013 — Eval-set mutation policy (Phase 14 D-03)

Verbatim 4-step protocol any future mutation MUST follow:

1. **Write a new ADR in `DECISIONS.md`** documenting the change, the reviewer-visible reason it could not wait for v2.0, and the previous baseline being superseded.
2. **Update `EVAL_SET_SHA256`** in `tests/test_eval_set_frozen.py` to the fresh `sha256(open(eval_set.jsonl,"rb").read()).hexdigest()`.
3. **Re-run real-eval** via `gh workflow run real-eval` to produce a fresh `representative: true` report under `data/eval/reports/<ts>/`. The report's `manifest.dataset_hash` MUST match the new `EVAL_SET_SHA256` (existing `validate.py:248-259` gate asserts this on every committed report dir).
4. **Update `data/eval/baseline.json`** per D-07 to point at the new report dir + its `eval_set_sha256`. Phase 17 plans MUST validate against the baseline they declare; the mismatch error message names this ADR.

ADR-013's Consequences section makes the contract explicit: paired-bootstrap deltas stay interpretable across phases (`+`), CI catches accidental mutations loudly (`+`), the baseline.json cross-check makes Phase 17 declarative (`+`), but legitimate fixes require the full re-baseline cycle including a real-eval run (`-`), and Phase 17 mid-dev runs that touch the eval set must allocate ADR-014/015/... numbers for each supersession (`-`).

## Verification

All `<verification>` clauses in `14-02-PLAN.md` pass:

```
test -f data/eval/ground_truth/eval_set.jsonl   → PASS
! test -f data/eval/ground_truth/questions.jsonl → PASS
grep -rn 'questions\.jsonl' packages tests docs scripts → zero matches (PASS)
grep -c '^## ADR-' DECISIONS.md → 13 (PASS — was 12 pre-plan)
grep -c '^## ADR-013' DECISIONS.md → 1 (PASS)
ADR-013 contains EVAL_SET_SHA256 → 3 occurrences (PASS)
ADR-013 contains baseline.json → 2 occurrences (PASS)
ADR-013 contains tests/test_eval_set_frozen.py → 2 occurrences (PASS)
ADR-013 contains "Phase 17" → 5 occurrences (PASS)
ADR-013 contains 4 numbered steps → PASS
ADR-013 has ≥ 2 `- +` bullets and ≥ 2 `- -` bullets → PASS (3 `+`, 2 `-`)
pytest tests/test_eval_set_frozen.py tests/test_eval_dataset_schema.py
       tests/test_eval_harness.py tests/test_eval_traces.py
       tests/test_docs_gates.py -ra -q → 28 passed, 0 failed, 0 xfailed
```

Test counts by file:
- `test_eval_set_frozen.py` — 1 passed (was 1 xfail before this plan; xfail decorator removed and SHA256 matches)
- `test_eval_dataset_schema.py` — 12 passed
- `test_eval_harness.py` — 13 passed
- `test_eval_traces.py` — 1 passed
- `test_docs_gates.py` — 1 passed (the ≥ 8 ADR-count gate stays green at the new count of 13)

## Commits

| Commit | Type | Description |
|--------|------|-------------|
| `0eccfe2` | refactor(14-02) | rename ground-truth questions.jsonl -> eval_set.jsonl + backfill SHA256 (8 files: 1 rename + 7 modifications) |
| `2ad6f0d` | docs(14-02) | add ADR-013 codifying D-03 4-step eval-set mutation policy (1 file: DECISIONS.md +71 net lines) |

## Deviations from Plan

**None directly.** Two micro-elaborations on the plan's `<action>` directive deserve transparent capture:

1. **Two follow-on local-var renames in `runner.py`** (lines 353 + 364). The plan enumerated 9 grep-replace sites (one per file), with `runner.py:167` as the entry. The plan's action body says "rename the local var consistently through the rest of that function" — lines 353 (`_dataset_hash(questions_path)` → `_dataset_hash(eval_set_path)`) and 364 (`log.error("eval_run_no_questions", questions_path=str(questions_path))` → `... eval_set_path=str(eval_set_path)`) are the same local variable consumed in the function and were updated for consistency. Net effect: zero behavior change, zero added scope, the grep gate stays empty.

2. **Test scaffold docstring + unused import cleanup.** When I removed the `@pytest.mark.xfail(...)` decorator from `tests/test_eval_set_frozen.py`, `import pytest` became unused (would trip ruff `F401` next CI run). I removed it. I also rewrote the Wave-0-vintage module docstring to reflect the now-shipped state (replacing "lands this red" with "Plan 14-02 backfilled the digest... and removed the xfail marker so any future byte-level mutation surfaces as CI fail"). The replacement docstring still cites D-01/D-02/D-03/D-07 and is grep-clean for `questions.jsonl`. Net effect: ruff stays happy, the file's narrative matches its post-14-02 state.

Neither qualifies as a Rule-1..4 deviation — both are intrinsic to the plan's "remove xfail marker" + "rename consistently through the rest of that function" directives.

## Authentication Gates

None — no API keys touched. Plan is pure-Python file shuffling + Markdown editing.

## Known Stubs

None introduced. The renamed file is the existing 32-record committed eval set; no stub data, no placeholder text, no TODO/FIXME shipped.

## Threat Flags

None new. The plan's own `<threat_model>` enumerated T-14-05/06/07 (eval-set tampering, incomplete rename, git history loss); all three mitigations now wired in:

- **T-14-05 (Tampering)** — `tests/test_eval_set_frozen.py` byte-identity gate green; ADR-013 4-step protocol codified in `DECISIONS.md`.
- **T-14-06 (Stale refs)** — post-rename `grep -rn 'questions\.jsonl' packages tests docs scripts` returns empty (verified).
- **T-14-07 (History loss)** — `git mv` used; `git log --follow data/eval/ground_truth/eval_set.jsonl` finds the pre-rename commits `8ca824d`, `52bd80f`, `fb60234`, `c5e89c6`.

## How To Resume

This plan is complete. Wave 1 of Phase 14 has now shipped:
- ✓ Plan 14-01: Wave-0 xfail-strict scaffolds (already merged at `79e574b`)
- ✓ Plan 14-02: D-01 rename + D-02 SHA256 freeze + D-03 ADR-013 (this plan)

Next in the phase: Plan 14-03+ (further EMP-XX closure) — see `.planning/phases/14-empirical-closure/14-03-PLAN.md` for the next wave.

The orchestrator owns post-wave merges and STATE.md/ROADMAP.md updates.

## Self-Check: PASSED

**Files exist:**
- `FOUND: data/eval/ground_truth/eval_set.jsonl`
- `FOUND: tests/test_eval_set_frozen.py` (SHA256 backfilled, xfail marker removed)
- `FOUND: DECISIONS.md` (ADR-013 appended; count = 13)
- `MISSING (expected): data/eval/ground_truth/questions.jsonl` (renamed via git mv)

**Commits exist:**
- `FOUND: 0eccfe2` (refactor(14-02): rename ground-truth questions.jsonl -> eval_set.jsonl + backfill SHA256)
- `FOUND: 2ad6f0d` (docs(14-02): add ADR-013 codifying D-03 4-step eval-set mutation policy)
