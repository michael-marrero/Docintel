---
phase: 05-retrieval-hybrid-rerank
plan: 02
subsystem: retrieval
tags: [workspace, package-scaffold, pydantic-model, contract-types, wave-0]
requires:
  - "Phase 4 indices on disk (docintel-index workspace package — analog for pyproject.toml shape)"
  - "docintel-core workspace package present (numpy==2.4.4 pin source of truth; existing __all__ list in types.py)"
provides:
  - "docintel-retrieve workspace package skeleton (7th workspace member) with empty public surface ready for Plans 05-03/05-04/05-05 to extend"
  - "RetrievedChunk Pydantic v2 model in docintel_core.types — seven D-03 fields, ConfigDict(extra='forbid', frozen=True), re-exported from docintel_retrieve"
  - "uv.lock regenerated with new workspace member; uv lock --check exits 0"
affects:
  - "Wave 1 plans 05-03/05-04/05-05 can now import docintel_retrieve.* and instantiate RetrievedChunk"
  - "Phase 6 (reader) + Phase 7 (generation) + Phase 13 (UI) can now `from docintel_core.types import RetrievedChunk` per CD-02 without depending on the retrieve package"
tech-stack:
  added: []
  patterns:
    - "Library-only workspace package (no [project.scripts]) per D-01 — Phase 5 CLI deferred to Phase 10/13"
    - "Atomic class-creation + re-export pattern (plan-checker WARNING 5 fix): Task 1 ships empty __all__ skeleton, Task 2 atomically adds class to docintel_core AND extends docintel_retrieve __init__ in the same commit"
    - "Pydantic v2 ConfigDict(extra='forbid', frozen=True) for retrieval DTO — structural defense against per-stage debug field leakage (RESEARCH.md anti-pattern line 622) AND post-construction mutation"
    - "Explicit numpy re-pin from docintel-core source of truth (FND-09 pattern) — numpy==2.4.4 verbatim"
key-files:
  created:
    - "packages/docintel-retrieve/pyproject.toml"
    - "packages/docintel-retrieve/src/docintel_retrieve/__init__.py"
    - "packages/docintel-retrieve/src/docintel_retrieve/py.typed"
  modified:
    - "packages/docintel-core/src/docintel_core/types.py"
    - "pyproject.toml"
    - "uv.lock"
decisions:
  - "Numpy pin in packages/docintel-retrieve/pyproject.toml is `numpy==2.4.4` — copied verbatim from packages/docintel-core/pyproject.toml (the source of truth) per FND-09 explicit-re-pin pattern. NOT a free invention."
  - "Workspace root [tool.uv.sources] reflowed to align '=' across all rows when inserting docintel-retrieve (alphabetical position between docintel-index and docintel-ingest). Visual parity only — uv lock does not care about whitespace."
  - "Task 2 RetrievedChunk class docstring deliberately *names* the forbidden per-stage debug fields (bm25_rank, dense_rank, rrf_score, rerank_score) as documented anti-patterns. Future maintainers grepping for those names land on the prose explanation of why they're forbidden."
metrics:
  duration: "7 minutes"
  tasks: 2
  files_created: 3
  files_modified: 3
  completed: "2026-05-14"
---

# Phase 05 Plan 02: docintel-retrieve Package Skeleton + RetrievedChunk Model Summary

Land the structural Wave-0 piece that Wave-1 plans (05-03..05-05) build on: a new 7th workspace package (`docintel-retrieve`) with an empty public surface, and the `RetrievedChunk` Pydantic v2 contract model in `docintel_core.types` per CD-02.

## What This Plan Did

Two atomic commits — Task 1 ships the package skeleton with `__all__ = []`, Task 2 atomically adds both the `RetrievedChunk` class to `docintel_core.types` AND the matching re-export in `docintel_retrieve/__init__.py` in a single commit. This sequencing addresses the plan-checker WARNING 5 cross-task-coupling issue: Task 1's acceptance does not depend on `RetrievedChunk` existing, and Task 2's class definition and public-surface re-export land coherently at HEAD.

After this plan, `uv lock --check` exits 0 with 7 workspace members (was 6), `from docintel_retrieve import RetrievedChunk` works, `RetrievedChunk(extra=...)` raises `ValidationError`, and `rc.score = X` after construction raises `ValidationError`.

## Task 1 — Package Skeleton (commit `429045c`)

**Files created:**

