---
phase: 14-empirical-closure
plan: 04
subsystem: adapters/observability/ci
tags: [phase-14, wave-2, emp-05, sweep, ci-gate, p-emp-04, t-emp-04, d-06]
dependency_graph:
  requires:
    - phase: 14-03
      provides: "before_sleep_safe(logger, log_level) factory + _REDACT_PATTERN + _redact helper at packages/docintel-core/src/docintel_core/adapters/real/_logging.py — the import target the 12 sweep sites depend on"
    - phase: 14-01
      provides: "Wave-0 xfail-strict scaffold at tests/test_check_before_sleep_safe.py (3-function trio: negative / canonical / positive) + tests/fixtures/before_sleep_violations/_unsafe_example.py (negative) + tests/fixtures/before_sleep_violations_with_safe/safe_example.py (positive) — the trio Plan 14-04 Task 3 flips green"
  provides:
    - "12 before_sleep_safe use-sites across 6 adapter files (RESEARCH Pitfall 1 verified count): qdrant_dense.py × 6, judge.py × 2, embedder_bge.py × 1, llm_anthropic.py × 1, llm_openai.py × 1, reranker_bge.py × 1"
    - "scripts/check_before_sleep_safe.sh — 6th CI grep gate (D-06 two-sided: Side A no raw before_sleep_log + Side B every @retry-using file imports before_sleep_safe)"
    - ".github/workflows/ci.yml — gate step `Check before_sleep_safe (EMP-05 / P-EMP-04)` wired in the lint-and-test job between gate 5 (`Check no print (OBS-03)`) and `Chunk-idempotency gate (ING-04)`"
    - "tests/test_check_before_sleep_safe.py — 3 xfail markers removed; trio now passes green via subprocess invocation of the gate against canonical / negative / positive scan dirs"
  affects:
    - "EMP-05 is structurally closed. The helper (14-03) + sweep + gate + CI chain is now end-to-end: no API key can leak through tenacity retry-path logs into committed CI eval-report manifests, and the gate fires at PR time if a future adapter reintroduces a raw `before_sleep_log` call OR lands an @retry( without the safe import"
    - "Phase 17 paired-bootstrap baseline reads — the closure is structural, not just code-review-dependent"
tech-stack:
  added: []  # No new pip deps — pure shell + Python edits + CI YAML wiring
  patterns:
    - "Two-sided CI grep gate (D-06): mirrors check_adapter_wraps.sh shape verbatim (shebang + set -euo pipefail + REAL_ADAPTERS=${1:-...} + PROBLEM=0 + final OK + exit $PROBLEM). Side A is `grep -rn` for the forbidden symbol; Side B is `grep -rl '@retry('` + per-file check for the safe import"
    - "Docstring substring discipline applied (Plan 14-03 precedent): the gate is text-based, so docstring/comment mentions of the forbidden symbol trip Side A. Every swept adapter file's SP-3 comment block now references `before_sleep_safe` instead of `before_sleep_log`; the qdrant_dense.py module docstring + judge.py inline comment block were also rewritten"
    - "Insertion convention: new CI grep gates are added adjacent to the existing gates (between gate 5 and the chunk-idempotency gate), preserving the lint-and-test job's reading order"
key-files:
  created:
    - scripts/check_before_sleep_safe.sh
  modified:
    - packages/docintel-core/src/docintel_core/adapters/real/embedder_bge.py
    - packages/docintel-core/src/docintel_core/adapters/real/llm_anthropic.py
    - packages/docintel-core/src/docintel_core/adapters/real/llm_openai.py
    - packages/docintel-core/src/docintel_core/adapters/real/reranker_bge.py
    - packages/docintel-core/src/docintel_core/adapters/real/qdrant_dense.py
    - packages/docintel-core/src/docintel_core/adapters/real/judge.py
    - packages/docintel-core/src/docintel_core/adapters/real/_logging.py
    - .github/workflows/ci.yml
    - tests/fixtures/before_sleep_violations_with_safe/safe_example.py
    - tests/test_check_before_sleep_safe.py
