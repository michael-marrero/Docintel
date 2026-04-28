---
phase: 01-scaffold-foundation
plan: 01
subsystem: foundation
tags: [scaffolding, uv-workspace, pydantic-settings, structlog]
requires: []
provides:
  - "uv-workspace-root"
  - "docintel-core-package"
  - "docintel-api-package-skeleton"
  - "docintel-ui-package-skeleton"
  - "docintel-eval-package-skeleton"
  - "Settings-model"
  - "structlog-configure-logging"
  - "uv.lock"
affects:
  - "all-phase-1-plans-after-01"
  - "all-phase-2-plus-plans-import-docintel_core"
tech_stack_added:
  - "uv 0.11.8"
  - "pydantic 2.13.3"
  - "pydantic-settings 2.14.0"
  - "structlog 25.5.0"
  - "hatchling (build-backend)"
patterns:
  - "uv workspace with packages/* members"
  - "pydantic-settings env_prefix=DOCINTEL_ as the single env reader"
  - "PEP 561 py.typed markers in every package"
key_files_created:
  - "pyproject.toml"
  - ".python-version"
  - "packages/docintel-core/pyproject.toml"
  - "packages/docintel-core/src/docintel_core/__init__.py"
  - "packages/docintel-core/src/docintel_core/config.py"
  - "packages/docintel-core/src/docintel_core/types.py"
  - "packages/docintel-core/src/docintel_core/log.py"
  - "packages/docintel-core/src/docintel_core/py.typed"
  - "packages/docintel-api/pyproject.toml"
  - "packages/docintel-api/src/docintel_api/__init__.py"
  - "packages/docintel-api/src/docintel_api/py.typed"
  - "packages/docintel-ui/pyproject.toml"
  - "packages/docintel-ui/src/docintel_ui/__init__.py"
  - "packages/docintel-ui/src/docintel_ui/py.typed"
  - "packages/docintel-eval/pyproject.toml"
  - "packages/docintel-eval/src/docintel_eval/__init__.py"
  - "packages/docintel-eval/src/docintel_eval/py.typed"
  - "uv.lock"
key_files_modified:
  - ".gitignore"
decisions:
  - "Settings.api_url default uses compose service name `api` (consumed by docintel-ui in Plan 04)"
  - "Workspace deviation from spec layout (D-01) accepted — per-service Docker images, hard module boundaries"
  - "mypy ignore_missing_imports = true for Phase 1 only (D-12); will tighten when Phase 2 lands typed protocols"
  - "Hatchling chosen as build-backend; uv handles editable installs internally"
metrics:
  duration_seconds: 898
  duration_human: "14m 58s"
  tasks_completed: 3
  files_created: 18
  files_modified: 1
  completed_date: "2026-04-28"
requirements_completed:
  - "FND-01"
  - "FND-02"
  - "FND-08"
---

# Phase 01 Plan 01: Scaffold uv Workspace + docintel_core Foundation Summary

uv workspace root with four sub-packages (`docintel-core`, `docintel-api`, `docintel-ui`, `docintel-eval`), the canonical `docintel_core.config.Settings` model gating `LLM_PROVIDER=stub`/`real`, and the first deterministic `uv.lock` (106 packages resolved). Phase 2+ now has a stable import target.

## Objective Recap

Stand up the uv workspace structural skeleton every later wave installs into. Lock CONTEXT.md decisions D-01..D-04 (workspace shape, uv-only, per-package pyproject, single env reader) and D-25 (first commit on phase branch is workspace pyproject + uv.lock). No FastAPI/Streamlit/Docker code yet — just imports, types, and the Settings object.

## What Was Built

### Workspace root
- `pyproject.toml` — workspace-only root with `[tool.uv.workspace]` `members = ["packages/*"]`, `[tool.uv.sources]` declaring all four packages `workspace = true`, plus shared ruff/black/mypy/pytest config.
- `.python-version` pinned to `3.11`.
- No runtime dependencies declared at root (per D-03).

### Package skeletons (all four)
Each under `packages/<name>/src/<module>/` with `__init__.py` and PEP 561 `py.typed`:

| Package | Pinned deps | Console script |
|---|---|---|
| `docintel-core` | pydantic 2.13.3, pydantic-settings 2.14.0, structlog 25.5.0 | — |
| `docintel-api` | docintel-core, fastapi 0.136.1, uvicorn[standard] 0.46.0, sentence-transformers 5.4.1 | `docintel-api = "docintel_api.main:run"` |
| `docintel-ui` | docintel-core, streamlit 1.56.0, httpx 0.28.1 | — |
| `docintel-eval` | docintel-core | `docintel-eval = "docintel_eval.cli:main"` |

### docintel_core implementation
- `__init__.py` — `__version__ = "0.1.0"` exported (consumed by `/health` in Plan 03).
- `config.py` — `Settings(BaseSettings)` with fields:
  - `llm_provider: Literal["stub", "real"] = "stub"` (FND-08 provider flip)
  - `anthropic_api_key: SecretStr | None = None`
  - `openai_api_key: SecretStr | None = None`
  - `data_dir: str = "data"`
  - `git_sha: str = "unknown"`
  - `api_url: str = "http://api:8000"`
  - `model_config = SettingsConfigDict(env_file=".env", env_prefix="DOCINTEL_", extra="ignore", case_sensitive=False)`
- `types.py` — empty placeholder (concrete types land in owning phases).
- `log.py` — `configure_logging(level=INFO)` configures structlog with JSON renderer, `merge_contextvars` processor (Phase 12 will add trace_id), `add_log_level`, ISO `TimeStamper`, stdlib `LoggerFactory`. Idempotent.