- `packages/docintel-retrieve/pyproject.toml` — name `docintel-retrieve`, version `0.1.0`, `requires-python = ">=3.11,<3.13"`, dependencies `["docintel-core", "numpy==2.4.4"]`, `[build-system]` hatchling, `[tool.hatch.build.targets.wheel].packages = ["src/docintel_retrieve"]`. **NO `[project.scripts]` block** — Phase 5 is library-only per D-01; the CLI lives in Phase 10/13.
- `packages/docintel-retrieve/src/docintel_retrieve/__init__.py` — module docstring + `__all__: list[str] = []`. No imports, no re-exports. Self-contained acceptance: `import docintel_retrieve; docintel_retrieve.__all__ == []`. Task 2 atomically replaces the empty `__all__` with the re-export pair.
- `packages/docintel-retrieve/src/docintel_retrieve/py.typed` — 1-byte PEP 561 marker (matches `packages/docintel-index/src/docintel_index/py.typed`).

**Files modified:**

- `pyproject.toml` (workspace root) — extends `[tool.uv.sources]` with `docintel-retrieve = { workspace = true }` between `docintel-index` and `docintel-ingest`. All six existing source rows re-aligned so the `=` column lines up visually (one extra character was needed). The `[tool.uv.workspace].members = ["packages/*"]` glob auto-discovers the new package — no edit needed there.
- `uv.lock` — regenerated via `uv lock` (NOT `uv sync`). Output: "Resolved 121 packages... Added docintel-retrieve v0.1.0". `git diff --shortstat uv.lock` → `1 file changed, 16 insertions(+)`.

**Numpy pin source of truth confirmation:** `packages/docintel-core/pyproject.toml` line 14 pins `numpy==2.4.4`. Plan 05-02 copies this verbatim into `packages/docintel-retrieve/pyproject.toml` per FND-09's explicit-re-pin pattern. No invention.

**Self-contained acceptance verified:** Task 1's `__init__.py` has no `from docintel_core.types import RetrievedChunk` import line. `RetrievedChunk` *is* mentioned in the module docstring as documentation of the *future* re-export — those mentions are prose, not Python-level surface. The structural test (`import docintel_retrieve; assert docintel_retrieve.__all__ == []`) passes against Task 1's HEAD without RetrievedChunk needing to exist.

## Task 2 — RetrievedChunk Class + Atomic Re-Export (commit `67901df`)

Three coupled edits in one commit:

**Edit 1 — extend `__all__` in `docintel_core/types.py`:** Insert `"RetrievedChunk"` in alphabetical position after `"NormalizedFilingManifest"`. Now nine names (was eight).

**Edit 2 — add the `RetrievedChunk` class.** Position: between `Chunk` and `IndexManifestEmbedder` per the analog placement decision. Verbatim source (downstream plans can grep against this — and pin against the exact field declarations):

```python
class RetrievedChunk(BaseModel):
    """A single retrieval result returned by ``Retriever.search`` (Phase 5).

    D-03: the public retrieval shape is exactly seven fields — ``chunk_id``,
          ``text``, ``score``, ``ticker``, ``fiscal_year``, ``item_code``,
          ``char_span_in_section``. Per-stage debug fields (``bm25_rank``,
          ``dense_rank``, ``rrf_score``, ``rerank_score``) are deliberately
          OMITTED from the public model — they are internal accounting that
          downstream callers (Phase 6 reader, Phase 7 generation, Phase 13
          UI) MUST NOT depend on. RESEARCH.md anti-pattern line 622 forbids
          leaking them onto the public shape; ``ConfigDict(extra="forbid")``
          is the bite point.
    D-16: ``char_span_in_section`` is the citation anchor — Phase 7's
          ``Citation`` will render the chunk text inline AND offer an
          "expand" affordance that highlights the span in the surrounding
          section text. Same semantics as ``Chunk.char_span_in_section``.
    CD-02: this model lives in ``docintel_core.types`` (not in
          ``docintel_retrieve.types``) so Phase 6 / 7 / 13 can import it
          without depending on the retrieve package. The schema is a
          contract; the retrieve package re-exports it as a convenience.
    Frozen=True: downstream callers MUST NOT mutate the result list —
          ``rc.score = X`` raises ``pydantic.ValidationError`` after
          construction. This is defense-in-depth against a Phase 7
          reranker-output-shape mistake that would otherwise silently
          corrupt RRF scores in shared result lists.

    The ``score`` field is the final score a caller should compare against —
    after the reranker stage in the default pipeline, or the RRF score in
    the no-rerank ablation (Phase 11). Callers should not need to know
    which stage produced it; the orchestrator owns the policy.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    text: str
    # final reranker score (or RRF score in no-rerank ablation)
    score: float
    ticker: str
    fiscal_year: int
    # e.g., "Item 1A" — matches Phase 3 Chunk.item_code
    item_code: str
    # citation anchor — Phase 3 D-16
    char_span_in_section: tuple[int, int]
```

Field count: exactly seven. No `bm25_rank` / `dense_rank` / `rrf_score` / `rerank_score` field declarations (confirmed by grep on `^    {name}: ` patterns inside the class body). The forbidden names appear only inside the docstring as documented anti-patterns.