decisions:
  - "Pitfall 1 verified surface = 12 sites across 6 files. CONTEXT.md D-04's '6 across 5' undercount was the original blocker — RESEARCH Pitfall 1 corrected it before the sweep, so the per-file site table (qdrant_dense × 6, judge × 2, others × 1 each) drove the swap arithmetic. The total `grep -c 'before_sleep=before_sleep_safe' adapters/real/` returns exactly 12 — sum verified per file."
  - "Relative `from ._logging import before_sleep_safe` (vs absolute `from docintel_core.adapters.real._logging import ...`) chosen for all 6 swept files. Both are accepted by the D-06 gate; the relative form is one line shorter and matches the convention of adapters/real/ being a single package directory."
  - "Two unplanned docstring repairs needed (Rule 3 - blocking issue) to make the gate's text-based Side A pass on (a) the helper module itself and (b) the positive fixture. The helper's docstring referenced `@retry(... )` which tripped Side B (no @retry-using file may exist without the safe import) — rewritten to `@retry` (no paren). The positive fixture's docstring referenced the literal symbol name in prose — rewritten to `canonical-symbol usage`. Both edits are prose-only, no API surface affected. This precedent extends Plan 14-03's 'docstring substring discipline'."
  - "Gate's exit-code semantics chosen to mirror check_adapter_wraps.sh exactly: 0 = OK, 1 = at least one violation (either side). Wave-0 trio asserts exit-code identity (`returncode == 0` for canonical/positive, `returncode != 0` for negative) — the subprocess-based test doesn't parse stderr, just inspects exit codes, so the gate's print statements are advisory only."
metrics:
  duration: "~15 min"
  completed: "2026-05-31"
  tasks: 3
  files_created: 1
  files_modified: 10
  commits:
    - "d08e5a4: refactor(14-04): sweep 12 before_sleep_log call-sites to before_sleep_safe"
    - "211226d: feat(14-04): ship D-06 two-sided gate + wire 6th CI step"
    - "6578211: test(14-04): flip Wave-0 gate-trio xfail markers green"
requirements-completed: [EMP-05]
---

# Phase 14 Plan 04: EMP-05 sweep + D-06 CI gate Summary

**12 before_sleep_log call-sites across 6 adapter files swapped to before_sleep_safe; scripts/check_before_sleep_safe.sh ships as the 6th CI grep gate (D-06 two-sided); Wave-0 gate-trio flipped green. EMP-05 is structurally closed.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 3
- **Files created:** 1 (`scripts/check_before_sleep_safe.sh`)
- **Files modified:** 10 (6 adapters + helper + CI YAML + positive fixture + trio test)

## Accomplishments

- **Task 1 sweep (12 sites / 6 files):** every `before_sleep=before_sleep_log(_retry_log, logging.WARNING)` use-site replaced with `before_sleep=before_sleep_safe(_retry_log, logging.WARNING)`; every `from tenacity import (...)` block had `before_sleep_log` dropped; every file gained a new sibling import `from ._logging import before_sleep_safe`. Per-file site enumeration matches RESEARCH Pitfall 1 verbatim: `qdrant_dense.py × 6` (lines 374, 385, 399, 416, 431, 448), `judge.py × 2` (lines 129, 244 — module-level @retry, not class-method), `embedder_bge.py × 1` (line 85), `llm_anthropic.py × 1` (line 106), `llm_openai.py × 1` (line 108), `reranker_bge.py × 1` (line 74). Every file's SP-3 two-logger comment block (and qdrant_dense.py's module docstring) was also rewritten to reference `before_sleep_safe` so the text-based Side A grep stays clean.
- **Task 2 gate + CI wiring:** `scripts/check_before_sleep_safe.sh` (mode 0755) mirrors `scripts/check_adapter_wraps.sh` shape verbatim (shebang + comment header + `set -euo pipefail` + `REAL_ADAPTERS="${1:-...}"` + `PROBLEM=0`). Body is the D-06 two-sided assertion: Side A `grep -rn "before_sleep_log" "$REAL_ADAPTERS"` must exit empty; Side B `for f in $(grep -rl "@retry(" "$REAL_ADAPTERS")` checks each file imports `before_sleep_safe` from `._logging` (or absolute equivalent). `.github/workflows/ci.yml` gained a 6th step `Check before_sleep_safe (EMP-05 / P-EMP-04)` inserted between `Check no print (OBS-03)` (line 163) and `Chunk-idempotency gate (ING-04)` (line 178) — gate header lands at line 169, run-line at line 176.
- **Task 3 xfail flip:** all 3 `@pytest.mark.xfail(strict=True, reason="xfail until 14-04: ...")` decorators on `tests/test_check_before_sleep_safe.py` removed. Trio (negative / canonical / positive) now passes green via subprocess invocation of the gate against the corresponding scan dirs.
- **EMP-05 fully closed:** helper (14-03) → sweep (this plan Task 1) → gate (this plan Task 2) → CI (this plan Task 2) → trio (this plan Task 3). No API key can structurally leak through a tenacity retry-path log into a committed CI eval-report manifest; regression is caught at PR time by the 6th gate.

