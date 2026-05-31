---
phase: 14-empirical-closure
plan: 5
subsystem: empirical-closure / baseline-lock / readme-paste
tags: [phase-14, wave-2, emp-01, emp-02, baseline-lock, readme-paste, real-run-checklist, makefile, scripts]
requires:
  - 14-01-SUMMARY.md  # Wave-0 EMPIRICAL-PENDING xfail-strict test scaffolds (test_baseline_schema, test_baseline_cost_matches, test_readme_no_stub_banner, test_hero_gif_present)
  - 14-02-SUMMARY.md  # D-01 eval_set.jsonl rename + EVAL_SET_SHA256 freeze (baseline-lock target relies on the frozen sha256 vs report dataset_hash check)
provides:
  - data/eval/baseline.json  # NOT created by this plan — schema-writer infrastructure only; user owns the trigger per D-08
  - Makefile baseline-lock target  # D-07 schema writer + D-08 validation sweep (3 gates)
  - Makefile readme-paste target  # D-10 README PASTE-REAL-NUMBERS swap entry point
  - scripts/readme_paste.py  # D-10 helper (atomic re.DOTALL anchor-block replacement)
  - docs/REAL-RUN-CHECKLIST.md Phase 14 section  # User-owned EMP-01/02/03 sequence + Pitfall 7 macOS prereqs
affects:
  - none  # Infra-only plan; no production code in packages/* changed
tech-stack:
  added: []  # No new pip installs; stdlib argparse/re/json/pathlib/os only
  patterns:
    - "Makefile multiline body with `; \\` continuations so shell vars persist across the validation chain (mirrors `ablate-chunk-sweep` at Makefile:119-143)"
    - "Python re.sub with flags=re.DOTALL count=1 for multi-line HTML-comment anchor-block replacement (Pitfall 4 — sed-fragility avoidance)"
    - "Atomic file write via tempfile + os.replace (POSIX-atomic on same filesystem)"
    - "macOS-safe sha256 selector via `command -v sha256sum >/dev/null && ... || ...` runtime detection (Pitfall 7)"
    - "Defense-in-depth file-existence gates with actionable FAIL: messages naming the precondition command"
key-files:
  created:
    - scripts/readme_paste.py  # 274 lines; mypy --strict clean; executable
  modified:
    - Makefile  # +67 lines: baseline-lock + readme-paste targets, .PHONY + help: text body updated
    - docs/REAL-RUN-CHECKLIST.md  # +192 lines: Phase 14 EMP-01/02/03 user-owned sequence with prereqs + verification commands
decisions:
  - "Mirrored the ablate-chunk-sweep multiline `; \\` heredoc body style (Makefile:119-143) rather than splitting baseline-lock into multiple @-lines — the multi-line shell-var chain (REPORT_DIR / RESULTS / REP / EVAL_SHA / REPORT_EVAL_SHA / GIT_SHA / PROMPT_HASH / COST / NOW) needs to persist across the validation gates"
  - "Used a runtime `command -v sha256sum` detection (Pitfall 7) rather than documenting `brew install coreutils` as a macOS prereq — the macOS shasum builtin already supports `-a 256` so no install is needed for the sha256 step; only `jq` requires brew install"
  - "Helper output keeps the exact headline-metrics table shape from README.md:51-61 (only values change) so the diff after `make readme-paste` is minimal and reviewable"
  - "Helper writes via tempfile + os.replace rather than direct write to preserve README.md if the helper crashes mid-write"
  - "Helper does NOT touch packages/docintel-ui/ — Pitfall 5 confirms eval_view.py:128-137 auto-detects the new representative: true report on next render; modifying the UI would create two truths"
  - "Used `phase_locked: 14` as a literal int (no quotes in the printf JSON) so Wave-0 test_baseline_schema.py's isinstance(int) check passes"
  - "Did NOT create data/eval/baseline.json or trigger gh workflow run real-eval — D-08 explicitly rejects auto-locking; the user owns the trigger and the eyeball-the-report step"
metrics:
  duration: "6m"
  completed: "2026-05-31"
---

# Phase 14 Plan 5: baseline-lock / readme-paste / REAL-RUN-CHECKLIST EMP sequencing — Summary

**One-liner:** Shipped the user-owned EMP-01/EMP-02 plan-side infrastructure — `make baseline-lock TS=<ts>` writes the 7-field D-07 baseline.json schema after firing 3 D-08 validation gates, `make readme-paste` + `scripts/readme_paste.py` rewrites the README's PASTE-REAL-NUMBERS anchor block atomically via re.DOTALL, and `docs/REAL-RUN-CHECKLIST.md` documents the 4-step user-owned sequence with macOS prerequisites and Wave-0 test cross-references.