**Edit 3 — extend `docintel_retrieve/__init__.py`:** Replace the Task-1 line `__all__: list[str] = []` with the re-export pair:

```python
from docintel_core.types import RetrievedChunk

__all__ = ["RetrievedChunk"]
```

The class definition (Edit 2) and the public-surface re-export (Edit 3) land in the same commit so `docintel_retrieve.RetrievedChunk` and `docintel_core.types.RetrievedChunk` are coherent at HEAD.

## Verification (Plan-Level)

| # | Check | Result |
|---|-------|--------|
| 1 | `uv lock --check` exits 0 (7-member workspace in sync) | PASS |
| 2 | `uv run mypy --strict packages/docintel-core/src/docintel_core/types.py` clean | PASS |
| 2b | `uv run mypy --strict` (whole workspace) — no NEW errors introduced by Plan 05-02 | PASS (11 pre-existing errors in unrelated packages remained unchanged; baseline = 11 errors in 5 files, post-plan = 11 errors in 5 files) |
| 3 | `tests/test_retrieved_chunk_schema.py` 4 passed | DEFERRED (see below — Plan 05-01 sibling worktree) |
| 4 | Full pytest suite — `uv run pytest -ra -q` → 96 passed, 5 skipped, 0 failed | PASS |
| 5 | Three grep gates (`check_index_wraps.sh` + `check_adapter_wraps.sh` + `check_ingest_wraps.sh`) | PASS |
| 6 | `uv run python -c "from docintel_retrieve import RetrievedChunk; print(RetrievedChunk)"` prints class object | PASS |
| 7 | `uv run python -c "import docintel_retrieve; assert docintel_retrieve.__all__ == ['RetrievedChunk']"` | PASS |

**Behavioral verifications (run against final HEAD):**

| # | Behavior | Result |
|---|----------|--------|
| B1 | `RetrievedChunk(...)` with all 7 fields constructs and round-trips; `rc.char_span_in_section` is `tuple[int, int]` (not list) | PASS |
| B2 | `RetrievedChunk(..., bm25_rank=3)` raises `pydantic.ValidationError` (extra="forbid") | PASS |
| B3 | `rc.score = 0.99` after construction raises `pydantic.ValidationError` (frozen=True) | PASS |
| B4 | `"RetrievedChunk" in docintel_core.types.__all__` | PASS |
| B5 | `from docintel_retrieve import RetrievedChunk` succeeds AND `"RetrievedChunk" in docintel_retrieve.__all__` | PASS |

## Deviations from Plan

### Documented adjustments

**1. [Documentation note — not a Rule deviation] Plan-script `! grep -F 'RetrievedChunk' ...` source-assertion check.**

- **Where:** Task 1 acceptance criteria, source-assertion bullet 5.
- **Issue:** The plan prescribes a docstring for Task 1's `__init__.py` that *mentions* `RetrievedChunk` twice (once in `Retriever.search(query, k) -> list[RetrievedChunk]` and once in the bulleted plan-by-plan history). The plan ALSO prescribes a source-assertion that `! grep -F 'RetrievedChunk' packages/docintel-retrieve/src/docintel_retrieve/__init__.py` returns no matches. The two are mutually inconsistent.
- **Resolution:** Honored the plan's *intent* (no Python-level import or `__all__` entry for `RetrievedChunk` in Task 1) — confirmed by `grep -q '^from docintel_core'` returning no matches and `__all__: list[str] = []` being present. The two prose mentions inside the module docstring are exactly the text the plan's `<action>` block specifies.
- **Action:** None — the docstring as-shipped is exactly what the plan asked for; the source-assertion command was over-strict relative to the prescribed docstring. The semantic intent (Task 1 ships no Python-level re-export) is satisfied.

### Auto-fixed Issues

None — Tasks 1 and 2 executed exactly as planned. No Rule-1/2/3 deviations encountered.

### Deferred Issues

**1. `tests/test_retrieved_chunk_schema.py` xfail-flip — not in this worktree.**

- **Found during:** Task 2 setup (read_first phase).
- **Issue:** The plan's Task 2 action block prescribes deleting four `@pytest.mark.xfail(strict=True, reason="Wave N — Plan 05-02 ...")` decorators from `tests/test_retrieved_chunk_schema.py`. That file is the deliverable of Plan 05-01, which runs in PARALLEL in a sibling worktree as part of the same Wave-0 wave. The file does NOT exist in this worktree (`find tests -name 'test_retrieved_chunk_schema*'` returns empty).
- **Why deferred (not a bug):** Plan 05-02's behavior verification (B1-B5 above) covers the schema contract directly via inline Python `-c` checks. The xfail-flip cleanup is a post-merge concern — when both Wave-0 worktrees land on the integration branch, the xfail-marker removal can be done either as a follow-up commit on the integration branch or rolled into the Plan 05-01 worktree's final commit if planners prefer.
- **Action item for integration:** After Plan 05-01 + Plan 05-02 merge, edit `tests/test_retrieved_chunk_schema.py` to delete the four `@pytest.mark.xfail(strict=True, reason="Wave N — Plan 05-02 ...")` decorators. Run `uv run pytest tests/test_retrieved_chunk_schema.py -ra -q` and confirm `4 passed`.

