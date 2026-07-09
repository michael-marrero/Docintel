---
phase: 14-empirical-closure
plan: 03
subsystem: adapters/observability
tags: [phase-14, wave-1, emp-05, sanitizer, before-sleep-safe, p-emp-04, tenacity, redaction-regex]
dependency_graph:
  requires:
    - phase: 14-01
      provides: "Wave-0 xfail-strict scaffold at tests/test_before_sleep_redacts_api_keys.py (4 parametrized D-05 redaction cases) that Plan 14-03 flips green"
  provides:
    - "packages/docintel-core/src/docintel_core/adapters/real/_logging.py — before_sleep_safe(logger, log_level) factory + _REDACT_PATTERN + _redact helper"
    - "Tenacity-compatible Callable[[RetryCallState], None] that mirrors the vendored before-sleep semantics verbatim (None-guards on outcome + next_action per RESEARCH Pitfall 3) but redacts str(exception) and str(result) via D-05 patterns before logger.log"
    - "4 green parametrized test cases proving sk-/sk-ant-/pa-/Bearer scrub to typed [REDACTED:<type>] markers via a real tenacity @retry drive"
  affects:
    - "14-04 will sweep the 12 raw use-sites across 6 adapter files (per RESEARCH Pitfall 1) to before_sleep_safe and land the scripts/check_before_sleep_safe.sh CI gate (D-06)"
    - "Phase 17 paired-bootstrap baseline reads — once the gate lands, no API key can leak through retry-path logs into committed eval-report manifests"
tech-stack:
  added: []  # No new pip deps — stdlib re + logging + typing + already-installed tenacity (pinned 9.1.4)
  patterns:
    - "Sanitizing-wrapper-around-vendored-factory: mirror upstream semantics verbatim (None-guards + closure shape + log format) and apply the sanitizing transform at exactly two points — str(exception) and str(result) — before the upstream logger.log call"
    - "Leading-underscore module convention: _logging.py is internal to adapters/real/ (NOT a public docintel-core export). __init__.py does NOT re-export it"
    - "Two-logger SP-3 scope: this module wraps only the stdlib path that tenacity uses; the structured-event logger every other real adapter binds is intentionally NOT imported (single responsibility)"
    - "Docstring substring discipline: prose that would otherwise reference forbidden tokens (the canonical-symbol literal + the structured-event library name) is reworded around them so the Plan 14-04 grep gate stays clean"
key-files:
  created:
    - packages/docintel-core/src/docintel_core/adapters/real/_logging.py
  modified:
    - tests/test_before_sleep_redacts_api_keys.py
decisions:
  - "_REDACT_PATTERN ordering: sk-ant- precedes sk- in the alternation so Anthropic keys are matched by the longer prefix and emit [REDACTED:sk-ant-] not [REDACTED:sk-]"
  - "20-char minimum after each prefix: keeps 40-char git SHAs and short request IDs from being scrubbed (verified by acceptance criteria — a 40-char SHA passes through unchanged)"
  - "Success-branch redaction (str(outcome.result())) is belt-and-suspenders: tenacity's before-sleep does not fire on success today, but redacting anyway costs one regex pass and forecloses a future contract change"
  - "RetryCallState is imported under typing.TYPE_CHECKING only — though tenacity 9.1.4 DOES export it at top-level (verified during execution), keeping the typing-only import per the plan's CRITICAL note future-proofs against package layout changes"
  - "Docstring prose deliberately avoids the literal substrings for the forbidden canonical symbol and the structured-event library name — the Plan 14-04 D-06 grep gate is text-based, and a prose mention would falsely flag this module as a violation"
metrics:
  duration: "~7 min"
  completed: "2026-05-31"
  tasks: 2
  files_created: 1
  files_modified: 1
  commits:
    - "ac58dbf: feat(14-03): land before_sleep_safe sanitizer at adapters/real/_logging.py"
    - "d98e92d: test(14-03): flip Wave-0 redaction test green by removing xfail marker"
requirements-completed: [EMP-05]
---

# Phase 14 Plan 03: before_sleep_safe sanitizer Summary