## What Landed

### Task 1 — `make baseline-lock TS=<ts>` Makefile target (commit `50ada3f`)

- New Makefile target at lines 145-191 (after `ablate-chunk-sweep`, before `eval` placeholder).
- `.PHONY:` updated to include `baseline-lock readme-paste` (line 18-20).
- `help:` body adds two new rows in the Working block:

  ```
  baseline-lock  Phase 14 EMP-01 / D-08: lock v1.0 baseline from a representative real-eval report (usage: make baseline-lock TS=<timestamp>)
  readme-paste   Phase 14 EMP-02 / D-10: paste real numbers from baseline.json into README.md PASTE-REAL-NUMBERS block
  ```

- Body fires the 3 D-08 validation gates in order:
  1. **Gate 1 (TS-required):** `make baseline-lock` (no args) → `FAIL: missing TS=<timestamp> argument` + exit 2.
  2. **Gate 2 (file-exists):** `TS=does-not-exist` → `FAIL: data/eval/reports/does-not-exist/results.json not found` + exit 1.
  3. **Gate 3 (representative=true):** `TS=stub-sample` → `FAIL: ... manifest.representative=false (D-08: must be true — auto-locking on flaky runs is rejected)` + exit 1.
  4. **Gate 4 (eval-set sha cross-check):** if `EVAL_SHA != REPORT_EVAL_SHA` → `FAIL: eval_set.jsonl sha256 does not match report dataset_hash`.
- On success: writes the D-07 7-field JSON (with `phase_locked: 14` as a literal int and `cost_usd` as a raw jq float) to `data/eval/baseline.json` then commits with `chore(baseline): lock v1.0 baseline @ <ts>`.
- Pitfall 7 macOS toolchain: `if command -v sha256sum >/dev/null 2>&1; then ... else shasum -a 256 ...; fi` — runtime detection, no env var.

### Task 2 — `scripts/readme_paste.py` D-10 helper + `make readme-paste` target (commit `f6e5250`)

- New script `scripts/readme_paste.py` (274 lines, executable, `mypy --strict` clean).
- Argparse signature:

  ```
  usage: readme_paste.py [-h] [--baseline BASELINE] [--repo-root REPO_ROOT] [--dry-run]

  Phase 14 EMP-02 / D-10: paste real numbers from baseline.json into the
  README.md PASTE-REAL-NUMBERS anchor block.

  options:
    -h, --help            show this help message and exit
    --baseline BASELINE   Path to baseline.json (default: data/eval/baseline.json)
    --repo-root REPO_ROOT Repository root (default: cwd)
    --dry-run             Print the proposed replacement block to stdout without writing
  ```

- Reads the 7 D-07 baseline fields + the linked report's `manifest` / `retrieval` / `faithfulness` / `latency` sections.
- Builds the replacement block — keeps the exact table shape from README.md:51-61 (Hit@5/Hit@3/MRR/Faithfulness/p50/p95/$/query); only values change. Adds a `representative: true` honest-disclosure note with `locked_at` + short `git_sha` provenance.
- Replacement is atomic: `re.sub(_ANCHOR_PATTERN, new_block, content, count=1)` where `_ANCHOR_PATTERN` is `re.compile(r"<!-- PASTE-REAL-NUMBERS:.*?<!-- END-PASTE-REAL-NUMBERS -->", flags=re.DOTALL)`. Write goes via tempfile + `os.replace` (POSIX-atomic on same filesystem).
- Every missing-field path emits `FAIL: <key>` and returns 1 — never crashes silently.
- Smoke-tested via `--dry-run` against a fake baseline.json pointing at `data/eval/reports/stub-sample/`; output matches the expected block shape.
- Makefile target `readme-paste` (lines 193-211) fires a `data/eval/baseline.json` precondition gate (`FAIL: ... not found — run 'make baseline-lock TS=<ts>' first per D-08`) then invokes the helper via `uv run python scripts/readme_paste.py`.

### Task 3 — `docs/REAL-RUN-CHECKLIST.md` Phase 14 section (commit `78ab275`)