### Lockfile
- `uv.lock` resolves 106 packages from PyPI 2026-04-28 snapshot.
- `uv lock --check` exits 0.
- `uv sync --all-packages --frozen` installs in 22ms after first build.

## Verification Results

| Check | Result |
|---|---|
| `test -f pyproject.toml && grep '\[tool.uv.workspace\]'` | PASS |
| All four `packages/*/pyproject.toml` declare pinned deps | PASS |
| All four packages have `py.typed` markers | PASS |
| `__version__ == "0.1.0"` | PASS |
| `Settings().llm_provider == "stub"` (no env) | PASS |
| `Settings().api_url == "http://api:8000"` (no env) | PASS |
| `DOCINTEL_LLM_PROVIDER=real` → `Settings().llm_provider == "real"` | PASS |
| `os.environ` / `os.getenv` calls absent from `docintel_core/` | PASS |
| `uv lock --check` exits 0 | PASS |
| `uv sync --all-packages --frozen` exits 0 | PASS |
| Runtime: `uv run python -c 'from docintel_core ...'` prints `0.1.0 stub` | PASS |

## Commits

| # | Hash | Message |
|---|---|---|
| 1 | `6edfe61` | feat(01-01): add uv workspace root pyproject.toml + .python-version |
| 2 | `c6e671e` | feat(01-01): scaffold four uv workspace packages |
| 3 | `dde7702` | feat(01-01): implement docintel_core (Settings, log, types) + uv.lock |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Self-referential CI grep gate in config.py docstring**
- **Found during:** Task 3 verification.
- **Issue:** Original docstring read `CI greps for \`os.environ\` / \`os.getenv\` outside this file and fails on any match.` — but the docstring itself contains the literal tokens, which would match the gate's own grep regex. The plan's `<verify>` step uses `! grep -E 'os\.environ|os\.getenv' ...` and matched the docstring (exit 1 from the negated grep).
- **Fix:** Reworded the docstring to describe the gate without using the literal token sequences (`os dot environ / os dot getenv`). Behavioral effect: zero. Static-analysis effect: the gate's own self-reference no longer trips itself.
- **Files modified:** `packages/docintel-core/src/docintel_core/config.py`
- **Commit:** `dde7702`

**2. [Rule 2 - Missing critical infra] .gitignore lacked Python/venv/agent ignores**
- **Found during:** Task 3 pre-commit (`git status --short` showed `__pycache__/`, `.venv/` artifacts as untracked).
- **Issue:** `.gitignore` only contained `.planning/`. Without Python ignores, `__pycache__/`, `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.env`, and `.claude/` would all be committable.
- **Fix:** Extended `.gitignore` with standard Python + uv + agent ignores. `.planning/` retained.
- **Files modified:** `.gitignore`
- **Commit:** `dde7702`

### Auth Gates

None — no API keys touched in Phase 1 by design.

## Known Stubs

None. Plan 01-01 is structural scaffolding; every file's role is fully realized within its Phase 1 / Phase 2 scope.

## Threat Flags

None. Plan 01-01 introduces no network endpoints, auth paths, or trust boundaries — only package skeletons and a config model with `SecretStr` fields (which are explicitly `None`-default in this plan; populated only via env in real mode in later phases).

## Environment-Specific Note (informational, not a deviation)

On macOS-with-uv-managed-CPython 3.11.15, uv-build 0.11.8 sets `UF_HIDDEN` on the editable `_editable_impl_<package>.pth` files it writes into `.venv/lib/python3.11/site-packages/`. CPython's `site.py` (lines 176-178 in 3.11.15) skips `.pth` files with `UF_HIDDEN` set, so a fresh `uv sync` may produce a venv where workspace-member imports fail until the flag is cleared (`chflags nohidden .venv/lib/python3.11/site-packages/_editable_impl_*.pth`) or the package is reinstalled with `--reinstall-package`. This is uv-managed-Python + macOS specific; Linux CI is unaffected (no UF_HIDDEN flag on Linux). Phase 1 Plan 02 (CI) will run on Linux and not encounter this. Recorded here so a future macOS reviewer can debug it without re-deriving the cause.

## Where Future Phases Extend

- **Plan 01-02 onward (this phase):** Dockerfile, docker-compose.yml, FastAPI `/health` consuming `docintel_core.__version__` and `Settings.llm_provider`, Streamlit calling `Settings.api_url`, GitHub Actions running `uv lock --check` + ruff/black/mypy/pytest + gitleaks.
- **Phase 2:** `Embedder`, `Reranker`, `LLMClient`, `LLMJudge` protocols + at least one real and one stub adapter each, `make_adapters(cfg)` factory keyed on `Settings.llm_provider`. Tenacity retry wraps every LLM call.
- **Phase 12:** `log.configure_logging` extended with `contextvars` trace_id propagation. Phase 1's structure already imports `structlog.contextvars.merge_contextvars` so the trace fields drop in without restructuring.
- **Phase 13:** Streamlit's `Query`/`Traces`/`Eval-Results` tabs filled (labels locked in Plan 01-04 from CONTEXT.md D-16).

## Self-Check: PASSED

- All claimed files exist on disk under `packages/` and at workspace root.
- Three task commits exist in `git log` on this worktree branch (6edfe61, c6e671e, dde7702).
- `uv.lock` present at workspace root; `uv lock --check` exits 0.
- Settings runtime acceptance confirmed: `0.1.0 stub` printed from `uv run --package docintel-core`.