**`before_sleep_safe(logger, log_level)` factory + 4-pattern redaction regex landed at `adapters/real/_logging.py`; Wave-0 xfail-strict redaction test flipped green (4/4 cases passing).**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-05-31T21:49:37Z
- **Completed:** 2026-05-31T21:56:31Z
- **Tasks:** 2
- **Files created:** 1 (`_logging.py`, 197 lines)
- **Files modified:** 1 (`tests/test_before_sleep_redacts_api_keys.py`)

## Accomplishments

- Landed `packages/docintel-core/src/docintel_core/adapters/real/_logging.py` — a tenacity-compatible sanitizing before-sleep factory that mirrors the vendored canonical factory's semantics verbatim (RuntimeError on `outcome is None` and `next_action is None`, identical retry-line format) while applying the D-05 redaction regex to `str(exception)` and `str(result)` before `logger.log(...)`.
- `_REDACT_PATTERN` covers the 4 D-05 key shapes — OpenAI `sk-`, Anthropic `sk-ant-` (matched FIRST in the alternation per the order rule), Voyage `pa-`, and any HTTP `Bearer ` header — and replaces each match with a typed `[REDACTED:<type>]` marker that preserves the "an auth credential was here" signal without leaking content.
- `_redact()` helper is importable for tests (underscore-prefixed; not in `__all__`); per-type discrimination is by prefix on the matched substring.
- Flipped the Wave-0 redaction test green: removed the file-level `@pytest.mark.xfail(strict=True, reason="xfail until 14-03: ...")` decorator and updated the docstring lifecycle note. 4 parametrized cases (`sk-ant-`, `sk-`, `pa-`, `Bearer`) drive a real tenacity `@retry` decorator (Pitfall 3 recipe — no hand-mocked `RetryCallState`) and assert via `caplog` that the planted key is absent AND the typed marker is present.
- Closes the helper side of EMP-05's P-EMP-04 mitigation (API-key leakage on retry-path log). Plan 14-04 closes the sweep + CI grep gate (D-06).

## Task Commits

Each task was committed atomically:

1. **Task 1: Create `_logging.py` sanitizer factory + redact helper + `_REDACT_PATTERN`** — `ac58dbf` (feat)
2. **Task 2: Flip Wave-0 redaction test green (remove xfail decorator)** — `d98e92d` (test)

_Note: This is a TDD plan whose RED gate was already laid by Plan 14-01 (Wave-0 xfail-strict scaffold at `tests/test_before_sleep_redacts_api_keys.py`). Plan 14-03 is therefore the GREEN gate — Task 1 ships the implementation that makes the existing scaffold pass; Task 2 removes the xfail marker so XPASS does not become an XPASS-strict failure._

## Files Created/Modified

### Created

- `packages/docintel-core/src/docintel_core/adapters/real/_logging.py` (197 lines)
  - Module-scope: `_REDACT_PATTERN` (compiled `re.Pattern[str]`) + `_redact(text: str) -> str` + `before_sleep_safe(logger: logging.Logger, log_level: int) -> Callable[[RetryCallState], None]`
  - Imports: stdlib `logging` + `re` + `typing`; `from tenacity._utils import get_callback_name`; `RetryCallState` under `if TYPE_CHECKING:` only
  - Does NOT import the structured-event logger library; does NOT reference the canonical tenacity symbol the D-06 grep gate forbids (so the gate stays clean once 14-04 lands the sweep)
  - mypy `--strict` clean

### Modified

- `tests/test_before_sleep_redacts_api_keys.py`
  - Removed file-level `@pytest.mark.xfail(strict=True, reason="xfail until 14-03: ...")` decorator
  - Updated module docstring to reflect post-14-03 green state (literal "xfail until 14-03" substring no longer appears)
  - 4 parametrized cases now pass green: `[sk-ant-]`, `[sk-]`, `[pa-]`, `[Bearer]`
  - Driven by a real `tenacity.retry(stop=stop_after_attempt(2), wait=wait_fixed(0), before_sleep=before_sleep_safe(_logger, logging.WARNING))` decorator on a function that raises `ValueError(planted)` — Pitfall 3 recipe in action

## Sample redaction outputs

D-05 patterns scrub to typed markers:

```
'sk-ant-1234567890abcdefghij1234567890abcdef'             -> '[REDACTED:sk-ant-]'
'sk-1234567890abcdefghij1234567890abcdef'                 -> '[REDACTED:sk-]'
'pa-1234567890abcdefghij1234567890abcdef'                 -> '[REDACTED:pa-]'
'Bearer abcdefghij1234567890abcdefghij1234567890='        -> '[REDACTED:Bearer]'
```

D-05 invariants hold (pass-through unchanged):

```
'0123456789abcdef0123456789abcdef01234567'  (40-char git SHA)  -> '0123456789abcdef0123456789abcdef01234567'
'sk-short'                                  (<20 chars after prefix) -> 'sk-short'
'abc1234567890abcdef1234567890abcdef'       (no recognized prefix)   -> 'abc1234567890abcdef1234567890abcdef'
```

## D-05 ordering confirmation

`_REDACT_PATTERN.pattern`:
```
(sk-ant-[a-zA-Z0-9-_]{20,}|sk-[a-zA-Z0-9-_]{20,}|pa-[a-zA-Z0-9-_]{20,}|Bearer\s+[a-zA-Z0-9.\-_~+/]{20,}=*)
```

`sk-ant-` appears at position 1; `sk-[` appears at position 27 — `sk-ant-` precedes `sk-` per the D-05 ordering rule. An Anthropic key (`sk-ant-XXXXXXXXXXXXXXXXXXXX`) is matched by the longer prefix first and correctly emits `[REDACTED:sk-ant-]`, not `[REDACTED:sk-]`.

## Test Results

```
$ pytest tests/test_before_sleep_redacts_api_keys.py -ra -q
....                                                                     [100%]
4 passed in 0.03s
```

Zero xfail, zero xpass — clean green per acceptance criterion.

## mypy --strict

```
$ mypy --strict packages/docintel-core/src/docintel_core/adapters/real/_logging.py
Success: no issues found in 1 source file
```

## Decisions Made

- **D-05 regex ordering verified by both static (position-in-pattern) and runtime (Anthropic-key-input → correct marker) assertions.** The acceptance criteria block was specific about both — needed because a future edit that mechanically alphabetizes the alternation would silently mis-categorize Anthropic keys.
- **20-char `{20,}` minimum verified against a 40-char git SHA pass-through.** The acceptance criteria call this out specifically because the natural failure mode if the regex were too loose is silent destruction of useful retry-context (commit hashes, request IDs) in log archaeology.
- **Belt-and-suspenders success-branch redaction kept** even though tenacity's before-sleep does not fire on success today. Cost is one regex pass per retry; benefit is a future-proof contract.
- **Docstring substring discipline applied:** prose mentions of the forbidden canonical tenacity symbol and the structured-event logger library were reworded around them. The Plan 14-04 D-06 grep gate is text-based — a prose mention would falsely flag this module as a violation when 14-04 sweeps the adapters/real/ tree.
- **`RetryCallState` kept under `TYPE_CHECKING` only** per the plan's CRITICAL note, even though tenacity 9.1.4 DOES export it at top-level (verified at runtime: `from tenacity import RetryCallState` works). Typing-only import is the more portable shape — survives package layout changes — and matches the vendored upstream factory.

## Deviations from Plan

None — plan executed exactly as written.

The acceptance criteria block called for grep counts of `'structlog' == 0` and `'before_sleep_log' == 0` in `_logging.py`. On the first draft of the docstring, both substrings appeared in explanatory prose (structlog mentioned 4 times in "why we don't import it"; before_sleep_log mentioned 6 times in "the canonical factory we mirror"). I rewrote the prose to describe the same constraints without using the forbidden literal substrings — that's a docstring-quality-of-life adjustment within the plan's explicit acceptance criteria, not a deviation.

## Issues Encountered

- **uv-run-from-worktree-with-`--project`-flag resolves docintel_core to the MAIN checkout's source, not the worktree's.** The main venv's editable install of `docintel_core` points at `/Users/mm/GitHub/Docintel-main/packages/docintel-core/src/...`, so `uv run --project /Users/mm/GitHub/Docintel-main pytest` from the worktree fails the redaction test with `ModuleNotFoundError: docintel_core.adapters.real._logging`. **Resolution:** Use `PYTHONPATH=<worktree>/packages/docintel-core/src` + the venv's `pytest` binary directly. Verified that with the override, the 4 redaction tests pass green. This is an environmental quirk specific to running parallel-executor agents in worktrees, not a code defect.