**2. `[project.urls]`-style or homepage metadata in `docintel-retrieve/pyproject.toml`.**

- The plan does not prescribe a homepage URL or repository URL on the new package. The analog (`docintel-index/pyproject.toml`) also omits these. No deferred work — this is consistent with the rest of the workspace.

## Threat Surface Scan

Plan 05-02 ships a Pydantic model and a workspace package skeleton. No new SDK call, no I/O, no network, no env-var read. Threat surface review:

- **T-5-V5-01-shape (Tampering — schema drift):** Mitigated by `ConfigDict(extra="forbid")` on `RetrievedChunk`. The behavior verification B2 (extra `bm25_rank` → `ValidationError`) is the bite-point regression test against future PRs that try to leak per-stage debug fields onto the public shape.
- **T-5-V5-mutability (Tampering — post-construction mutation):** Mitigated by `ConfigDict(frozen=True)`. Behavior verification B3 enforces.
- **T-5-V5-task1-coupling (Process — cross-task acceptance coupling):** Mitigated by the atomic Task 1 / Task 2 split. Task 1 ships `__all__ = []` (self-contained acceptance); Task 2 atomically adds class + re-export in one commit. WARNING 5 from plan-checker addressed.

No new threat surface introduced. No flags raised.

## Decisions Recorded

- **Numpy pin in `docintel-retrieve/pyproject.toml`:** `numpy==2.4.4`. Source of truth: `packages/docintel-core/pyproject.toml` line 14. Copied verbatim per FND-09. Future numpy bumps in docintel-core must also bump this file (Phase 5 has no transitive coverage that would auto-bump it).
- **Library-only package:** `docintel-retrieve` ships NO `[project.scripts]` block per D-01. Phase 5 exposes its public surface only as importable Python; the CLI affordance is Phase 10/13 work.
- **CD-02 placement:** `RetrievedChunk` lives in `docintel_core.types`, NOT `docintel_retrieve.types`. Rationale: Phase 6 reader, Phase 7 generation, Phase 13 UI need to import the model without taking a hard dependency on the retrieve package. The retrieve package's re-export is a convenience for cohesion, not the canonical home.
- **Frozen + extra=forbid pair:** Pattern S1 (RESEARCH.md line 1169) — defense-in-depth against both the schema-drift attack (extra fields silently flowing through) and the post-construction-mutation attack (a downstream reranker corrupting the score field in a shared result list).

## Files in Final State

```
packages/docintel-retrieve/
├── pyproject.toml                       (NEW — Task 1)
└── src/
    └── docintel_retrieve/
        ├── __init__.py                  (NEW — Task 1 empty skeleton; Task 2 added re-export)
        └── py.typed                     (NEW — Task 1; 1 byte)

packages/docintel-core/src/docintel_core/
└── types.py                             (MODIFIED — Task 2: +RetrievedChunk class, +__all__ entry)

pyproject.toml                           (MODIFIED — Task 1: +docintel-retrieve in [tool.uv.sources])
uv.lock                                  (MODIFIED — Task 1: +16 lines for docintel-retrieve v0.1.0)
```

## Commits

| Task | Hash | Type | Description |
|------|------|------|-------------|
| 1 | `429045c` | feat | scaffold docintel-retrieve workspace package skeleton |
| 2 | `67901df` | feat | add RetrievedChunk model + atomic re-export from docintel_retrieve |

## Self-Check: PASSED

- File `packages/docintel-retrieve/pyproject.toml` exists at HEAD.
- File `packages/docintel-retrieve/src/docintel_retrieve/__init__.py` exists at HEAD.
- File `packages/docintel-retrieve/src/docintel_retrieve/py.typed` exists at HEAD (1 byte).
- File `packages/docintel-core/src/docintel_core/types.py` modified (RetrievedChunk class + __all__).
- File `pyproject.toml` modified (workspace [tool.uv.sources] extension).
- File `uv.lock` modified (regenerated; +16 lines).
- Commit `429045c` exists in `git log --oneline -3`.
- Commit `67901df` exists in `git log --oneline -3`.
- `uv lock --check` exits 0.
- `uv run python -c "from docintel_retrieve import RetrievedChunk"` succeeds.
- Full pytest suite: 96 passed, 5 skipped, 0 failed.
- mypy delta: 0 new errors introduced (baseline 11 pre-existing errors in unrelated packages unchanged).