## Task Commits

Each task was committed atomically:

1. **Task 1: Sweep all 12 `before_sleep_log` call-sites across 6 adapter files** — `d08e5a4` (refactor)
2. **Task 2: Ship `scripts/check_before_sleep_safe.sh` + wire 6th CI step + docstring repairs** — `211226d` (feat)
3. **Task 3: Flip Wave-0 gate-trio xfail markers green** — `6578211` (test)

## Files Created/Modified

### Created

- `scripts/check_before_sleep_safe.sh` (mode 0755, 49 lines)
  - Mirrors `check_adapter_wraps.sh` shape (shebang + comment header + `set -euo pipefail` + `REAL_ADAPTERS="${1:-...}"` + `PROBLEM=0` + final `OK` echo + `exit "$PROBLEM"`)
  - Side A: `if grep -rn "before_sleep_log" "$REAL_ADAPTERS" --include="*.py" 2>/dev/null; then ...`
  - Side B: `for f in $(grep -rl "@retry(" "$REAL_ADAPTERS" --include="*.py"); do if ! grep -q "from \._logging import\|from docintel_core\.adapters\.real\._logging import" "$f" || ! grep -q "before_sleep_safe" "$f"; then ...`

### Modified

- `packages/docintel-core/src/docintel_core/adapters/real/embedder_bge.py` (1 site swap, 1 import block update, 1 SP-3 comment rewrite)
- `packages/docintel-core/src/docintel_core/adapters/real/llm_anthropic.py` (1 site, 1 import block, 1 comment)
- `packages/docintel-core/src/docintel_core/adapters/real/llm_openai.py` (1 site, 1 import block, 1 comment)
- `packages/docintel-core/src/docintel_core/adapters/real/reranker_bge.py` (1 site, 1 import block, 1 comment)
- `packages/docintel-core/src/docintel_core/adapters/real/qdrant_dense.py` (6 sites swapped via Edit replace_all, 1 import block, 1 module docstring rewrite, 1 SP-3 inline comment rewrite)
- `packages/docintel-core/src/docintel_core/adapters/real/judge.py` (2 sites swapped via Edit replace_all, 1 import block, 1 SP-3 multi-line comment rewrite — module-level @retry, not class-method)
- `packages/docintel-core/src/docintel_core/adapters/real/_logging.py` (docstring line 4 only: `@retry(... )` → `@retry` to keep Side B clean; no API change)
- `.github/workflows/ci.yml` (8-line step inserted between `Check no print (OBS-03)` and `Chunk-idempotency gate (ING-04)`)
- `tests/fixtures/before_sleep_violations_with_safe/safe_example.py` (docstring rewording in 1 phrase: `...before_sleep_log and...` → `...canonical-symbol usage and...` to keep Side A clean when the positive fixture is the explicit SCAN_DIR)
- `tests/test_check_before_sleep_safe.py` (3 `@pytest.mark.xfail(strict=True, ...)` decorators removed)

## Verification

### Per-file before_sleep_safe site counts (must sum to 12)

