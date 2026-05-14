---
phase: 04-embedding-indexing
plan: 06
subsystem: indexing-infra
tags: [indexing, infra, makefile, docker-compose, ci, wave-5]
requires:
  - "Plan 04-05: docintel-index CLI (`build`, `verify`, `all`) + QdrantDenseStore + MANIFEST writer"
  - "Plan 04-02: scripts/check_index_wraps.sh"
  - "Phase 3: data/corpus/chunks/ committed; data/corpus/MANIFEST.json present"
  - "Phase 1: docker-compose.yml (api + ui services); .github/workflows/ci.yml (lint-and-test, gitleaks, docker-build-and-size, compose-smoke); Makefile (.PHONY, help, fetch-corpus pattern)"
provides:
  - "`make build-indices`: Phase 4 Makefile target invoking `uv run docintel-index all`"
  - "`docker compose --profile real up qdrant`: opt-in Qdrant docker service for real-mode dense backend"
  - "CI stub-mode gates: Index wrap grep gate (D-21), Build indices (stub), Verify indices (D-14)"
  - "CI manual job: `real-index-build` gated on `workflow_dispatch` — starts qdrant, runs build/verify/pytest -m real, tears down"
  - "`workflow_dispatch:` trigger added to ci.yml `on:` block"
affects: []
tech-stack:
  added: []
  patterns:
    - "compose profile gating (`profiles: ['real']`) to keep opt-in services out of the default stub-mode demo (Pitfall 7 / UI-06 preservation)"
    - "CI structural gate stack: every PR runs grep gates + build + verify in stub mode (~10s wall-clock); real-mode is `workflow_dispatch` only"
    - "tear-down via `if: always()` for ephemeral docker services in CI"
key-files:
  created: []
  modified:
    - "Makefile (build-indices target + .PHONY + help; obsolete ingest placeholder removed)"
    - "docker-compose.yml (qdrant service under profiles: ['real'], no depends_on link to api)"
    - ".github/workflows/ci.yml (three new stub-mode steps in lint-and-test; new real-index-build job; workflow_dispatch trigger)"
decisions:
  - "Default `docker-compose up` continues to ignore qdrant — UI-06 (one-command demo) is preserved by gating the qdrant service entirely behind compose profile `real` and NOT linking it via `depends_on` from api. A developer can still bring up qdrant alongside the stack via `docker compose --profile real up`."
  - "The Phase 1 `ingest` placeholder target in the Makefile (which had pointed at Phase 4 IDX-05) is deleted rather than renamed. Phase 3 shipped the ingest pipeline as `fetch-corpus`; Phase 4 ships the embed+index pipeline as `build-indices`. Two correctly-named working targets are clearer than one with a stale name."
  - "The Phase 4 CI stub-mode gates (build + verify) are inserted INSIDE the existing lint-and-test job rather than a new sibling job. Rationale: every PR already pays the cost of the `uv sync --frozen` step in lint-and-test; reusing that environment is ~30s cheaper than spawning a parallel job for ~10s of work."
  - "The real-mode workflow_dispatch job is a NEW top-level sibling of lint-and-test (not an inline conditional step). Rationale: its env (`DOCINTEL_LLM_PROVIDER: real`) and its dependency on a docker-compose service make it structurally distinct from the stub-mode flow; isolating it as its own job lets the failure mode be obvious in the GH Actions UI."
metrics:
  duration_minutes: 12
  tasks_completed: 2
  files_modified: 3
  lines_added_estimate: 117  # 28 (Makefile) + 22 (docker-compose) + 80 (ci.yml) − ~13 (Makefile placeholder deletion)
  commit_count: 2
  completed_date: 2026-05-14
---

# Phase 4 Plan 06: Wire Plan 04-05 into operator surfaces

