---
phase: 14
plan: 01
subsystem: empirical-closure
tags: [phase-14, wave-0, xfail-scaffold, empirical-closure, EMP-01, EMP-02, EMP-03, EMP-04, EMP-05]
dependency_graph:
  requires: []
  provides:
    - "Red xfail-strict scaffolds for EMP-01..EMP-05 (the red→green chain that downstream plans 14-02..14-07 will flip green)"
    - "Two planted-fixture dirs (negative + positive) that 14-04's `check_before_sleep_safe.sh` gate will be tested against"
  affects:
    - "14-02 will rename data/eval/ground_truth/questions.jsonl → eval_set.jsonl and backfill EVAL_SET_SHA256 in tests/test_eval_set_frozen.py + remove the xfail marker"
    - "14-03 will land packages/docintel-core/src/docintel_core/adapters/real/_logging.py (before_sleep_safe + _REDACT_PATTERN) + remove the xfail marker on tests/test_before_sleep_redacts_api_keys.py"
    - "14-04 will land scripts/check_before_sleep_safe.sh + sweep the 12 use-sites across 6 files (per RESEARCH Pitfall 1 correction) + remove the xfail markers on tests/test_check_before_sleep_safe.py"
    - "14-05 will land make baseline-lock Makefile target (data/eval/baseline.json schema producer)"
    - "14-06 will land the D-10 README PASTE-REAL-NUMBERS mechanical swap + remove the xfail markers on tests/test_baseline_schema.py / test_baseline_cost_matches.py / test_readme_no_stub_banner.py"
    - "14-07 (phase gate) preserves the tests/test_hero_gif_present.py EMPIRICAL-PENDING marker per Phase 5 test_reranker_canary_real_mode precedent"
tech-stack:
  added: []  # No new pip deps — uses stdlib hashlib + re + datetime + json + pathlib + already-installed pytest + tenacity
  patterns:
    - "Wave-0 xfail-strict scaffolds (project convention from Phases 06/11/12/13)"
    - "Planted-fixture trio (negative / canonical / positive) mirroring tests/test_no_print_gate.py:43-111"
    - "Path-anchor + repo-root walk-up helper (verbatim from tests/test_docs_gates.py:16-26)"
    - "Module-level hardcoded constant for byte-identity freeze (mirrors tests/test_eval_dataset_schema.py constants pattern)"
key-files:
  created:
    - tests/test_eval_set_frozen.py
    - tests/test_before_sleep_redacts_api_keys.py
    - tests/test_check_before_sleep_safe.py
    - tests/test_baseline_schema.py
    - tests/test_baseline_cost_matches.py
    - tests/test_readme_no_stub_banner.py
    - tests/test_hero_gif_present.py
    - tests/fixtures/before_sleep_violations/_unsafe_example.py
    - tests/fixtures/before_sleep_violations_with_safe/safe_example.py
  modified: []
decisions:
  - "EVAL_SET_SHA256 placeholder is the literal string <TO_BE_FILLED_IN_AT_FREEZE_TIME> with the cross-cutting `# frozen Phase 14; mutation requires ADR per D-03` comment (D-02)"
  - "Redaction test cases parametrized in D-05 order (sk-ant- precedes sk-) so the order-matters invariant is exercised, not merely documented (D-05)"
  - "Tenacity-driven RetryCallState (not hand-mocked) per Pitfall 3 — avoids the None-guard footgun and exercises the canonical before_sleep callable shape"
  - "_unsafe_example.py uses a leading underscore so the gate's canonical scan never trips on the planted negative fixture (mirrors no_print_violations/offender.py escape convention)"
  - "test_hero_gif_present.py xfail reason carries the literal string 'EMPIRICAL-PENDING D-11' so 14-07 phase gate can grep for honest-pending status (preserved past phase gate, mirroring Phase 5 test_reranker_canary_real_mode precedent)"
metrics:
  duration: "~30 min"
  completed: "2026-05-31"
  tasks: 2
  files_created: 9
  commits:
    - "86ced1e: test(14-01): land Wave-0 xfail-strict scaffolds for EMP-04 + EMP-05"
    - "ab80488: test(14-01): land Wave-0 xfail-strict scaffolds for EMP-01 + EMP-02 + EMP-03"
---

# Phase 14 Plan 01: Wave-0 EMPIRICAL-PENDING xfail-strict scaffolds Summary

**One-liner:** Seven red xfail-strict test scaffolds + two planted-fixture dirs covering all five Phase-14 requirements (EMP-01..EMP-05), each carrying a `# xfail until <plan-id>` reason that names the downstream plan that flips it green.

## What landed