```
$ grep -rcE 'before_sleep=before_sleep_safe' packages/docintel-core/src/docintel_core/adapters/real/ --include='*.py' | grep -v ':0$'
packages/docintel-core/src/docintel_core/adapters/real/embedder_bge.py:1
packages/docintel-core/src/docintel_core/adapters/real/llm_anthropic.py:1
packages/docintel-core/src/docintel_core/adapters/real/llm_openai.py:1
packages/docintel-core/src/docintel_core/adapters/real/qdrant_dense.py:6
packages/docintel-core/src/docintel_core/adapters/real/reranker_bge.py:1
packages/docintel-core/src/docintel_core/adapters/real/judge.py:2

$ grep -rE 'before_sleep=before_sleep_safe' packages/docintel-core/src/docintel_core/adapters/real/ --include='*.py' | wc -l
12
```

Sum = 1 + 1 + 1 + 6 + 1 + 2 = **12** (matches Pitfall 1 verified count exactly).

### Side A invariant (no raw before_sleep_log in adapters/real/)

```
$ grep -rn 'before_sleep_log' packages/docintel-core/src/docintel_core/adapters/real/ --include='*.py' | wc -l
0
```

### Canonical gate scan (Side A + Side B green)

```
$ bash scripts/check_before_sleep_safe.sh
OK: adapters/real/ uses before_sleep_safe and never raw before_sleep_log
exit=0
```

### Negative fixture (planted raw before_sleep_log MUST be caught)

```
$ bash scripts/check_before_sleep_safe.sh tests/fixtures/before_sleep_violations
tests/fixtures/before_sleep_violations/_unsafe_example.py:1:"""Negative fixture for tests/test_check_before_sleep_safe.py::test_gate_fails_on_planted_raw_before_sleep_log.
tests/fixtures/before_sleep_violations/_unsafe_example.py:3:This file intentionally contains a single **raw** ``before_sleep=before_sleep_log(``
...
tests/fixtures/before_sleep_violations/_unsafe_example.py:41:from tenacity import before_sleep_log, retry
tests/fixtures/before_sleep_violations/_unsafe_example.py:44:@retry(before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING))
FAIL: raw before_sleep_log found in tests/fixtures/before_sleep_violations (P-EMP-04: API key leak surface)
      use docintel_core.adapters.real._logging.before_sleep_safe instead
FAIL: tests/fixtures/before_sleep_violations/_unsafe_example.py contains @retry( but does not import before_sleep_safe
exit=1
```

### Positive fixture (planted before_sleep_safe + import → exit 0)

```
$ bash scripts/check_before_sleep_safe.sh tests/fixtures/before_sleep_violations_with_safe
OK: adapters/real/ uses before_sleep_safe and never raw before_sleep_log
exit=0
```

### CI step insertion position (gate 5 < new gate < chunk-idempotency)

```
$ awk '/Check no print/{p=NR} /Check before_sleep_safe/{s=NR} /Chunk-idempotency/{c=NR} END{print p, s, c; exit (p < s && s < c ? 0 : 1)}' .github/workflows/ci.yml
163 169 178
exit=0
```

New step header lands at line 169, between line 163 (`Check no print (OBS-03)`) and line 178 (`Chunk-idempotency gate (ING-04)`).

### Gate-trio test (3 passed, 0 xfail, 0 xpass)

```
$ pytest tests/test_check_before_sleep_safe.py -ra -v
tests/test_check_before_sleep_safe.py::test_gate_fails_on_planted_raw_before_sleep_log PASSED [ 33%]
tests/test_check_before_sleep_safe.py::test_gate_passes_on_canonical_adapters_real PASSED [ 66%]
tests/test_check_before_sleep_safe.py::test_gate_passes_on_positive_fixture PASSED [100%]
3 passed in 0.05s
```

### mypy --strict on adapters/real/

```
$ mypy --strict packages/docintel-core/src/docintel_core/adapters/real/
Success: no issues found in 10 source files
```

### Targeted adapter tests (sweep doesn't break callers)

```
$ pytest tests/test_adapters.py -ra -q -m "not real"
13 passed, 1 skipped in 2.92s
```

(The 1 skipped is `tests/test_adapters.py:298: real key not set — skipped in stub-mode CI`, unchanged from baseline.)

### Redaction-helper test (sweep preserves the helper contract)

