---
phase: 01-scaffold-foundation
plan: 02
subsystem: scaffold/secrets-hygiene
tags: [gitignore, env-template, pre-commit, gitleaks, secrets, tooling-config]
requires:
  - none (Wave 1, parallel with Plan 01)
provides:
  - .gitignore protects .env, data/, build artifacts, OS junk, tool caches
  - .env.example template with DOCINTEL_LLM_PROVIDER=stub default
  - .pre-commit-config.yaml hooks (ruff, black, gitleaks) on pre-commit + pre-push
  - .gitleaks.toml shared config for pre-commit AND CI
  - tests/fixtures/leaked_key.example template (Plan 09 fixture source)
affects:
  - all future commits (gitleaks gate)
  - Plan 09 (gitleaks-rejects-fake-key test depends on this allowlist + fixture)
  - Plan 10 (CI workflow reuses .gitleaks.toml)
tech-stack:
  added:
    - pre-commit-hooks v5.0.0
    - ruff-pre-commit v0.15.12
    - black 24.10.0 (python3.11)
    - gitleaks v8.21.2
  patterns:
    - allowlist-by-path for legitimate placeholder files
    - fixture-by-template (.example tracked, .txt gitignored)
key-files:
  created:
    - .env.example
    - .pre-commit-config.yaml
    - .gitleaks.toml
    - tests/fixtures/leaked_key.example
  modified:
    - .gitignore
decisions:
  - D-19 implemented: pre-commit runs ruff (lint+format), black, gitleaks on pre-commit AND pre-push
  - D-20 implemented: .env.example has DOCINTEL_LLM_PROVIDER=stub, empty key placeholders
  - D-21 implemented: .gitleaks.toml committed, fixture template tracked, runtime fixture gitignored
  - D-13 implemented: same .gitleaks.toml will be reused by CI (Plan 10)
metrics:
  duration_seconds: 179
  tasks_completed: 4
  files_changed: 5
  completed: 2026-04-28T17:40:44Z
---

# Phase 1 Plan 02: Secrets Hygiene & Tooling Config Summary

Established the secrets-hygiene + tooling-config layer for docintel: gitignore rules for secrets/data/build artifacts, an `.env.example` template that hardcodes the offline-stub default, pre-commit hooks pinned to STACK.md versions, and a shared gitleaks config used by both pre-commit and CI.

## What Was Built

### Task 1 — `.gitignore` extensions (commit `315a55d`)

Appended to the existing `.planning/`-only gitignore:

- **Secrets:** `.env`, `.env.*` with `!.env.example` exception, `*.key`, `*.pem` (Pitfall #26 — the career-grade key-leak risk).
- **Data:** `data/corpus/`, `data/indices/`, `data/traces/`, `data/eval/cache/`. **Intentionally NOT** included: `data/eval/reports/` — spec §10 / CLAUDE.md require those to be committed as part of the artifact.
- **Python build:** `__pycache__/`, `*.py[cod]`, `*$py.class`, `*.egg-info/`, `.eggs/`, `build/`, `dist/`, `.venv/`, `venv/`.
- **Tool caches:** `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `.coverage`, `htmlcov/`, `.uv-cache/`. Note: `uv.lock` is committed (deterministic builds).
- **OS / editors:** `.DS_Store`, `Thumbs.db`, `.idea/`, `.vscode/`, `*.swp`, `*~`.
- **Test fixtures:** `tests/fixtures/leaked_key.txt` only — the `.example` template is tracked.

`git check-ignore` confirms `.env`, `data/corpus/foo.pdf`, `data/indices/x`, `__pycache__/` all match. `.env.example` correctly does not match (un-ignored by the negation pattern).

### Task 2 — `.env.example` (commit `be9dd49`)

Repo-root template developers copy to `.env`. All variables use the `DOCINTEL_` prefix matching `Settings.model_config.env_prefix` (Plan 01):

- `DOCINTEL_LLM_PROVIDER=stub` — the only material default; offline-first per D-11/D-20.
- `DOCINTEL_ANTHROPIC_API_KEY=`, `DOCINTEL_OPENAI_API_KEY=` — blank for stub mode.
- `DOCINTEL_DATA_DIR=data` — local data directory default.
- `DOCINTEL_GIT_SHA=unknown` — Docker injects via `ARG GIT_SHA`; locally falls through to "unknown".

Triple-redundant stub default by design: `.env.example` (here), CI workflow `env:` block (Plan 10), and docker-compose env passthrough (Plan 07) will all set `LLM_PROVIDER=stub`.

### Task 3 — `.pre-commit-config.yaml` (commit `e59b949`)

Hooks run on `pre-commit` AND `pre-push` (D-19), pinned to STACK.md 2026-04-28 PyPI snapshot:

| Repo | Rev | Hooks |
|------|-----|-------|
| pre-commit/pre-commit-hooks | v5.0.0 | trailing-whitespace, end-of-file-fixer, check-yaml, check-toml, check-added-large-files (2 MB cap), detect-private-key |
| astral-sh/ruff-pre-commit | v0.15.12 | ruff (--fix), ruff-format |
| psf/black | 24.10.0 | black (python3.11) |
| gitleaks/gitleaks | v8.21.2 | gitleaks (--config=.gitleaks.toml) |

**Hook order rationale:** ruff fixes auto-fixable lint, black formats, gitleaks scans the staged content last so it sees the final form. detect-private-key is a cheap belt-and-suspenders before gitleaks runs.

### Task 4 — `.gitleaks.toml` + fixture (commit `3c0692c`)

`.gitleaks.toml` extends gitleaks default rules (`useDefault = true`) and adds an allowlist scoped narrowly:

- **Allowlist paths:** `^\.env\.example$`, `^\.gitleaks\.toml$` (the regex-shaped placeholders in this very file), `^tests/fixtures/leaked_key\.example$`, `^\.planning/`.
- **Allowlist regexes:** `sk-EXAMPLE...`, `sk-ant-api03-EXAMPLE...` — common doc placeholder shapes.

**Allowlist scope rationale:** keep it minimal so the default rule set still catches real leaks. The `.planning/` allowlist is necessary because planning docs may quote example keys. The fixture template is allowlisted so we can commit it; the runtime `leaked_key.txt` derived from it is **gitignored AND not allowlisted** — that asymmetry is exactly what Plan 09's test asserts (gitleaks must reject the runtime copy).

`tests/fixtures/leaked_key.example` contains a documented `sk-proj-AAAAAAA...` canonical sentinel — not a real key, but the same shape gitleaks scans for. Plan 09's pytest case will copy this content into a temporary `leaked_key.txt` and assert `gitleaks detect --no-git --source=<tmpfile> --config=.gitleaks.toml` exits non-zero.

## Verification

| Check | Result |
|-------|--------|
| `git check-ignore -v .env` | matches `.gitignore:4:.env` |
| `git check-ignore -v data/corpus/foo.pdf` | matches `.gitignore:11:data/corpus/` |
| `git check-ignore -v data/indices/x` | matches `.gitignore:12:data/indices/` |
| `git check-ignore -v __pycache__/` | matches `.gitignore:17:__pycache__/` |
| `git check-ignore -v .env.example` | exit 1 (un-ignored, tracked) |
| `.env.example` contains `DOCINTEL_LLM_PROVIDER=stub` | YES |
| `.pre-commit-config.yaml` references `.gitleaks.toml` | YES |
| `.gitleaks.toml` has `useDefault = true` and `[allowlist]` | YES |
| `tests/fixtures/leaked_key.example` has `sk-proj-` shape | YES |

**Deferred (out of scope here):** `pre-commit run --all-files` and `gitleaks detect` end-to-end runs require those tools to be installed locally; that runs in Plan 09 (test) and Plan 10 (CI workflow). Both binaries are pinned in the pre-commit config and Plan 10 will install them in CI.

## Deviations from Plan

None — plan executed exactly as written.

One minor process note: an early edit was inadvertently applied to the main repo's `.gitignore` (which lives outside this worktree). It was reverted with `git checkout -- .gitignore` before any commit was made there, and the same content was correctly applied inside the worktree. No commits in either tree were affected.

## Auth Gates

None encountered.

## Files Created/Modified

| File | Action | Commit |
|------|--------|--------|
| `.gitignore` | extended (kept `.planning/`) | `315a55d` |
| `.env.example` | created | `be9dd49` |
| `.pre-commit-config.yaml` | created | `e59b949` |
| `.gitleaks.toml` | created | `3c0692c` |
| `tests/fixtures/leaked_key.example` | created | `3c0692c` |

## Mapping to Phase Success Criteria

- **Success criterion #2** ("`gitleaks` pre-commit refuses to commit a fake API key"): the pre-commit hook + the `.gitleaks.toml` allowlist asymmetry (template tracked, runtime fixture gitignored AND not allowlisted) sets up the exact gate Plan 09's test will exercise.
- **Success criterion #3** ("`LLM_PROVIDER=stub` is the default in `.env.example`"): satisfied by Task 2.

## Requirements Closed

- **FND-06** (pre-commit hygiene with ruff/black/gitleaks): pre-commit-config in place, hooks pinned, gitleaks reused by CI per D-13.
- **FND-08** (`LLM_PROVIDER=stub` default): hardcoded in `.env.example`; will also be set in CI workflow (Plan 10) and docker-compose (Plan 07).

## Self-Check: PASSED

- `.gitignore` exists with required patterns: FOUND
- `.env.example` exists with `DOCINTEL_LLM_PROVIDER=stub`: FOUND
- `.pre-commit-config.yaml` exists with ruff + black + gitleaks: FOUND
- `.gitleaks.toml` exists with `useDefault=true` and allowlist: FOUND
- `tests/fixtures/leaked_key.example` exists with sk-proj- shape: FOUND
- Commit `315a55d` (Task 1): FOUND in git log
- Commit `be9dd49` (Task 2): FOUND in git log
- Commit `e59b949` (Task 3): FOUND in git log
- Commit `3c0692c` (Task 4): FOUND in git log