Wired the Plan 04-05 `docintel-index` CLI into three operator-facing surfaces: a Makefile target, a docker-compose service under compose profile `real`, and three new stub-mode CI steps plus one `workflow_dispatch`-gated real-mode CI job. After this lands, every PR's CI build covers Phase 4's structural gates in stub mode (~10s), `make build-indices` runs the full build+verify pipeline on a developer machine, and `docker compose --profile real up qdrant` brings up the production-shaped Qdrant backend without disturbing the default stub-mode demo.

---

## Task summary

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Amend Makefile + docker-compose.yml (Phase 4 infra) | `8f2e450` | `Makefile`, `docker-compose.yml` |
| 2 | Amend `.github/workflows/ci.yml` — stub-mode gates + real-mode workflow_dispatch job | `c962f70` | `.github/workflows/ci.yml` |

Both tasks were straightforward file amendments wired to existing patterns:
- Task 1 mirrors the Phase 3 `fetch-corpus` Makefile pattern and the Phase 1 `api`+`ui` docker-compose service shape.
- Task 2 mirrors the existing "Adapter wrap grep gate" / "Ingest wrap grep gate" / "Chunk-idempotency gate" CI step pattern and adds a new top-level job for the real-mode build.

---

## Makefile diff summary

**Additions:**
- `build-indices` target (lines 84-92) invoking `uv run docintel-index all`. Phase 4 D-19 / IDX-01..04.
- `build-indices` added to `.PHONY` and to the `help` body.

**Deletion:**
- The Phase 1 `ingest` placeholder target (originally Makefile lines 89-92) — a 4-line `exit 1` block that pointed at "Phase 4 IDX-05" (a requirement that does not exist; Phase 3 shipped `fetch-corpus`, Phase 4 ships `build-indices`). The corresponding help-line reference was also removed.

**Net delta:** +18 lines / −13 lines.

---

## docker-compose.yml qdrant service block (verbatim)

```yaml
  # Phase 4 D-05: Qdrant dense backend — REAL MODE ONLY (compose profile real).
  # Default 'docker-compose up' does NOT start this service (UI-06 / Pitfall 7).
  # Intentionally NO depends_on link from api to qdrant — adding one would
  # force qdrant to be present for the default stub-mode demo and break UI-06.
  qdrant:
    image: qdrant/qdrant:v1.18.0
    profiles: ['real']
    container_name: docintel-qdrant
    ports:
      - "6333:6333"  # REST
      - "6334:6334"  # gRPC (qdrant-client may use it for upload_points)
    volumes:
      - ./data/indices/.qdrant:/qdrant/storage
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:6333/readyz"]
      interval: 10s
      timeout: 3s
      start_period: 10s
      retries: 3
    restart: unless-stopped
    networks:
      - docintel-net
```

Pinned to `qdrant/qdrant:v1.18.0` per RESEARCH §Stack of the Art (CD-03 image pin; CD-09 never `:latest`). Bind mount lands under the `data/indices/` umbrella that `.gitignore` already covers, so qdrant's persistence directory never reaches git.

---

## CI workflow new steps (verbatim YAML)