```
$ pytest tests/test_before_sleep_redacts_api_keys.py -ra -q
4 passed in 0.03s
```

## Decisions Made

- **Relative import form chosen** (`from ._logging import before_sleep_safe`) for all 6 swept files. Both relative and absolute (`from docintel_core.adapters.real._logging import ...`) are accepted by the D-06 gate, but relative is one line shorter and matches the single-directory adapter package convention.
- **Pitfall 1 verified count drove the swap arithmetic** — not CONTEXT.md D-04. The "6 across 5" CONTEXT.md undercount would have missed both `qdrant_dense.py` sites at lines 416/431/448 (3 extra) and the entire `judge.py` file (2 more sites). Acceptance test `grep -c 'before_sleep=before_sleep_safe' adapters/real/` returning 12 (vs. 6 if CONTEXT.md had been believed) is the empirical confirmation.
- **Docstring substring discipline extended to the helper + positive fixture** (Plan 14-03 precedent) — the gate is text-based and grep doesn't distinguish code-context from docstring-prose, so any literal mention of `before_sleep_log` or `@retry(` substring in a file that would otherwise be caught by Side A or Side B trips the gate. Two minimal prose-only rewrites resolved this without changing any API surface.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] `_logging.py` docstring tripped Side B on the canonical scan**