| File | Lines | Purpose | Flips green via |
|------|-------|---------|-----------------|
| `tests/test_eval_set_frozen.py` | 80 | EMP-04 / D-02 hardcoded `EVAL_SET_SHA256` byte-identity assertion against `data/eval/ground_truth/eval_set.jsonl` | Plan 14-02 (rename + SHA backfill) |
| `tests/test_before_sleep_redacts_api_keys.py` | 117 | EMP-05 / D-05 four parametrized redaction cases (sk-ant- precedes sk- to exercise order-matters invariant; pa-; Bearer) driving a real tenacity `@retry` (Pitfall 3 recipe) | Plan 14-03 (`_logging.before_sleep_safe`) |
| `tests/test_check_before_sleep_safe.py` | 137 | EMP-05 / D-06 three-function gate trio (negative SCAN_DIR → non-zero; canonical → zero; positive SCAN_DIR → zero) mirroring `tests/test_no_print_gate.py:43-111` verbatim | Plan 14-04 (gate script + 12-site sweep) |
| `tests/test_baseline_schema.py` | 130 | EMP-01 / D-07 7-field schema validation (`report_dir`, `git_sha`, `eval_set_sha256`, `prompt_version_hash`, `phase_locked==14`, `cost_usd`, `locked_at`) | Plan 14-06 (user runs `make baseline-lock`) |
| `tests/test_baseline_cost_matches.py` | 79 | D-09 three-way cross-check `baseline.cost_usd == manifest.total_cost_usd == sum(per_question.cost_usd)` via `pytest.approx(abs=1e-6)` | Plan 14-06 |
| `tests/test_readme_no_stub_banner.py` | 91 | EMP-02 / D-10 slice `PASTE-REAL-NUMBERS` HTML-comment block via `re.search(..., re.DOTALL)`; assert `representative: false` absent AND `representative: true` present | Plan 14-06 (mechanical paste) |
| `tests/test_hero_gif_present.py` | 96 | EMP-03 / D-11 presence + non-zero-size + mtime > `baseline.locked_at` (ordering invariant); xfail reason carries the literal `EMPIRICAL-PENDING D-11` marker for 14-07 honest-pending status report | Manual / user-owned (NOT auto-flipped by any plan; preserved past phase gate per Phase 5 precedent) |
| `tests/fixtures/before_sleep_violations/_unsafe_example.py` | 47 | Planted negative fixture; leading-underscore filename so the canonical scan path-filter skips it; contains `@retry(before_sleep=before_sleep_log(...))` | Used by 14-04's gate-script tests |
| `tests/fixtures/before_sleep_violations_with_safe/safe_example.py` | 39 | Planted positive fixture; `@retry(before_sleep=before_sleep_safe(...))` + `from docintel_core.adapters.real._logging import before_sleep_safe` | Used by 14-04's gate-script tests |

## Red→green chain map

| Wave-0 file | xfail reason text | Downstream flipper plan |
|-------------|-------------------|-------------------------|
| `test_eval_set_frozen.py` | `xfail until 14-02: D-01 rename to eval_set.jsonl + EVAL_SET_SHA256 backfill` | **14-02** |
| `test_before_sleep_redacts_api_keys.py` (× 4 parametrize cases) | `xfail until 14-03: _logging.before_sleep_safe lands` | **14-03** |
| `test_check_before_sleep_safe.py::test_gate_fails_on_planted_raw_before_sleep_log` | `xfail until 14-04: gate script + sweep (scripts/check_before_sleep_safe.sh)` | **14-04** |
| `test_check_before_sleep_safe.py::test_gate_passes_on_canonical_adapters_real` | `xfail until 14-04: gate script + sweep (12 sites across 6 files per Pitfall 1)` | **14-04** |
| `test_check_before_sleep_safe.py::test_gate_passes_on_positive_fixture` | `xfail until 14-04: gate script + sweep (scripts/check_before_sleep_safe.sh)` | **14-04** |
| `test_baseline_schema.py` | `xfail until 14-06: user runs make baseline-lock TS=<ts> after real-eval commits report` | **14-06** |
| `test_baseline_cost_matches.py` | `xfail until 14-06: user runs make baseline-lock (cost_usd cross-check requires baseline.json + results.json)` | **14-06** |
| `test_readme_no_stub_banner.py` | `xfail until 14-06: README real-numbers paste via make readme-paste flips representative:false -> representative:true in PASTE-REAL-NUMBERS block` | **14-06** |
| `test_hero_gif_present.py` | `EMPIRICAL-PENDING D-11: user records docs/hero.gif AFTER baseline.json lock per docs/REAL-RUN-CHECKLIST.md (Phase 14 phase-gate preserves this marker per Phase 5 precedent)` | **User-owned** (preserved past 14-07) |

## Verification