- **Pre-existing test failures in the worktree** unrelated to this plan: 12 tests in `tests/test_bm25_store.py`, `tests/test_chunk_idempotency.py`, `tests/test_index_*.py`, `tests/test_ingest_cli.py`, and `tests/test_generator_search_integration.py` fail in the worktree environment because they depend on data/cwd setup unique to the main checkout. **Resolution:** Logged in `.planning/phases/14-empirical-closure/deferred-items.md` (worktree-only file; not committed). Verified zero causal link to Plan 14-03's diff — Task 1's only change is `+197` lines in a new file under `adapters/real/`, and none of the failing tests reference it. Per the executor SCOPE BOUNDARY rule, these are NOT fixed by Plan 14-03.

## User Setup Required

None — no external service configuration required. This plan ships pure Python + tests; no environment variables, no API keys, no infrastructure changes.

## Threat Flags

None — this plan closes T-EMP-04 (the API-key leakage threat). The new file (`_logging.py`) is a leaf helper module with no network surface, no auth path, no file I/O beyond a `logger.log` call. No new threat surface introduced.

## Next Phase Readiness

- **Plan 14-04 unblocked.** With `before_sleep_safe` landed and importable from `docintel_core.adapters.real._logging`, Plan 14-04 can now:
  1. Sweep the 12 raw use-sites across 6 adapter files (per RESEARCH Pitfall 1: qdrant_dense.py × 6, judge.py × 2, embedder_bge.py × 1, llm_anthropic.py × 1, llm_openai.py × 1, reranker_bge.py × 1) by swapping `before_sleep=before_sleep_log(_retry_log, logging.WARNING)` → `before_sleep=before_sleep_safe(_retry_log, logging.WARNING)` and updating the import block at the top of each file.
  2. Land `scripts/check_before_sleep_safe.sh` (the two-sided D-06 gate: no raw canonical-symbol calls in `adapters/real/` AND every `@retry`-using file imports `before_sleep_safe`).
  3. Wire the gate into `.github/workflows/ci.yml` alongside the existing 5 grep gates.
  4. Remove the xfail markers on the 3 cases in `tests/test_check_before_sleep_safe.py`.

- **The Wave-0 → Wave-1 chain link for EMP-05 is closed on the helper side.** EMP-05's full closure requires Plan 14-04's sweep + gate to land; once both are in, no API key can structurally leak through a tenacity retry-path log into the committed CI eval-report manifest.

---
*Phase: 14-empirical-closure*
*Plan: 03*
*Completed: 2026-05-31*

## Self-Check: PASSED

Verified before declaring complete:

- `[ -f packages/docintel-core/src/docintel_core/adapters/real/_logging.py ]` → FOUND (197 lines)
- `[ -f tests/test_before_sleep_redacts_api_keys.py ]` → FOUND (xfail marker absent, 4 cases passing green via real-tenacity drive)
- `git log --oneline | grep -q ac58dbf` → FOUND (Task 1: feat(14-03) commit)
- `git log --oneline | grep -q d98e92d` → FOUND (Task 2: test(14-03) commit)
- `python -c "from docintel_core.adapters.real._logging import before_sleep_safe, _REDACT_PATTERN, _redact; print('OK')"` → exit 0
- `pytest tests/test_before_sleep_redacts_api_keys.py -ra -q` → 4 passed, 0 xfail, 0 xpass
- `mypy --strict packages/docintel-core/src/docintel_core/adapters/real/_logging.py` → Success: no issues
- `grep -c structlog _logging.py` → 0 ✓
- `grep -c before_sleep_log _logging.py` → 0 ✓
- `grep -c 'outcome is None' _logging.py` → 2 ✓ (Pitfall 3 guards)
- `grep -c 'next_action is None' _logging.py` → 2 ✓ (Pitfall 3 guards)
- `grep -c 'xfail until 14-03' tests/test_before_sleep_redacts_api_keys.py` → 0 ✓