- Appended a new `## Phase 14 — empirical-closure (EMP-01 / EMP-02 / EMP-03)` section (192 lines).
- Section structure:
  - **Prerequisites (macOS only — Pitfall 7):** `brew install jq` + `sha256sum`/`shasum -a 256` sanity check.
  - **Step 1 (EMP-01):** trigger `gh workflow run real-eval -f representative=true`, wait for green CI, eyeball `report.md` (manifest header, Hit@3 canary differential, cost_usd sanity bounds).
  - **Step 2 (EMP-01):** run `make baseline-lock TS=<ts>`; verify with `pytest tests/test_baseline_schema.py tests/test_baseline_cost_matches.py`.
  - **Step 3 (EMP-02):** run `make readme-paste`, visually inspect, commit; verify UI auto-flip (Pitfall 5) and run `pytest tests/test_readme_no_stub_banner.py`.
  - **Step 4 (EMP-03):** record `docs/hero.gif` per HERO-STORYBOARD.md, commit; verify with `pytest tests/test_hero_gif_present.py`.
  - **Verification — all four EMP closures land green:** single `pytest` command on all 4 Wave-0 tests.
- 14 checkbox items (`- [ ]` format consistent with the existing checklist).
- Cross-references all 4 Wave-0 tests by exact path so the user can audit completion by name.

## Deviations from Plan

None — plan executed exactly as written. The verification step in PLAN.md Task 1 mentioned an awk pattern `awk '/^baseline-lock:/,/^[a-z][a-z_-]*:/' Makefile | grep -c '\\$' >= 5` which returns 0 because the awk range matches `baseline-lock:` itself and stops immediately. The actual structural assertion the criterion was probing — "the body uses line continuations" — is satisfied (32 ` \` line continuations inside the target body via `awk '/^baseline-lock:/ {found=1} found {print}' Makefile | grep -c ' \\$'`).

One micro-fix during testing: my `FAIL: results.json not found ...` error message in the Makefile originally embedded backtick-quoted commands (`` `gh workflow run real-eval` ``) that the test shell evaluated as command substitution. Switched to single-quoted forms (`'gh workflow run real-eval'`). This was a Rule 1 inline fix; no test or behavior change needed.

## Authentication Gates

None — this plan is entirely offline-first infrastructure. No `gh workflow run`, no API key check, no live network access. The user-owned `gh workflow run real-eval` step is documented in `docs/REAL-RUN-CHECKLIST.md` per D-08 + Plan 14-05's `<success_criteria>` explicit prohibition.

## Verification Results

| Verification | Result |
|---|---|
| `make help \| grep -E 'baseline-lock\|readme-paste'` | OK — both targets listed |
| `make baseline-lock` (no TS) | OK — exits non-zero with `FAIL: missing TS=...` |
| `make baseline-lock TS=does-not-exist` | OK — exits non-zero with `FAIL: ... not found` |
| `make baseline-lock TS=stub-sample` | OK — exits non-zero with `FAIL: ... manifest.representative=false` |
| `test -x scripts/readme_paste.py` | OK — executable bit set |
| `uv run python scripts/readme_paste.py --help` | OK — `--baseline` + `--dry-run` flags present |
| `uv run mypy --strict scripts/readme_paste.py` | OK — Success: no issues found in 1 source file |
| `make readme-paste` (no baseline.json) | OK — exits non-zero with `FAIL: data/eval/baseline.json not found` |
| `--dry-run` smoke with stub-sample fixture | OK — produces the expected anchor block |
| `docs/REAL-RUN-CHECKLIST.md` Phase 14 section | OK — header present, 14 checkbox items, all 4 user steps + verification block |
| `pytest tests/test_eval_set_frozen.py` regression | OK — 1 passed in 0.01s (no impact from this plan) |
| `data/eval/baseline.json` does NOT exist | OK — user owns the trigger per D-08 |

## Known Stubs

None. This plan ships infrastructure (Makefile targets + a Python helper + checklist documentation); the actual `data/eval/baseline.json` artifact is deliberately not created here — per CONTEXT.md D-08 and PLAN.md's `<success_criteria>` line "**DO NOT** invoke `gh workflow run real-eval` or `make baseline-lock TS=<ts>` against the live workflow", the user owns the trigger. Plan 14-06 picks up after the user runs them.

## Self-Check

Files exist:
- `Makefile` → FOUND (modified, +67 lines)
- `scripts/readme_paste.py` → FOUND (created, 274 lines, executable)
- `docs/REAL-RUN-CHECKLIST.md` → FOUND (modified, +192 lines)

Commits exist (verified via `git log --oneline -4`):
- `50ada3f` feat(14-05): add make baseline-lock target with D-08 validation gates — FOUND
- `f6e5250` feat(14-05): add readme_paste.py D-10 helper + make readme-paste target — FOUND
- `78ab275` docs(14-05): append Phase 14 EMP-01/02/03 sequencing to REAL-RUN-CHECKLIST — FOUND

## Self-Check: PASSED