- **Found during:** Task 2 first dry-run of `bash scripts/check_before_sleep_safe.sh`
- **Issue:** The helper module's docstring (line 4) contained the substring `@retry(... )`. Side B (`grep -rl '@retry('`) matched the helper itself; the helper does NOT import `before_sleep_safe` (it IS the export), so the gate failed: `FAIL: packages/docintel-core/src/docintel_core/adapters/real/_logging.py contains @retry( but does not import before_sleep_safe`.
- **Fix:** Rewrote the docstring's `@retry(... )` mention to `@retry` (no paren). The helper now has zero `@retry(` substring, so Side B doesn't flag it. No API change.
- **Files modified:** `packages/docintel-core/src/docintel_core/adapters/real/_logging.py` (docstring line 4 only)
- **Commit:** `211226d`

**2. [Rule 3 - Blocking issue] Positive fixture docstring tripped Side A**

- **Found during:** Task 2 dry-run of `bash scripts/check_before_sleep_safe.sh tests/fixtures/before_sleep_violations_with_safe`
- **Issue:** The positive fixture's docstring (line 13) contained the literal substring `...before_sleep_log and...` in prose explaining the D-06 two-sided assertion. Side A scanned `.py` files in the SCAN_DIR and matched this docstring line, returning a false-positive FAIL.
- **Fix:** Rewrote the docstring phrase to `...canonical-symbol usage and...`. The fixture's structural shape (`@retry(... before_sleep=before_sleep_safe(...))` + `from docintel_core.adapters.real._logging import before_sleep_safe`) is unchanged.
- **Files modified:** `tests/fixtures/before_sleep_violations_with_safe/safe_example.py` (docstring rewording only)
- **Commit:** `211226d`

Both auto-fixes are docstring-only edits that keep the gate's text-based grep simple (vs. introducing per-line escape comments or path filters). The pattern matches Plan 14-03's "Docstring substring discipline" SUMMARY note verbatim.

## Issues Encountered

- **Environmental: `tests/test_judge_structured_output.py::test_deserialization_failure_returns_sentinel` fails in this worktree** — pre-existing in Plan 14-03 (logged in deferred-items per the worktree-only file the 14-03 SUMMARY references). Root cause is HTTPX trying to use SOCKS proxy (`socks5h://localhost:49183` set in env) but `socksio` is not installed in the venv. The failing test has **zero** `before_sleep` references and zero causal link to this plan's diff. Per the executor SCOPE BOUNDARY rule, this is NOT fixed by Plan 14-04. The targeted adapter tests (`test_adapters.py`) and the redaction-helper test (`test_before_sleep_redacts_api_keys.py`) both pass cleanly, confirming the sweep didn't break the adapter contract.

- **The trio test passes via subprocess** — `subprocess.run(["bash", str(_GATE_SCRIPT), str(_NEG_FIXTURE_DIR)], check=False, capture_output=True, text=True)`. The test inspects `result.returncode` only (not stderr), so the gate's print statements are advisory; the contract is exit-code identity. This matches the established `tests/test_no_print_gate.py` convention the trio was patterned on.

## User Setup Required

None — no external service configuration required. This plan ships pure Python + shell + CI YAML edits. No environment variables, no API keys, no infrastructure changes. The 6th CI gate will run automatically on the next PR / push.

## Threat Flags

None — this plan closes T-EMP-04 (information disclosure via retry-path log → committed CI eval-report manifest). The D-06 gate's Side B also pre-emptively closes T-14-11 (a future adapter landing with `@retry(` and no `before_sleep` param at all, violating CLAUDE.md "no silent retries on LLM calls"). No new threat surface introduced.

## Next Phase Readiness

- **EMP-05 fully closed.** With Plan 14-04 landed, the full chain is end-to-end: `_logging.py` helper (14-03) → sweep (14-04 Task 1) → gate script (14-04 Task 2) → CI workflow step (14-04 Task 2) → green Wave-0 trio (14-04 Task 3). Any future PR that reintroduces a raw `before_sleep_log` in `adapters/real/` or lands an `@retry(`-using file without the safe import is caught at PR-time by the 6th `lint-and-test` gate.
- **REQUIREMENTS.md EMP-05 marker → DONE.** The orchestrator will update the requirements traceability table when it consolidates the Wave 2 SUMMARYs.
- **No follow-on for this plan.** Plan 14-05 (EMP-04 freeze) and beyond proceed independently per the Phase 14 ROADMAP.

---
*Phase: 14-empirical-closure*
*Plan: 04*
*Completed: 2026-05-31*

## Self-Check: PASSED

Verified before declaring complete:

- `[ -x scripts/check_before_sleep_safe.sh ]` → FOUND (mode 0755, 49 lines)
- `[ -f .github/workflows/ci.yml ]` → FOUND (1 new step `Check before_sleep_safe (EMP-05 / P-EMP-04)` at line 169)
- `git log --oneline | grep -q d08e5a4` → FOUND (Task 1: refactor(14-04) sweep commit)
- `git log --oneline | grep -q 211226d` → FOUND (Task 2: feat(14-04) gate + CI commit)
- `git log --oneline | grep -q 6578211` → FOUND (Task 3: test(14-04) xfail flip commit)
- `grep -rn 'before_sleep_log' packages/docintel-core/src/docintel_core/adapters/real/ --include='*.py' | wc -l` → 0 ✓
- `grep -rE 'before_sleep=before_sleep_safe' packages/docintel-core/src/docintel_core/adapters/real/ --include='*.py' | wc -l` → 12 ✓
- Per-file site counts via `grep -rcE 'before_sleep=before_sleep_safe' adapters/real/`: embedder_bge=1, llm_anthropic=1, llm_openai=1, reranker_bge=1, qdrant_dense=6, judge=2 → sums to 12 ✓
- `bash scripts/check_before_sleep_safe.sh` → exit 0 ✓ (canonical adapters/real/ scan)
- `bash scripts/check_before_sleep_safe.sh tests/fixtures/before_sleep_violations` → exit 1 ✓ (negative caught)
- `bash scripts/check_before_sleep_safe.sh tests/fixtures/before_sleep_violations_with_safe` → exit 0 ✓ (positive accepted)
- `awk '...' .github/workflows/ci.yml` position check → exit 0 ✓ (163 < 169 < 178)
- `grep -c 'xfail until 14-04' tests/test_check_before_sleep_safe.py` → 0 ✓
- `pytest tests/test_check_before_sleep_safe.py -ra -q` → 3 passed, 0 xfail, 0 xpass ✓
- `mypy --strict packages/docintel-core/src/docintel_core/adapters/real/` → Success: no issues found in 10 source files ✓
- `pytest tests/test_adapters.py -ra -q -m "not real"` → 13 passed, 1 skipped (real key — unchanged from baseline) ✓
- `pytest tests/test_before_sleep_redacts_api_keys.py -ra -q` → 4 passed ✓ (redaction-helper contract preserved)