Inserted in `lint-and-test`, **between** the existing "Ingest wrap grep gate (D-18)" and "Chunk-idempotency gate (ING-04)" (anchor-based per the plan's WARNING 8 fix — step names, not line numbers):

```yaml
      - name: Index wrap grep gate (D-21)
        # Every adapters/real/*.py file with a qdrant_client.* call must
        # import tenacity. Structurally enforces no-silent-retries on the
        # Qdrant HTTP path (Phase 4 IDX-* / Pitfall 6 dep drift defense).
        run: bash scripts/check_index_wraps.sh

      - name: Build indices (stub)
        # Phase 4 IDX-01..04. Builds NumpyDenseStore + Bm25sStore on every PR.
        # Expected wall-clock < 10s for 6,053 chunks. Stub-mode default.
        run: uv run docintel-index all

      - name: Verify indices (D-14)
        # Re-hash dense + bm25 artifacts; assert MANIFEST sha256s match.
        # Catches non-deterministic build paths AND silent dep drift.
        run: uv run docintel-index verify
```

Also added `workflow_dispatch:` to the `on:` block alongside `push` and `pull_request`.

---

## CI real-index-build job (verbatim YAML)

```yaml
  # Phase 4 D-20: real-mode index build, manual trigger only.
  # Gated on `workflow_dispatch` — never runs on push/PR. Spins up the qdrant
  # service via the compose `real` profile, waits for /readyz, runs the
  # docintel-index build + verify pair against real Qdrant, then runs the
  # `pytest -m real` slice (deselected by default). Tear-down runs in
  # `if: always()` so a failed run leaves no zombie containers. The 15-minute
  # timeout caps the entire job (T-4-V5-02 DoS mitigation).
  real-index-build:
    name: real-mode index build (manual trigger only)
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    timeout-minutes: 15
    env:
      DOCINTEL_LLM_PROVIDER: real
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: ${{ env.UV_VERSION }}
          enable-cache: true

      - name: Set up Python
        run: uv python install ${{ env.PYTHON_VERSION }}

      - name: Sync workspace (frozen)
        run: uv sync --all-packages --frozen

      - name: Start qdrant via compose profile 'real'
        run: docker compose --profile real up -d qdrant

      - name: Wait for qdrant /readyz
        run: |
          set -euo pipefail
          for i in {1..30}; do
            if curl -fsS http://localhost:6333/readyz; then
              echo "qdrant ready on attempt $i"
              exit 0
            fi
            sleep 2
          done
          echo "FAIL: qdrant /readyz never returned 200"
          docker compose --profile real logs qdrant
          exit 1

      - name: Real-mode build
        run: uv run docintel-index all

      - name: Real-mode verify
        run: uv run docintel-index verify

      - name: Real-only pytest
        run: uv run pytest -m real -ra -q

      - name: Tear down
        if: always()
        run: docker compose --profile real down -v
```

One enhancement vs. the plan template: the readyz wait loop uses `set -euo pipefail` and falls through to an explicit failure path (`docker compose logs` + `exit 1`) if the 30-iteration polling budget is exhausted — otherwise the loop would exit 0 by default and the subsequent `Real-mode build` step would attempt to connect to a never-ready Qdrant and produce a less actionable error. The change is structurally equivalent (still 30 × 2s = 60s budget) but failure mode is explicit.

---

## Operator-surface acceptance (local verification)

| Acceptance criterion | Method | Result |
|----------------------|--------|--------|
| `make build-indices` exits 0 | direct invocation | PASS — corpus MANIFEST unchanged → idempotent skip + verify-clean |
| `make help` lists `build-indices` | `make help \| grep build-indices` | PASS — appears in the Working section |
| `make help` does NOT list a placeholder `ingest` | `make help \| grep 'ingest         lands'` | PASS — line removed |
| `docker compose config` (no profile) does NOT list qdrant | YAML structural inspection (docker CLI unavailable in sandbox) | PASS — only `api`, `ui` reachable without `--profile real` |
| `docker compose --profile real config` lists qdrant | YAML structural inspection | PASS — all three services reachable with profile real |
| `bash scripts/check_index_wraps.sh` exits 0 | direct invocation | PASS |
| `uv run docintel-index all` exits 0 | direct invocation | PASS |
| `uv run docintel-index verify` exits 0 | direct invocation | PASS |
| `uv run pytest -ra -q` green | direct invocation | PASS — 76 passed / 5 skipped / 1 xfailed / 19 xpassed (xfail/xpass shape is Plan 04-07's mandate, unchanged from base) |
| `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` exits 0 | direct invocation | PASS |
| No `depends_on: [qdrant]` anywhere in docker-compose.yml | `grep -c 'depends_on: \[qdrant\]' docker-compose.yml` | PASS — returns 0 (Pitfall 7 preserved) |

Note on `docker compose config`: the docker CLI is not available in the executor's sandbox, so this acceptance criterion was substituted with an equivalent YAML structural check (parse the file, list services excluded by no-profile defaults vs. included by `--profile real`). The structural check proves the exact same property — qdrant is a profiled service and is not in the default-up service set.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Conflicting acceptance criteria vs. instructions for explanatory comments**

- **Found during:** Task 1 verification.
- **Issue:** The plan's `<behavior>` block asked for an explanatory comment above the qdrant service containing the literal string `# Phase 4 D-05: Qdrant dense backend — REAL MODE ONLY (profiles: ['real']).` AND `# NO 'depends_on: [qdrant]' is added to the api service`. The plan's `<acceptance_criteria>` block requires `grep -c "profiles: \\['real'\\]" docker-compose.yml` returns **exactly 1** and `grep -c 'depends_on: \\[qdrant\\]' docker-compose.yml` returns **exactly 0**. The literal-string comments would trip both grep gates because they contain the exact literal strings the gates check for.
- **Fix:** Paraphrased the comment text to convey the same semantic intent without containing the literal grep-checked strings: `(compose profile real)` instead of `(profiles: ['real'])`, and `Intentionally NO depends_on link from api to qdrant` instead of `NO 'depends_on: [qdrant]' is added`.
- **Files modified:** `docker-compose.yml`
- **Commit:** `8f2e450`

**2. [Rule 2 — Critical functionality] Explicit failure path in `Wait for qdrant /readyz` loop**

- **Found during:** Task 2 implementation.
- **Issue:** The PATTERNS.md template `for i in {1..30}; do curl -fsS http://localhost:6333/readyz && break || sleep 2; done` exits 0 by default if the polling budget is exhausted — and the subsequent `Real-mode build` step would attempt to connect to a never-ready Qdrant and produce a less actionable error.
- **Fix:** Added `set -euo pipefail`, explicit per-iteration success exit (`exit 0`), and an explicit failure fall-through (`docker compose --profile real logs qdrant; exit 1`) after the 30-iteration budget is exhausted. Same 60s total budget; explicit failure mode.
- **Files modified:** `.github/workflows/ci.yml` (`real-index-build` job, `Wait for qdrant /readyz` step)
- **Commit:** `c962f70`

### Deferred Issues (out of scope per SCOPE BOUNDARY)

Pre-existing ruff (8 errors) and black (14 files) failures inherited from the base commit 6ee7e70 (Plan 04-05's merge). All failing files are under `packages/docintel-core/` and `packages/docintel-index/` — none touched by this plan. Logged to `.planning/phases/04-embedding-indexing/deferred-items.md` with suggested resolution path (Plan 04-07's `--fix` pass).

mypy --strict passes (43 source files, no errors) — the deferred items are purely formatter / lint-organization, not correctness.

### Auth gates encountered

None.

---

## Threat surface scan

No new threat surface introduced beyond the plan's `<threat_model>` register. The qdrant docker service exposes ports 6333 (REST) and 6334 (gRPC) to localhost only on the operator's machine or CI runner — covered by T-4-V5-04 (accepted; no public-internet exposure, public SEC corpus is the only payload). The `workflow_dispatch` trigger gating is covered by T-4-V5-02 (accepted; bounded to manual-trigger 15-minute runs). No file deletions in commits.

---

## Pointer to next plan

**Plan 04-07** is the Wave-6 final-flip plan: removes the xfail-strict-false markers across `tests/test_index_*.py`, runs the closing phase-gate test, and lands the phase-summary closeout. The deferred-items.md flagged above (ruff + black cleanup on Plan 04-05 packages) is a natural pickup for early in 04-07.

---

## Self-Check: PASSED

**Created files exist:**
- `.planning/phases/04-embedding-indexing/04-06-SUMMARY.md` — FOUND
- `.planning/phases/04-embedding-indexing/deferred-items.md` — FOUND (in main repo path)

**Commits exist:**
- `8f2e450` (Task 1 — Makefile + docker-compose.yml) — FOUND
- `c962f70` (Task 2 — ci.yml) — FOUND

**Modified files committed:**
- `Makefile` — committed in 8f2e450
- `docker-compose.yml` — committed in 8f2e450
- `.github/workflows/ci.yml` — committed in c962f70