**Pytest collection (must-have artifact #1 — 11+ collected tests):**
```
uv run pytest --collect-only tests/test_eval_set_frozen.py tests/test_baseline_schema.py tests/test_baseline_cost_matches.py tests/test_before_sleep_redacts_api_keys.py tests/test_check_before_sleep_safe.py tests/test_readme_no_stub_banner.py tests/test_hero_gif_present.py -q
→ 12 tests collected in 0.01s
```
(test_eval_set_frozen 1 + test_baseline_schema 1 + test_baseline_cost_matches 1 + test_before_sleep_redacts 4 (parametrize) + test_check_before_sleep_safe 3 + test_readme_no_stub_banner 1 + test_hero_gif_present 1 = 12)

**Plan-scope pytest run (must-have artifact #4 — 0 unexpected pass / XPASS):**
```
uv run pytest tests/test_eval_set_frozen.py tests/test_baseline_schema.py tests/test_baseline_cost_matches.py tests/test_before_sleep_redacts_api_keys.py tests/test_check_before_sleep_safe.py tests/test_readme_no_stub_banner.py tests/test_hero_gif_present.py -ra -q
→ 12 xfailed in 0.07s
```
All 12 collected tests xfail as designed. Zero XPASS. Zero unexpected pass.

**Existing suite regression check:**
```
uv run pytest -ra -q -m "not real"
→ 249 passed, 2 skipped, 8 deselected, 12 xfailed in 40.81s
```
No regressions. The 3 pre-existing failures observed during the cold-cache `uv sync` baseline (BM25 artifacts + generator hero) resolved on subsequent runs once `data/indices/` was populated; they are out-of-scope for Wave-0 scaffolds regardless. The Wave-0 scaffolds added exactly the 12 expected xfails — nothing else.

**Fixtures NOT pytest-collected (must-have artifact #5):**
```
uv run pytest --collect-only tests/fixtures/ -q 2>&1 | grep -E '_unsafe_example|safe_example'
→ (empty — pytest correctly skips fixture files)
```

**Static acceptance criteria (Task 1):** 13/13 pass — see plan acceptance_criteria block.
**Static acceptance criteria (Task 2):** 12/12 pass — see plan acceptance_criteria block.

## Deviations from Plan

**None.** Plan executed exactly as written. Two minor docstring polish edits during Task 1 (to satisfy the acceptance criterion `grep -c 'TO_BE_FILLED_IN_AT_FREEZE_TIME' == 1` and `grep -c 'questions.jsonl' == 0`) — these were cosmetic adjustments to the scaffold-file docstrings to keep the gate-grep assertions clean; no behavioral changes to the test assertions themselves.

## Threat Flags

None — Wave 0 lands no production code, only test scaffolds + planted fixtures. The fake-key strings in `tests/test_before_sleep_redacts_api_keys.py` are clearly fake patterns (e.g., `sk-1234567890abcdefghij1234567890abcdef`) that the existing gitleaks CI allowlist (`.github/workflows/ci.yml:180-193`) is configured to ignore. No real secrets present.

## Known Stubs

None — every test in Wave 0 has its production code wired or scheduled in a named downstream plan (14-02..14-06). The `test_hero_gif_present.py` EMPIRICAL-PENDING marker is intentional and tracked by 14-07 honest-pending status convention.

## Threat Model — Mitigations Applied

- **T-14-01** (Tampering — Wave-0 scaffolds silently passing pre-implementation): mitigated via xfail-strict on every test (`pytest.mark.xfail(strict=True, ...)`); XPASS fails the suite. Confirmed via Wave-0 run (12 xfailed, 0 XPASS).
- **T-14-02** (Tampering — planted negative leaking into canonical D-06 gate scan): mitigated via leading-underscore filename `_unsafe_example.py` + dedicated fixture dir outside `packages/`; the gate's default scan target is `adapters/real/` only, never `tests/`.
- **T-14-03** (Information Disclosure — planted fixture API key strings): accepted — strings are clearly fake (20+ alphanumeric chars after the prefix); existing gitleaks allowlist covers the pattern.
- **T-14-04** (Tampering — hero-gif xfail marker becoming permanently dormant): mitigated via the literal `EMPIRICAL-PENDING D-11` string in the xfail reason so 14-07 phase gate can grep for honest-pending status.
- **T-EMP-04** (API key leakage through `before_sleep_log`): the Wave-0 redaction test scaffold + planted fixtures establish the START of the chain (Wave 0 red → Wave 1 helper → Wave 2 sweep + CI gate); the threat is structurally closed by the 14-03/14-04 sequence.
- **T-14-SC** (Supply-chain — new pip installs): accepted — zero new pip deps introduced; legitimacy gate trivially satisfied.

## Self-Check: PASSED

**Files exist:**
- FOUND: tests/test_eval_set_frozen.py
- FOUND: tests/test_before_sleep_redacts_api_keys.py
- FOUND: tests/test_check_before_sleep_safe.py
- FOUND: tests/test_baseline_schema.py
- FOUND: tests/test_baseline_cost_matches.py
- FOUND: tests/test_readme_no_stub_banner.py
- FOUND: tests/test_hero_gif_present.py
- FOUND: tests/fixtures/before_sleep_violations/_unsafe_example.py
- FOUND: tests/fixtures/before_sleep_violations_with_safe/safe_example.py

**Commits exist:**
- FOUND: 86ced1e (test(14-01): land Wave-0 xfail-strict scaffolds for EMP-04 + EMP-05)
- FOUND: ab80488 (test(14-01): land Wave-0 xfail-strict scaffolds for EMP-01 + EMP-02 + EMP-03)
