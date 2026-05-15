# Phase 6: generation - Pattern Map

**Mapped:** 2026-05-15
**Files analyzed:** 21 (13 new + 8 modified)
**Analogs found:** 21 / 21

## File Classification

### New files to be created

| New File | Role | Data Flow | Closest Analog | Match Quality | Wave |
|----------|------|-----------|----------------|---------------|------|
| `packages/docintel-generate/pyproject.toml` | config (workspace package manifest) | n/a | `packages/docintel-retrieve/pyproject.toml` | exact | W0 |
| `packages/docintel-generate/src/docintel_generate/__init__.py` | config (package re-export surface) | n/a | `packages/docintel-retrieve/src/docintel_retrieve/__init__.py` | exact | W0 (skeleton) → W1/W2 (re-exports) |
| `packages/docintel-generate/src/docintel_generate/py.typed` | config (PEP 561 marker) | n/a | `packages/docintel-retrieve/src/docintel_retrieve/py.typed` | exact | W0 |
| `packages/docintel-generate/src/docintel_generate/prompts.py` | model/data (module-level prompt constants + hashes) | transform (import-time) | `packages/docintel-retrieve/src/docintel_retrieve/retriever.py` `Final[int]` constants (TOP_N_PER_RETRIEVER etc., lines 71-97) + `packages/docintel-core/src/docintel_core/adapters/stub/llm.py` sentinel constants (lines 23-37) | role-match (no perfect analog) | W1 |
| `packages/docintel-generate/src/docintel_generate/parse.py` | utility (pure regex helpers) | transform | `packages/docintel-core/src/docintel_core/adapters/stub/llm.py:31` `_CHUNK_RE` constant (will be MOVED, not duplicated) | exact (verbatim move) | W1 |
| `packages/docintel-generate/src/docintel_generate/generator.py` | service (orchestrator) | request-response | `packages/docintel-retrieve/src/docintel_retrieve/retriever.py` `Retriever` class (init + search + structlog) | exact | W2 |
| `scripts/check_prompt_locality.sh` | config (CI grep gate) | n/a | `scripts/check_adapter_wraps.sh` + `scripts/check_index_wraps.sh` + `scripts/check_ingest_wraps.sh` (all three share the same shape) | exact (3-way composite) | W0 |
| `tests/test_prompt_locality.py` | test (CI gate exit-code) | request-response | `tests/test_index_wraps_gate.py` (positive + negative bash invocation) | exact | W0 → flip in W4 |
| `tests/test_prompt_version_hash.py` | test (unit, module import) | transform | `tests/test_rrf_fuse.py` (`test_rrf_k_constant` — module-level constant assertion) + `tests/test_retrieved_chunk_schema.py` (Pydantic-shape pattern) | role-match | W0 → flip in W1 |
| `tests/test_generator_stub_determinism.py` | test (integration, stub) | request-response | `tests/test_retriever_search.py` (`test_retriever_returns_top_k` — `make_X(Settings(...))` + assert on results) | exact | W0 → flip in W2 |
| `tests/test_generator_refusal.py` | test (integration, dual refusal) | request-response | `tests/test_retriever_search.py` `test_zero_candidates` (CD-07 zero-candidate path) + `tests/test_reranker_canary.py` (dual-mode marker pattern) | role-match (combined) | W0 → flip in W2 |
| `tests/test_make_generator.py` | test (factory + lazy-import gate) | request-response | `tests/test_make_retriever.py` (all three tests verbatim) | exact | W0 → flip in W2 |
| `tests/test_judge_structured_output.py` | test (integration, real-mode judge) | request-response | `tests/test_reranker_canary.py` (`@pytest.mark.real` + xfail-until-wave-N pattern, lines 44-50) | role-match | W0 → flip in W3 |

### Files to be modified

| Modified File | Role | Data Flow | In-File Analog | Match Quality | Wave |
|---------------|------|-----------|----------------|---------------|------|
| `packages/docintel-core/src/docintel_core/types.py` | model (ADD `GenerationResult` Pydantic model) | n/a | `RetrievedChunk` class lines 148-191 (D-03 + CD-02 + `frozen=True` precedent) | exact | W2 |
| `packages/docintel-core/src/docintel_core/adapters/factory.py` | service (ADD `make_generator(cfg)` function) | request-response | `make_retriever(cfg)` lines 153-205 (full lazy-import + composition pattern) | exact | W2 |
| `packages/docintel-core/src/docintel_core/adapters/real/judge.py` | service (REMOVE `_JUDGE_SYSTEM_PROMPT`/`_build_judge_prompt`/`_SCORE_PATTERN` + REPLACE parser) | request-response | `packages/docintel-core/src/docintel_core/adapters/real/llm_anthropic.py` lines 102-156 (`@retry` + `client.messages.create` + return-shape pattern; judge's new structured-output call mirrors this) | partial (new code uses Anthropic adapter's call shape; old code uses heuristic regex) | W3 |
| `packages/docintel-core/src/docintel_core/adapters/stub/llm.py` | service (UPDATE `_STUB_REFUSAL` value + MOVE `_CHUNK_RE` to `parse.py` + re-import) | request-response | Existing in-file shape lines 23-37 (the constants block — value changes; the regex moves) | exact (in-place edit) | W3 |
| `.github/workflows/ci.yml` | config (ADD prompt-locality step) | n/a | Lines 89-106 (three existing wrap-grep-gate steps, same YAML shape) | exact | W4 |
| `CLAUDE.md` | doc (path-reference update) | n/a | Line 27 (single line referencing `src/docintel/generation/prompts.py`) | n/a (find-and-replace) | W0 (or W4) |
| `.planning/PROJECT.md` | doc (path-reference update) | n/a | Lines 31 + 66 (two references to `src/docintel/generation/prompts.py`) | n/a | W0 (or W4) |
| `.planning/REQUIREMENTS.md` | doc (path-reference update) | n/a | Line 56 (GEN-01 success criterion text) | n/a | W0 (or W4) |
| `.planning/ROADMAP.md` | doc (path-reference update) | n/a | Line 210 (Phase 6 `Provides:` line) | n/a | W0 (or W4) |
| `.planning/config.json` | doc/config (path-reference update) | n/a | Line 15 (`constraints.prompt_home`) | n/a | W0 (or W4) |

---

## Pattern Assignments

### `packages/docintel-generate/pyproject.toml` (config, workspace package manifest)

**Analog:** `packages/docintel-retrieve/pyproject.toml`

**Full pattern (16 lines, verbatim from analog — adapt name + description + deps):**

```toml
[project]
name = "docintel-retrieve"
version = "0.1.0"
description = "Hybrid retrieval (BM25 + dense via RRF) + cross-encoder rerank seam for docintel"
requires-python = ">=3.11,<3.13"
dependencies = [
    "docintel-core",
    "numpy==2.4.4",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/docintel_retrieve"]
```

**Deviation notes for Phase 6:**
- `name = "docintel-generate"` (D-01).
- `description = "Query-time generation: prompts module + Generator orchestrator + structured-output judge parser for docintel"`.
- `dependencies = ["docintel-core", "docintel-retrieve"]` (D-01 — adds `docintel-retrieve` workspace dep for `Retriever` + `RetrievedChunk`; transitive `anthropic`/`openai` via core's adapter deps; `numpy` NOT needed at this layer — no vectors, no embeddings).
- `packages = ["src/docintel_generate"]`.
- No `[project.scripts]` block — `docintel-generate` is library-only in v1 (per Code Context "Per-package Dockerfile target / no CLI").

**Anti-pattern flag:** Do NOT pin `anthropic` or `openai` SDK versions here — those live in `docintel-core/pyproject.toml` (single-pin discipline). Phase 6 only adds workspace deps.

---

### `packages/docintel-generate/src/docintel_generate/__init__.py` (config, re-export surface)

**Analog:** `packages/docintel-retrieve/src/docintel_retrieve/__init__.py`

**Full pattern (24 lines verbatim):**

```python
"""Phase 5 implementation — hybrid retrieval (BM25 + dense via RRF) + cross-encoder rerank seam.

Composes Phase 2 `AdapterBundle` + Phase 4 `IndexStoreBundle` into a single
`Retriever.search(query, k) -> list[RetrievedChunk]` seam.

See `docintel_retrieve.retriever` for the orchestrator class;
`docintel_retrieve.fuse` for the pure RRF helper;
`docintel_retrieve.null_adapters` for the Phase 11 ablation seam
(NullReranker + NullBM25Store).

Public surface is built up incrementally across Plans 05-02..05-05:
- Plan 05-02 Task 2 adds RetrievedChunk re-export (atomic with the class itself).
- Plan 05-03 adds RRF_K + _rrf_fuse re-exports.
- Plan 05-04 adds NullReranker + NullBM25Store re-exports.
- Plan 05-05 adds Retriever re-export.
"""

from docintel_core.types import RetrievedChunk

from docintel_retrieve.fuse import RRF_K, _rrf_fuse
from docintel_retrieve.null_adapters import NullBM25Store, NullReranker
from docintel_retrieve.retriever import Retriever

__all__ = ["RRF_K", "NullBM25Store", "NullReranker", "RetrievedChunk", "Retriever", "_rrf_fuse"]
```

**Deviation notes for Phase 6:**
- Docstring: rewrite for Phase 6 — "Phase 6 query-time generation. Composes Phase 5 Retriever + Phase 2 LLMClient into a single `Generator.generate(query, k) -> GenerationResult` seam." Mention `prompts.py` (canonical prompt home, GEN-01) and `parse.py` (regex + sentinel helpers).
- Re-exports per D-01:
  - `from docintel_core.types import GenerationResult` (D-17 — schema lives in core, re-exported as convenience matching `RetrievedChunk` precedent at line 18 of analog).
  - `from docintel_generate.generator import Generator` (Wave 2).
  - `from docintel_generate.prompts import SYNTHESIS_PROMPT, REFUSAL_PROMPT, JUDGE_PROMPT, PROMPT_VERSION_HASH` (Wave 1).
- `__all__` list: `["Generator", "GenerationResult", "JUDGE_PROMPT", "PROMPT_VERSION_HASH", "REFUSAL_PROMPT", "SYNTHESIS_PROMPT"]` (alphabetical, per analog convention).
- **Wave-incremental build-up applies:** Wave 0 skeleton stubs `__all__ = []`; Wave 1 adds the three `*_PROMPT` constants + `PROMPT_VERSION_HASH`; Wave 2 adds `Generator` + `GenerationResult`. Same pattern as Phase 5 (per docstring's "Public surface is built up incrementally" comment).

---

### `packages/docintel-generate/src/docintel_generate/py.typed` (config, PEP 561 marker)

**Analog:** `packages/docintel-retrieve/src/docintel_retrieve/py.typed`

**Full pattern:** empty file (zero bytes), marker only.

**Deviation notes:** None — verbatim copy.

---

### `packages/docintel-generate/src/docintel_generate/prompts.py` (model/data, transform)

**Primary analog (constant-block shape):** `packages/docintel-retrieve/src/docintel_retrieve/retriever.py` lines 71-119 (`Final[int]` + `Final[str]` module constants with docstrings).

**Secondary analog (sentinel-string pattern):** `packages/docintel-core/src/docintel_core/adapters/stub/llm.py` lines 23-37 (`_STUB_REFUSAL` and `_CHUNK_RE` as `Final[...]` with multi-line docstrings explaining the contract).

**Constant-with-rationale pattern (from `retriever.py:71-97`):**

```python
from typing import Final

TOP_N_PER_RETRIEVER: Final[int] = 100
"""D-05 — BM25 returns top-100, Dense returns top-100. RRF then fuses up to
200 ranked entries; the unique-chunk set is typically 120-180 with 10-K
boilerplate overlap. Recall payoff at 100 vs 50 is meaningful on near-
duplicate prose; 200 was rejected as diminishing returns at 6k chunks.
"""

TOP_M_RERANK: Final[int] = 20
"""D-06 — top-20 RRF-fused candidates go into ``Reranker.rerank``. bge-
reranker-base on CPU ≈ 20 ms per (query, chunk) pair → 20 pairs ≈ 0.4 s;
predictable and OK for both stub-mode CI and real-mode eval runs.
"""
```

**Sentinel-string pattern (from `stub/llm.py:23-37`):**

```python
_STUB_REFUSAL: Final[str] = "[STUB REFUSAL] No evidence found in retrieved context."
"""Canonical refusal string for the no-chunk path (GEN-04).

Phase 6 may replace this constant when formalising the prompt schema and
refusal contract. Phase 2 locks this text so Phase 9 stub-mode faithfulness
tests have a stable, predictable refusal sentinel.
"""

_CHUNK_RE: Final[re.Pattern[str]] = re.compile(r"\[([^\]]+)\]")
"""Module-level compiled regex for extracting [chunk_id] tokens.

Pattern is locked here for forward compatibility: Phase 6 introduces the
formal prompt schema; Phase 9 faithfulness tests rely on the same regex
producing the same citation extractions in stub and real modes.
"""
```

**Deviation notes for Phase 6:**
- Module shape (per D-07, D-08, D-11, RESEARCH.md Code Example 1, lines 854-930):
  1. `from __future__ import annotations` + `import hashlib` + `from typing import Final`.
  2. Local helper `def _h(s: str) -> str: return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]`.
  3. **CRITICAL header comment** above the three prompts: `# DO NOT reformat the body of these prompts — the SHA256[:12] hash is byte-exact.` (per Pitfall 3 — whitespace drift changes hash).
  4. Three `Final[str]` constants with triple-quoted bodies: `SYNTHESIS_PROMPT`, `REFUSAL_PROMPT`, `JUDGE_PROMPT`. Use `"""\` continuation form (RESEARCH Example 1 line 874) so the first newline is suppressed and the body starts at column 0.
  5. Four `Final[str]` hash constants: `_SYNTHESIS_HASH`, `_REFUSAL_HASH`, `_JUDGE_HASH`, `PROMPT_VERSION_HASH` (combined). All computed at module-load time (no runtime cost per query).
  6. One helper function `build_judge_user_prompt(prediction, reference, rubric="") -> str` — the user-prompt-builder for the judge migration (D-09, RESEARCH Example 1 lines 921-929).
- `SYNTHESIS_PROMPT` body MUST contain (D-10, D-11, RESEARCH Example 1 lines 874-891 verbatim):
  - The locked fenced citation example with `[AAPL-FY2024-Item-1A-018]` + `[NVDA-FY2024-Item-7-042]` chunk_ids.
  - Refusal instruction: "If the context does not contain enough information to answer the question, emit verbatim and ONLY this sentence: 'I cannot answer this question from the retrieved 10-K excerpts.'"
  - No-invented-chunk-ids rule + cite-from-context-only rule.
- `REFUSAL_PROMPT` = the exact 50-character sentinel string (D-11): `"I cannot answer this question from the retrieved 10-K excerpts."` — no trailing whitespace, no surrounding punctuation. CD-01 leaves exact `SYNTHESIS_PROMPT` and `JUDGE_PROMPT` body wording to planner.
- **Pitfall 9 deviation:** the `REFUSAL_TEXT_SENTINEL` constant that `Generator` and `adapters/stub/llm.py` import — researcher recommends placing it in `docintel_core.types` to avoid the core→generate import cycle (Pitfall 9 lines 826-838). Planner picks at execution time; PATTERNS.md does not lock the home. Whatever home, `REFUSAL_PROMPT` in `prompts.py` equals the same string body.

**Anti-pattern flag:** Do NOT add any prompt-related Settings fields (e.g., `DOCINTEL_REFUSAL_THRESHOLD`). FND-11 single-env-reader rule applies. Prompts are module constants, not env vars.

---

### `packages/docintel-generate/src/docintel_generate/parse.py` (utility, transform)

**Analog:** `packages/docintel-core/src/docintel_core/adapters/stub/llm.py:31` (the `_CHUNK_RE` constant — will be MOVED here, not duplicated).

**Verbatim from analog (4 lines including docstring):**

```python
_CHUNK_RE: Final[re.Pattern[str]] = re.compile(r"\[([^\]]+)\]")
"""Module-level compiled regex for extracting [chunk_id] tokens.

Pattern is locked here for forward compatibility: Phase 6 introduces the
formal prompt schema; Phase 9 faithfulness tests rely on the same regex
producing the same citation extractions in stub and real modes.
"""
```

**Deviation notes for Phase 6:**
- Module shape (D-12, D-13):
  1. `from __future__ import annotations` + `import re` + `from typing import Final`.
  2. Move `_CHUNK_RE` here from `stub/llm.py:31` (canonical home per D-12 — "Single regex across stub + real + Phase 7 parser").
  3. Optionally add `REFUSAL_TEXT_SENTINEL: Final[str] = "I cannot answer this question from the retrieved 10-K excerpts."` here OR in `docintel_core.types` (Pitfall 9 — planner picks; PATTERNS does not lock).
  4. Optionally a `def is_refusal(text: str) -> bool: return text.startswith(REFUSAL_TEXT_SENTINEL)` helper for re-use across `Generator` + stub + Phase 7 Citation parser. Single source of truth.
- Update `adapters/stub/llm.py` to `from docintel_generate.parse import _CHUNK_RE` (D-12). The `_CHUNK_RE` line in `stub/llm.py` is deleted; the import line is added below the existing `from docintel_core.adapters.types import ...` block.

**Anti-pattern flag:** Do NOT define `_CHUNK_RE` in BOTH `parse.py` AND `stub/llm.py`. The Phase 6 invariant is single canonical regex. `tests/test_generator_stub_determinism.py` should `from docintel_generate.parse import _CHUNK_RE` to confirm the move.

**Pitfall 9 cycle note:** This file is `docintel-generate.parse`, imported by `adapters/stub/llm.py` (which lives in `docintel-core`). That import is `docintel-core → docintel-generate`, which is the cycle direction Pitfall 9 flags. The pragmatic fix: move `_CHUNK_RE` to `docintel_core.types` or `docintel_core.adapters.types` instead of `docintel_generate.parse`. Planner picks. The PATTERN excerpt above is correct regardless of home — only the import path changes.

---

### `packages/docintel-generate/src/docintel_generate/generator.py` (service, request-response)

**Primary analog:** `packages/docintel-retrieve/src/docintel_retrieve/retriever.py` (the entire `Retriever` class structure — module docstring + Final constants + `__init__` + `.search()` + helper methods + structlog at end).

**Module docstring + imports pattern (from `retriever.py:1-68`):**

```python
"""Phase 5 D-02: a single ``Retriever.search(query, k) -> list[RetrievedChunk]``
callable that runs the full pipeline end-to-end. The pipeline order is
non-negotiable (Step A..G — RESEARCH.md Pattern 2 lines 433-516):

  A. query normalization — tokenize + truncate at 64 BGE tokens (D-11) ...
  ...

CD-04: this module composes already-wrapped adapter calls and adds NO new
tenacity wraps. The CI grep gates (...) are unchanged by Phase 5 — there are
no new SDK call sites in ``docintel-retrieve``.

FND-11: ``cfg: Settings`` passed in by the factory; this module does not
read environment variables.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Final

import numpy as np
import structlog
from docintel_core.adapters.types import AdapterBundle, IndexStoreBundle, RerankedDoc
from docintel_core.config import Settings
from docintel_core.types import Chunk, RetrievedChunk

from docintel_retrieve.fuse import _rrf_fuse

# Single structlog logger — no tenacity in this module (CD-04), so the
# SP-3 two-logger pattern (``_retry_log`` + ``log``) is intentionally NOT
# applied; the dead ``_retry_log`` placeholder would be misleading here.
log = structlog.stdlib.get_logger(__name__)
```

**Class shape — init + search pattern (from `retriever.py:122-180`):**

```python
class Retriever:
    """End-to-end query pipeline: BM25 + dense → RRF → rerank → top-K.

    D-02 single seam. Phase 6 calls ``.search()``; Phase 10 wraps it; ...

    CD-01: ``__init__`` eager-loads the ``chunk_id → Chunk`` map AND fires
    warm-up calls against both stores to trigger their ``_lazy_load_from_disk``
    paths (RESEARCH §5 — first-query latency property).
    """

    def __init__(
        self,
        bundle: AdapterBundle,
        stores: IndexStoreBundle,
        cfg: Settings,
    ) -> None:
        self._bundle = bundle
        self._stores = stores
        self._cfg = cfg
        # CD-01 — eager chunk-map load + MANIFEST cardinality check (Pitfall 7).
        self._chunk_map: dict[str, Chunk] = self._load_chunk_map()
        # ... warm-up calls ...

    def search(self, query: str, k: int = TOP_K_FINAL) -> list[RetrievedChunk]:
        t0 = time.perf_counter()
        # Step A — ...
        # Step B — ...
        # ... Step G telemetry at the bottom emits retriever_search_completed ...
```

**Structlog emission pattern (from `retriever.py:308-325`):**

```python
        # Step G — telemetry (D-12). Twelve fields verbatim; Phase 9 MET-05
        # + Phase 11 ablation reports source from this single log line.
        total_ms = (time.perf_counter() - t0) * 1000
        log.info(
            "retriever_search_completed",
            query_tokens=q_tokens,
            query_truncated=q_tokens > QUERY_TOKEN_HARD_CAP,
            bm25_candidates=len(bm25_results),
            dense_candidates=len(dense_results),
            rrf_unique=len(fused),
            rerank_input=len(top_m_chunks),
            results_returned=len(results),
            bm25_ms=round(bm25_ms, 2),
            dense_ms=round(dense_ms, 2),
            fuse_ms=round(fuse_ms, 2),
            rerank_ms=round(rerank_ms, 2),
            total_ms=round(total_ms, 2),
        )
        return results
```

**Zero-candidate / refusal path pattern (from `retriever.py:257-265`):**

```python
        # CD-07 — zero-candidate path. Phase 6 GEN-04 refusal path will take
        # over from here; the structlog warning is the observability hook
        # Phase 9 MET-05 can count.
        if not fused:
            log.warning(
                "retriever_search_zero_candidates",
                query=truncated_query[:100],
            )
            return []
```

**Deviation notes for Phase 6:**
- Imports (D-13, D-15, RESEARCH Pattern 1 lines 308-326):
  - Drop `numpy`, `json`, `Path`, `RerankedDoc`, `Chunk`, `_rrf_fuse`, `IndexStoreBundle` — `Generator` never touches embeddings, on-disk chunks, RRF, or the index stores directly (those are the `Retriever`'s concerns).
  - Add: `from docintel_core.adapters.types import AdapterBundle, CompletionResponse` and `from docintel_core.types import GenerationResult, RetrievedChunk` and `from docintel_retrieve.retriever import Retriever` and `from docintel_generate.parse import _CHUNK_RE` and `from docintel_generate.prompts import PROMPT_VERSION_HASH, REFUSAL_PROMPT, SYNTHESIS_PROMPT, _JUDGE_HASH, _REFUSAL_HASH, _SYNTHESIS_HASH`.
- Class shape per D-15, RESEARCH Pattern 1 lines 337-435:
  - `Generator.__init__(self, bundle: AdapterBundle, retriever: Retriever) -> None` — takes a constructed `Retriever` instance (NOT a `cfg`); factory composes them (D-03).
  - `__init__` body: just `self._bundle = bundle; self._retriever = retriever`. No eager-load (CD-03 — `Generator` instantiation is cheap; first-call cost is LLM SDK init, already lazy in `AnthropicAdapter._get_client`).
  - `.generate(query: str, k: int = 5) -> GenerationResult` — single public seam (D-15). Internal steps A..E mirroring `Retriever.search` A..G shape:
    - **Step A:** `retrieved = self._retriever.search(query, k=k)` + timed `retrieval_ms`.
    - **Step B (hard refusal):** if `not retrieved`, emit `generator_refused_zero_chunks` warn, build `GenerationResult(text=REFUSAL_TEXT_SENTINEL, cited_chunk_ids=[], refused=True, retrieved_chunks=[], completion=None, prompt_version_hash=PROMPT_VERSION_HASH)`, emit `generator_completed` telemetry, return.
    - **Step C:** `user_prompt = self._format_user_prompt(query, retrieved)` (private method per D-14); `completion = self._bundle.llm.complete(prompt=user_prompt, system=SYNTHESIS_PROMPT)` + timed `generation_ms`. No new `@retry` (CD-04 — already wrapped at adapter; same discipline as `Retriever` not double-wrapping `embedder.embed`).
    - **Step D:** `raw_ids = _CHUNK_RE.findall(completion.text)`; validate `cited ⊆ {c.chunk_id for c in retrieved}`; drop hallucinated IDs with `generator_hallucinated_chunk_id` warn (CD-07); detect refusal via `completion.text.startswith(REFUSAL_TEXT_SENTINEL)`.
    - **Step E:** build `GenerationResult`, emit `generator_completed` telemetry, return.
- `_format_user_prompt(query, retrieved)` method per D-14, RESEARCH Pattern 1 lines 399-412:
  - Build with `lines = ["<context>"]` then for each chunk `f"[chunk_id: {c.chunk_id} | company: {c.ticker} | fiscal_year: {c.fiscal_year} | section: {c.item_code}]"` header + raw `c.text` + `"---"` separator. Close with `"</context>"` + blank line + `f"Question: {query}"`. Return `"\n".join(lines)`.
- `generator_completed` structlog emission per D-16, RESEARCH Pattern 1 lines 417-434:
  - 14 fields: `query_tokens`, `n_chunks_retrieved`, `n_chunks_cited`, `refused`, `prompt_version_hash`, `synthesis_hash`, `refusal_hash`, `judge_hash`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `retrieval_ms`, `generation_ms`, `total_ms`, `model`. On hard-refusal path emit with `prompt_tokens=0, completion_tokens=0, cost_usd=0.0, model="stub-refusal"`. Match `Retriever`'s `round(ms, 2)` formatting discipline for timing fields.
- Logger pattern: SAME as `retriever.py:68`: single `log = structlog.stdlib.get_logger(__name__)`. Do NOT add the SP-3 two-logger pattern (`_retry_log`) — no tenacity wraps in this file (CD-04). The dead `_retry_log` would be misleading.

**Anti-pattern flag — DO NOT mirror these `Retriever` patterns:**
- The `_load_chunk_map` method (`retriever.py:386-444`) — `Generator` holds NO on-disk state. The chunk_map is inside the `Retriever` that `Generator` composes.
- The warm-up `try/except` calls in `__init__` (`retriever.py:173-180`) — `Generator` has no warm-up; LLM SDK init is already deferred lazy by `AnthropicAdapter._get_client`.
- The `_truncate_query` method (`retriever.py:328-384`) — query truncation already happened inside `self._retriever.search(query, k)`. `Generator` MUST NOT re-truncate (would emit a duplicate `retriever_query_truncated` line + waste tokens).
- The `_check_reranker_token_overflow` method (`retriever.py:446-484`) — Phase 5 canary defense, irrelevant to Phase 6.
- The MANIFEST cardinality check (`retriever.py:425-437`) — `Generator` doesn't touch indices.
- The `_CLAUDE_MD_HARD_GATE` constant (`retriever.py:100-119`) — Phase 5 canary text; Phase 6 does not need a hard-gate quote in this module.

---

### `packages/docintel-core/src/docintel_core/types.py` (MODIFIED — ADD `GenerationResult`)

**Analog (in-file):** `RetrievedChunk` class lines 148-191.

**Full pattern from analog (`types.py:148-191`):**

```python
class RetrievedChunk(BaseModel):
    """A single retrieval result returned by ``Retriever.search`` (Phase 5).

    D-03: the public retrieval shape is exactly seven fields — ``chunk_id``,
          ``text``, ``score``, ``ticker``, ``fiscal_year``, ``item_code``,
          ``char_span_in_section``. ...
    CD-02: this model lives in ``docintel_core.types`` (not in
          ``docintel_retrieve.types``) so Phase 6 / 7 / 13 can import it
          without depending on the retrieve package. The schema is a
          contract; the retrieve package re-exports it as a convenience.
    Frozen=True: downstream callers MUST NOT mutate the result list —
          ``rc.score = X`` raises ``pydantic.ValidationError`` after
          construction. ...
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

**Deviation notes for Phase 6 (D-17, RESEARCH Example 2 lines 934-986):**
- Add to `__all__` list (line 42-52): insert `"GenerationResult"` alphabetically between `"CompanyEntry"` and `"IndexManifest"`.
- New class shape (sibling of `RetrievedChunk`):
  ```python
  class GenerationResult(BaseModel):
      """Phase 6 generation output. Phase 7 Answer wraps this into the application schema.

      D-17: frozen=True so downstream callers cannot mutate (defense-in-depth against
      Phase 7 schema-shape mistakes that would otherwise silently corrupt shared lists).
      extra='forbid' so a tampered or partial construction raises pydantic.ValidationError
      immediately at the boundary.

      Home: docintel_core.types — matches RetrievedChunk precedent (Phase 5 CD-02). Phase 7
      Citation imports this contract without depending on docintel-generate.
      """

      model_config = ConfigDict(extra="forbid", frozen=True)

      text: str                              # raw LLM output (or REFUSAL_TEXT_SENTINEL on hard refusal)
      cited_chunk_ids: list[str]             # de-duplicated, validated against retrieved_chunks set
      refused: bool                          # True if hard zero-chunk OR LLM emitted refusal sentinel
      retrieved_chunks: list[RetrievedChunk] # the K chunks Phase 5 returned (frozen, immutable)
      completion: CompletionResponse | None  # None on hard refusal (LLM not called); otherwise the LLM's return
      prompt_version_hash: str               # combined PROMPT_VERSION_HASH at generation time
  ```
- **Critical import addition:** `from docintel_core.adapters.types import CompletionResponse` at top of file. `RetrievedChunk` is already in this module; `CompletionResponse` is in `adapters/types.py`. Importing it here creates a `docintel_core.types → docintel_core.adapters.types` dep — verify this is acyclic at runtime by reading both modules' import lists before committing.
- `CompletionResponse | None` is the PEP 604 union (already used in this codebase per `prev_chunk_id: str | None` in `Chunk` at line 142). No `Optional[...]` shim needed.

**Anti-pattern flag:**
- Do NOT add `score`, `confidence`, or any Phase 7 `Answer`-shaped fields here. `GenerationResult` is Phase 6's contract; Phase 7's `Answer` wraps it (per CONTEXT.md `<domain>` "Out of scope" — ANS-01..03).
- Do NOT add `query: str` to `GenerationResult` — the LLM's full prompt+system content is reconstructable from `retrieved_chunks` + the prompt module constants; Phase 7's `Answer.question_text` is the right home for that string.

---

### `packages/docintel-core/src/docintel_core/adapters/factory.py` (MODIFIED — ADD `make_generator`)

**Analog (in-file):** `make_retriever(cfg)` at lines 153-205.

**Full pattern verbatim (53 lines):**

```python
def make_retriever(cfg: Settings) -> Retriever:
    """Construct and return a Retriever composed of adapter + store bundles.

    Phase 5 D-04: third sibling factory alongside ``make_adapters(cfg)`` and
    ``make_index_stores(cfg)``. Calls both internally and constructs
    ``Retriever(bundle, stores, cfg)``. Lives in ``docintel_core.adapters.factory``
    (NOT in ``docintel-retrieve``) so the import direction matches every prior
    phase: ``docintel-retrieve`` imports from ``docintel-core``, never the reverse.

    Lazy-import discipline (D-12 + Pattern S5): ``from
    docintel_retrieve.retriever import Retriever`` lives INSIDE the function
    body so ``import docintel_core.adapters.factory`` stays cheap. ...

    The return-type annotation uses a string forward reference
    (``-> "Retriever"``) so no top-level (even TYPE_CHECKING) import of
    ``Retriever`` is required. mypy resolves the string by reading the
    function body's import.

    CD-01: eager-load. Constructing the Retriever loads the ...
    CD-08: NO factory-level cache — Phase 13 lru-caches at the FastAPI ...

    Args:
        cfg: Settings instance with ``llm_provider`` set ...
    Returns:
        Retriever ready to call ``.search(query, k)`` ...
    """
    # Lazy import — keeps `import docintel_core.adapters.factory` cheap
    # (D-12 + Pattern S5). The test_factory_lazy_imports_retriever_module
    # gate fails if this import is hoisted to module scope.
    from docintel_retrieve.retriever import Retriever

    bundle = make_adapters(cfg)
    stores = make_index_stores(cfg)
    return Retriever(bundle=bundle, stores=stores, cfg=cfg)
```

**Module-top TYPE_CHECKING addition pattern (from `factory.py:49-55`):**

```python
if TYPE_CHECKING:
    from docintel_retrieve.retriever import Retriever

    from docintel_core.adapters.real.judge import CrossFamilyJudge
    from docintel_core.adapters.real.llm_anthropic import AnthropicAdapter
    from docintel_core.adapters.real.llm_openai import OpenAIAdapter
    from docintel_core.config import Settings
```

**Deviation notes for Phase 6 (D-03, CD-03, CD-05, RESEARCH Example 3 lines 990-1031):**
- Add to `TYPE_CHECKING` block (after the existing `from docintel_retrieve.retriever import Retriever` line at 50): `from docintel_generate.generator import Generator`.
- New function `make_generator(cfg: Settings) -> Generator` placed AFTER `make_retriever` (alphabetical inversion — `make_generator` < `make_retriever`, but the natural ordering by phase number is generator-after-retriever; mirror Phase 5's append-to-end pattern).
- Body verbatim per RESEARCH Example 3 lines 1023-1028:
  ```python
  # Lazy import — keeps `import docintel_core.adapters.factory` cheap.
  from docintel_generate.generator import Generator

  bundle = make_adapters(cfg)
  retriever = make_retriever(cfg)
  return Generator(bundle=bundle, retriever=retriever)
  ```
- Docstring rewrite for Phase 6: mirror `make_retriever`'s structure (Phase X D-Y; the Nth sibling factory; lazy-import discipline; CD-XX eager-vs-lazy; CD-XX cache policy; Args + Returns).
- **Critical:** `make_generator` calls BOTH `make_adapters(cfg)` AND `make_retriever(cfg)`. The latter internally calls `make_adapters(cfg)` AGAIN. This means `make_adapters` runs twice when `make_generator` is invoked — that's OK because (a) it's a fresh `AdapterBundle` per call (no factory cache per CD-05), (b) `make_adapters` is cheap (~10 ms for stub mode, ~50 ms for real-mode without SDK init), (c) the two bundles will be DIFFERENT INSTANCES of identical adapter objects, which matters only if downstream stateful tracking ever lands on a per-instance basis (it does not in v1). Alternative considered + rejected: factor `make_retriever` to accept an optional `bundle` arg — but that breaks the Phase 5 D-04 signature contract.
- Module docstring update (lines 1-27): add a Phase 6 paragraph after the existing Phase 5 amendment (line 18-26): "Phase 6 amendment (D-03): `make_generator(cfg)` is the fourth sibling factory. It composes both `make_adapters(cfg)` and `make_retriever(cfg)` and constructs `docintel_generate.generator.Generator`. The Generator import lives INSIDE the function body (same lazy-import discipline)."

**Anti-pattern flag:**
- Do NOT add `@lru_cache` to `make_generator` (CD-05 — Phase 13 FastAPI caches at the dependency layer; eval harness constructs once per run). Mirrors `make_adapters` / `make_retriever` precedent.
- Do NOT factor out the `bundle = make_adapters(cfg)` duplication by passing the retriever's internal bundle through — the contract is "construct fresh per phase", and the cost is negligible.

---

### `packages/docintel-core/src/docintel_core/adapters/real/judge.py` (MODIFIED — migrate prompt + replace parser)

**Analogs:**
- For the **structured-output call shape** — `packages/docintel-core/src/docintel_core/adapters/real/llm_anthropic.py` lines 102-156 (the `@retry`-wrapped `client.messages.create` pattern; judge's structured-output call has the SAME shape with an added `tools=[...]` + `tool_choice=...` block).
- For the **prompt-import + delegate-retry-to-`self._llm`** discipline — current `adapters/real/judge.py` lines 28, 162-190 (the existing `from tenacity import retry` ADP-06 import + `_llm.complete(...)` call).

**Anthropic `@retry` + `client.messages.create` pattern (from `llm_anthropic.py:102-138`):**

```python
    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError)),
        before_sleep=before_sleep_log(_retry_log, logging.WARNING),
        reraise=True,
    )
    def complete(
        self,
        prompt: str,
        system: str | None = None,
    ) -> CompletionResponse:
        """..."""
        client = self._get_client()
        t0 = time.perf_counter()
        response = client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            system=system or "You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        # ... usage + cost + CompletionResponse construction ...
```

**Existing judge — tenacity-import-for-CI-gate pattern (from `judge.py:28-36`, KEEP as-is):**

```python
from tenacity import retry  # noqa: F401 — imported for ADP-06 gate; retry delegated to self._llm

# The tenacity import above is intentional even though no @retry decorator
# appears in this file. CrossFamilyJudge delegates retry responsibility to
# self._llm.complete(), which is already @retry-wrapped by AnthropicAdapter
# or OpenAIAdapter. Adding a second @retry here would double-wrap and create
# retry storms. The import satisfies the structural ADP-06 contract ...
```

**Deviation notes for Phase 6 (D-09, RESEARCH Pattern 3 lines 501-583):**

**Lines to REMOVE:**
- Line 25: `import re` (no longer needed once `_SCORE_PATTERN` is gone).
- Lines 44-49: `_JUDGE_SYSTEM_PROMPT = (...)` constant block.
- Line 52: `_SCORE_PATTERN = re.compile(r"score\s*:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)`.
- Lines 55-73: `def _build_judge_prompt(prediction, reference, rubric) -> str:` — replaced by `from docintel_generate.prompts import build_judge_user_prompt`.
- Lines 76-97: `def _parse_judge_response(text) -> JudgeVerdict:` — replaced by structured-output deserialization inside `.judge()`.

**Lines to PRESERVE (Phase 2 D-04 contract):**
- Lines 1-43: module docstring + imports + `_retry_log` + `log`.
- Lines 100-160: the `CrossFamilyJudge` class shell + `__init__` + degraded-mode detection + `.name` property.

**Lines to MODIFY — the `.judge()` method body (currently lines 162-190):**

The method becomes provider-dispatched. The Phase 2 D-04 cross-family wiring is preserved at the FACTORY level (`make_adapters` line 91-102); inside `.judge()` we need to detect which underlying adapter `self._llm` is, and use the appropriate SDK's structured-output API.

Per RESEARCH Pattern 3 (lines 519-582), the new shape is roughly:

```python
import json

from docintel_core.adapters.types import JudgeVerdict
from docintel_generate.prompts import JUDGE_PROMPT, build_judge_user_prompt

_JUDGE_VERDICT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "passed": {"type": "boolean"},
        "reasoning": {"type": "string"},
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "passed", "reasoning", "unsupported_claims"],
}

def judge(
    self,
    prediction: str,
    reference: list[str],
    rubric: str = "",
) -> JudgeVerdict:
    """..."""
    user_prompt = build_judge_user_prompt(prediction, reference, rubric)
    # Dispatch by underlying adapter family (Phase 2 D-04 cross-family wiring).
    # Lazy imports to avoid circular core→real→core cycles at module load.
    from docintel_core.adapters.real.llm_anthropic import AnthropicAdapter
    from docintel_core.adapters.real.llm_openai import OpenAIAdapter

    if isinstance(self._llm, AnthropicAdapter):
        return _judge_via_anthropic(self._llm._get_client(), user_prompt)
    elif isinstance(self._llm, OpenAIAdapter):
        return _judge_via_openai(self._llm._get_client(), user_prompt)
    else:
        raise TypeError(f"unsupported judge adapter type: {type(self._llm).__name__}")
```

Plus two module-level helpers `_judge_via_anthropic` and `_judge_via_openai` per RESEARCH Pattern 3 lines 532-581 — each accepts the raw SDK client (from `self._llm._get_client()`) plus the user prompt, makes the structured-output API call, and returns a `JudgeVerdict`.

- **CRITICAL CD-09 verification:** Before Wave 3 lands, planner verifies the pinned `anthropic` SDK version (`docintel-core/pyproject.toml`) supports `tools=[{strict: true}]` + `tool_choice={"type": "tool", "name": "..."}`, AND the pinned `openai` SDK version supports `response_format={"type": "json_schema", "json_schema": {"strict": true, ...}}`. If either pin is below the required version, Wave 3 bumps the pin first. Per RESEARCH Assumptions A1+A2 (lines 1059-1061), both stable at current pins; planner re-checks.

- **CD-04 / ADP-06 preservation:** The `from tenacity import retry` line + the accompanying explanatory comment (judge.py lines 28-36) STAYS verbatim. The new `_judge_via_anthropic` and `_judge_via_openai` helpers call `client.messages.create(...)` and `client.chat.completions.create(...)` respectively — both SDK call patterns the `check_adapter_wraps.sh` grep gate scans for. The retry is delegated to the adapter layer (`AnthropicAdapter.complete` / `OpenAIAdapter.complete` have it), BUT the new helpers DO NOT call `.complete()` — they call the SDK directly to access tool-use / response_format params not exposed by the protocol. **This is a NEW SDK call site outside the protocol seam.** Planner must decide: (a) extend `LLMClient.complete` protocol with optional `tools=` / `response_format=` params (clean, but expands the protocol surface), OR (b) duplicate the `@retry(...)` decorator on the two new helper functions in `judge.py` (matches the wrap-gate; minimal protocol change). Researcher's Pattern 3 example (lines 532-582) shows option (b) — but does NOT show the `@retry`. **PATTERNS recommends explicitly: the two helpers MUST be wrapped with the same `@retry(...)` decorator pattern from `llm_anthropic.py:102-108` AND `llm_openai.py` (its sibling — same wrap)**. Without the wrap, `scripts/check_adapter_wraps.sh` will flag `judge.py` as missing tenacity coverage (it has the import for ADP-06 but the new helpers don't have `@retry`). Planner confirms during execution.

**Anti-pattern flag:**
- Do NOT change `CrossFamilyJudge.__init__` or `.name` (Phase 2 D-04 contract).
- Do NOT change `make_adapters`'s cross-family dispatch (lines 91-102 of `factory.py`). Phase 6 D-09 is "prompt + parser, NOT dispatch" verbatim.
- Do NOT reuse the heuristic `_SCORE_PATTERN` regex as a fallback — if structured-output fails, raise (tenacity retries handle transient SDK errors; a JSON-shape failure after retries is a genuine bug that should surface, not be papered over). RESEARCH Pitfall 6 (lines 790-800) explicitly warns about regex-fallback cascading retry storms.

---

### `packages/docintel-core/src/docintel_core/adapters/stub/llm.py` (MODIFIED — update `_STUB_REFUSAL` value + re-import `_CHUNK_RE`)

**Analog (in-file):** Existing lines 23-37 (the constants block). The shape stays; values change.

**Existing pattern (lines 23-37, verbatim):**

```python
_STUB_REFUSAL: Final[str] = "[STUB REFUSAL] No evidence found in retrieved context."
"""Canonical refusal string for the no-chunk path (GEN-04).

Phase 6 may replace this constant when formalising the prompt schema and
refusal contract. Phase 2 locks this text so Phase 9 stub-mode faithfulness
tests have a stable, predictable refusal sentinel.
"""

_CHUNK_RE: Final[re.Pattern[str]] = re.compile(r"\[([^\]]+)\]")
"""Module-level compiled regex for extracting [chunk_id] tokens.

Pattern is locked here for forward compatibility: Phase 6 introduces the
formal prompt schema; Phase 9 faithfulness tests rely on the same regex
producing the same citation extractions in stub and real modes.
"""
```

**Deviation notes for Phase 6 (D-12, Pitfall 9):**

**Line-by-line edits:**
- Line 18: `import re` — KEEP only if `_CHUNK_RE` stays in-file (Pitfall 9 alternative). REMOVE if `_CHUNK_RE` is fully delegated to `docintel_generate.parse`.
- Line 23: Update value to `_STUB_REFUSAL: Final[str] = "I cannot answer this question from the retrieved 10-K excerpts."` — the new canonical sentinel from D-11. The exact byte-string MUST match `REFUSAL_PROMPT` in `prompts.py` and `REFUSAL_TEXT_SENTINEL` in `generator.py` (single source of truth across stub + real + generator + Phase 7).
- Lines 24-29: Update docstring to "Canonical refusal sentinel — mirrors `docintel_generate.prompts.REFUSAL_PROMPT` (D-11). Phase 6 promotes this from the Phase 2 placeholder `[STUB REFUSAL]`-bracketed text to the production-quality professional refusal. Stub tests + Phase 9 faithfulness assertions rely on byte-exact match against the canonical sentinel."
- Lines 31-37: Either:
  - (a) DELETE the `_CHUNK_RE` block here and ADD `from docintel_generate.parse import _CHUNK_RE` at the import block (matches D-12 verbatim — "single regex across stub + real"), OR
  - (b) KEEP the in-file `_CHUNK_RE` if Pitfall 9 cycle-avoidance demands `_CHUNK_RE` stays in `docintel-core`. In that case, `docintel_generate.parse._CHUNK_RE = docintel_core.adapters.stub.llm._CHUNK_RE` (re-export from generate → core, NOT core → generate). Planner picks at execution time.

**Per CONTEXT.md D-12 line 109:** "The chunk_id regex `_CHUNK_RE` is moved to `docintel_generate.parse._CHUNK_RE` and re-imported by the stub for consistency." This is the canonical direction; option (a) above. Pitfall 9 flags this as the cycle and recommends an alternative (move `REFUSAL_TEXT_SENTINEL` to core to avoid the inverse cycle). Both `_CHUNK_RE` and `REFUSAL_TEXT_SENTINEL` need a home. Cleanest split:
  - `_CHUNK_RE` → `docintel_generate.parse` (D-12).
  - `REFUSAL_TEXT_SENTINEL` constant → `docintel_core.types` or `docintel_core.adapters.types` (Pitfall 9 alternative).
  - `REFUSAL_PROMPT` in `docintel_generate.prompts` becomes `REFUSAL_PROMPT = REFUSAL_TEXT_SENTINEL` (re-export the same string body for the import-time hash computation).
  - `_STUB_REFUSAL` in `stub/llm.py` becomes `_STUB_REFUSAL = REFUSAL_TEXT_SENTINEL` (re-export).
- The `[STUB ANSWER citing ...]` template at lines 80-84 — UNCHANGED. The `[chunk_id]` bracket markers are already produced; D-12 explicitly confirms "no change needed" here.

**Anti-pattern flag:**
- Do NOT introduce a third sentinel string (e.g., for a "soft refusal" path). Single canonical sentinel across stub + real + zero-chunk + LLM-driven paths is the D-11 invariant.
- Do NOT skip the `_STUB_REFUSAL = ...` line — `_STUB_REFUSAL` is an exported name used by tests; deleting it breaks them.
- Do NOT reformat the `_STUB_REFUSAL` string body during the update. Pitfall 3 (whitespace drift changing hashes) applies even though `_STUB_REFUSAL` itself is not hashed — Phase 9 faithfulness tests `assert resp.text.startswith(_STUB_REFUSAL)` are byte-exact.

---

### `scripts/check_prompt_locality.sh` (NEW — CI grep gate)

**Three-way composite analog:** `scripts/check_adapter_wraps.sh` + `scripts/check_index_wraps.sh` + `scripts/check_ingest_wraps.sh`. All three follow the identical shape:

**Common shape (verbatim from `check_adapter_wraps.sh`, 41 lines):**

```bash
#!/usr/bin/env bash
# CI grep gate: every real adapter file that contains an SDK call
# must also import tenacity (ADP-06, D-18).
#
# Usage:
#   scripts/check_adapter_wraps.sh [SCAN_DIR]
#
# SCAN_DIR defaults to packages/docintel-core/src/docintel_core/adapters/real
# Pass a different directory (e.g., tests/fixtures/) to test the negative case.
#
# SDK_PATTERNS: grep-extended regex matching the four SDK call sites in this wave:
#   .messages.create    — Anthropic client
#   chat.completions.create — OpenAI client
#   .encode(            — SentenceTransformer
#   .predict(           — CrossEncoder
#
# If future waves add new SDK call sites in real/, update SDK_PATTERNS here.
#
# Exit codes:
#   0 — all files with SDK calls also import tenacity (or no SDK calls found)
#   1 — at least one file has SDK calls but no 'from tenacity import'
set -euo pipefail

REAL_ADAPTERS="${1:-packages/docintel-core/src/docintel_core/adapters/real}"
PROBLEM=0

SDK_PATTERNS='\.messages\.create\|chat\.completions\.create\|\.encode(\|\.predict('

for f in $(grep -rl "$SDK_PATTERNS" "$REAL_ADAPTERS" --include="*.py" --include="*.py.example" 2>/dev/null); do
    if ! grep -q "from tenacity import" "$f"; then
        echo "FAIL: $f contains SDK call(s) but no 'from tenacity import'"
        PROBLEM=1
    fi
done

if [ "$PROBLEM" -eq 0 ]; then
    echo "OK: all real adapter files with SDK calls have tenacity imports"
fi

exit "$PROBLEM"
```

**Deviation notes for Phase 6 (D-04, D-05, D-06, RESEARCH Pattern 4 lines 586-668):**

- Header docstring updated for Phase 6 / GEN-01 (mirror the existing header structure):
  - Purpose: "Fails if a Python file outside the allowlist contains an inline prompt-like string literal (GEN-01 — Phase 6 D-04)."
  - Usage line: `scripts/check_prompt_locality.sh [SCAN_DIR]` (SCAN_DIR defaults to `packages/`).
  - Allowlist enumeration: `packages/docintel-generate/src/docintel_generate/prompts.py`, `packages/docintel-generate/src/docintel_generate/parse.py`, `tests/**`, `**/conftest.py`, `**/test_*.py`, `packages/docintel-core/src/docintel_core/adapters/stub/llm.py`.
  - Escape hatch: per-line `# noqa: prompt-locality` (D-05).
- Body shape per RESEARCH Pattern 4 lines 621-667:
  - `set -euo pipefail` (matches all three analogs).
  - `SCAN_DIR="${1:-packages/}"`.
  - `NAME_PATTERN='_[A-Z_]*PROMPT[A-Z_]*\b|_[A-Z_]*INSTRUCTION[A-Z_]*\b|_[A-Z_]*SYSTEM_PROMPT\b'` — identifier-based detection.
  - `PHRASE_PATTERN='\b(You are|Based on the|<context>|<chunks>|cite|grounded|chunk_id)\b'` — content-based detection (with `[[ ${#match} -lt 80 ]] && continue` length filter to reduce false positives).
  - Two-loop structure: scan for `NAME_PATTERN` first, then `PHRASE_PATTERN`, both with `# noqa: prompt-locality` per-line escape via `if grep -q '# noqa: prompt-locality' <<<"$(sed -n "${lineno}p" "$file")"; then continue; fi`.
  - Allowlist exclusion: `EXCLUDES=("--exclude-dir=tests" "--exclude=conftest.py" "--exclude=test_*.py")` + `--exclude=` per allowlisted basename.
  - Exit code: `exit "$PROBLEM"` (0 = pass, 1 = fail). Same as three analogs.
- File must be executable: `chmod +x scripts/check_prompt_locality.sh` — verify with `git update-index --chmod=+x scripts/check_prompt_locality.sh` if needed.

**Anti-pattern flag:**
- Do NOT add a Python-AST-based scan. Bash + grep is the established pattern; Python AST would (a) require uv-run-Python in CI, increasing wall-clock by ~5s, and (b) inconsistent shape across the 4 grep gates (DRY-of-policy). RESEARCH Don't Hand-Roll table line 696 calls this out.
- Do NOT scan `data/`, `.planning/`, or `*.md` paths — the gate is scoped to Python source (`--include='*.py'`).
- Do NOT auto-fix violations (no `--fix` flag). The gate fails CI; the developer fixes the file or adds `# noqa: prompt-locality`.

---

### `.github/workflows/ci.yml` (MODIFIED — add prompt-locality step)

**Analog (in-file):** Lines 89-106 (the three existing wrap-grep-gate steps).

**Existing pattern (verbatim from lines 89-106):**

```yaml
      - name: Adapter wrap grep gate (ADP-06)
        # Every real adapter file with an SDK call must import tenacity.
        # Script exits non-zero if any file under packages/docintel-core/src/docintel_core/adapters/real/
        # contains an SDK call pattern but no tenacity import (D-18 structural enforcement).
        run: bash scripts/check_adapter_wraps.sh

      - name: Ingest wrap grep gate (D-18)
        # Every docintel_ingest file with a sec-edgar-downloader call must import tenacity.
        # Script exits non-zero if any file under packages/docintel-ingest/src/docintel_ingest/
        # contains a sec-edgar-downloader SDK call pattern but no tenacity import
        # (D-18 structural enforcement; ADP-06 analog for Phase 3 / ING-*).
        run: bash scripts/check_ingest_wraps.sh

      - name: Index wrap grep gate (D-21)
        # Every adapters/real/*.py file with a qdrant_client.* call must
        # import tenacity. Structurally enforces no-silent-retries on the
        # Qdrant HTTP path (Phase 4 IDX-* / Pitfall 6 dep drift defense).
        run: bash scripts/check_index_wraps.sh
```

**Deviation notes for Phase 6 (D-06, RESEARCH Pattern 4 doc-cross-references):**

- Add the NEW step IMMEDIATELY AFTER the existing three (after line 106):

```yaml
      - name: Check prompt locality (GEN-01)
        # Every prompt-like string literal must live in
        # packages/docintel-generate/src/docintel_generate/prompts.py
        # (the canonical home). Script exits non-zero if any .py file under
        # packages/ contains an inline prompt outside the allowlist
        # (Phase 6 D-04 structural enforcement of GEN-01).
        run: bash scripts/check_prompt_locality.sh
```

- Placement rationale: after the three existing wrap-gates so all four grep-gates form a single contiguous block; reviewers see "all the grep-gates" together. Comment shape mirrors the three existing comments verbatim (purpose + script behavior + requirement ID).
- The step runs in stub mode (no env vars required) — matches `check_adapter_wraps.sh` / `check_index_wraps.sh` / `check_ingest_wraps.sh`. No `env:` block needed.
- No matrix expansion needed — runs on the existing `lint-and-test` job (per the three analogs).

**Anti-pattern flag:**
- Do NOT add the step to the `real-index-build` workflow_dispatch job — that job is for real-mode index builds; the prompt-locality gate is a code-shape gate, runs on every PR.
- Do NOT skip the comment block above the `run:` line — the existing three steps have purpose-comments; consistency matters for reviewers grepping the workflow.

---

### Tests scaffolds (NEW — Wave 0 xfail scaffolds, flipped in Waves 1-3)

**Common analog for the xfail scaffold pattern:** Phase 5's `tests/test_retrieved_chunk_schema.py:1-50` + `tests/test_rrf_fuse.py:1-25`.

**Common xfail-scaffold pattern (verbatim from `test_retrieved_chunk_schema.py:1-32`):**

```python
"""Plan 05-01 Wave 0 xfail scaffolds for RetrievedChunk (RET-04, D-03, CD-02).

Covers VALIDATION.md rows 05-01-05 and 05-01-06 — the Phase 5 → Phase 6/7
public contract:

* test_retrieved_chunk_required_fields — the seven D-03 fields are all
  accepted (chunk_id, text, score, ticker, fiscal_year, item_code,
  char_span_in_section).
...

All four tests are xfail-strict-marked because ``RetrievedChunk`` does not yet
live in ``docintel_core.types`` at Wave 0 (per CD-02, the model home is
``docintel_core.types``, NOT ``docintel-retrieve.types``). The in-function
``from docintel_core.types import RetrievedChunk`` raises ImportError →
pytest counts this as the expected failure under xfail(strict=True). Plan 05-02
adds ``RetrievedChunk`` to ``docintel_core.types`` and removes these xfail
markers.

Analogs:
* ``tests/test_index_manifest.py`` — Pydantic-schema test patterns.
* ``packages/docintel-core/src/docintel_core/types.py`` ``Chunk`` class
  (lines 104-144) — same Pydantic v2 BaseModel + ConfigDict shape.
* 05-PATTERNS.md ``tests/test_retrieved_chunk_schema.py`` section.
"""
```

**Phase 6 test files — concrete analog assignments:**

| Phase 6 test file | Analog | Pattern excerpt source | Wave flip |
|-------------------|--------|------------------------|-----------|
| `tests/test_prompt_locality.py` | `tests/test_index_wraps_gate.py` (full file, 84 lines) | Subprocess invocation of bash script + positive-fixture + negative-fixture pattern at lines 33-84 | W0 → flip in W4 (after `prompts.py` ships in W1 and the script ships in W0, the positive case passes immediately; the negative case needs a `tests/fixtures/inline_prompt/` fixture parallel to `tests/fixtures/missing_tenacity/`) |
| `tests/test_prompt_version_hash.py` | `tests/test_rrf_fuse.py:test_rrf_k_constant` (lines 72-74) for module-constant assertion + `tests/test_retrieved_chunk_schema.py` for Pydantic-shape pattern | `from docintel_generate.prompts import PROMPT_VERSION_HASH; assert isinstance(PROMPT_VERSION_HASH, str); assert len(PROMPT_VERSION_HASH) == 12; assert PROMPT_VERSION_HASH.isalnum()` + sensitivity test (mutate the source string, re-import, assert hash changes) | W0 → flip in W1 |
| `tests/test_generator_stub_determinism.py` | `tests/test_retriever_search.py:test_retriever_returns_top_k` (lines 46-56) | `r = make_generator(Settings(llm_provider="stub")); results = [r.generate("revenue growth", k=5) for _ in range(3)]; assert all(r.text == results[0].text for r in results)` | W0 → flip in W2 |
| `tests/test_generator_refusal.py` | `tests/test_retriever_search.py:test_zero_candidates` (CD-07 zero-candidate path) | Construct a `Generator` whose retriever returns `[]`; assert `result.refused == True`, `result.text == REFUSAL_TEXT_SENTINEL`, `result.completion is None`. Second test: feed a stubbed completion that emits the sentinel verbatim; assert `result.refused == True`. | W0 → flip in W2 |
| `tests/test_make_generator.py` | `tests/test_make_retriever.py` (full file, lines 1-110) | Three tests verbatim from analog: `test_make_generator_stub` (factory dispatch); `test_make_generator_returns_composed` (Generator + Retriever both present); `test_factory_lazy_imports_generator_module` (D-12 lazy-import gate — sys.modules check) | W0 → flip in W2 |
| `tests/test_judge_structured_output.py` | `tests/test_reranker_canary.py:test_reranker_canary_real_mode` (lines 44-50 — `@pytest.mark.real` + nested xfail-until-Wave-N) | `@pytest.mark.real` outer + verifies a JudgeVerdict is returned from `make_adapters(Settings(llm_provider="real", llm_real_provider="anthropic")).judge.judge(prediction="apple grew rev", reference=["Apple revenue grew."], rubric="")` with all four fields populated | W0 → flip in W3 |

**xfail marker discipline (from `test_retrieved_chunk_schema.py`):**
```python
@pytest.mark.xfail(strict=True, reason="Wave 1 — docintel_generate.prompts not yet implemented")
def test_prompt_version_hash_is_12_char_hex() -> None:
    from docintel_generate.prompts import PROMPT_VERSION_HASH

    assert len(PROMPT_VERSION_HASH) == 12
    assert all(c in "0123456789abcdef" for c in PROMPT_VERSION_HASH)
```

**Deviation notes for Phase 6:**
- Every xfail test gets a `reason="Wave N — <thing> not yet implemented"` string matching the Phase 5 convention (so the W4 sweep can grep for the strings).
- Module-level docstring per test file mirrors Phase 5: phase + requirement ID + Wave 0 / Plan source + analog file + flip wave.
- For `test_judge_structured_output.py`: marker order is `@pytest.mark.real` (OUTER) + `@pytest.mark.xfail(strict=True, reason="Wave 3 — judge structured-output not yet wired")` (INNER) — see Phase 5 `test_reranker_canary.py:44-50` rationale (pytest's marker-collection evaluates `not real` deselection BEFORE applying xfail). Without `pytestmark` at module-level (which would gate the whole file and break stub-CI).

**Anti-pattern flag:**
- Do NOT add `pytestmark = pytest.mark.real` at module top of any Phase 6 test file. Phase 5 explicitly avoids this pattern (test_reranker_canary.py docstring lines 52-65) — the file would be deselected on every PR's default `lint-and-test` run.
- Do NOT use `@pytest.mark.skip` for "not yet implemented" — use `xfail(strict=True)` so the test FAILS the moment the implementation ships and someone forgets to remove the marker (positive feedback signal, not silent skip).

---

### Docs reconciliation (5 files MODIFIED — path-reference updates per D-02)

**Analog pattern:** None — these are doc-file find-and-replace edits. The "code excerpt" is just the line-context.

| File | Line | Existing text | New text |
|------|------|---------------|----------|
| `CLAUDE.md` | 27 | `- **All prompts live in \`src/docintel/generation/prompts.py\`**, versioned with a hash. Grep for inline string-literal prompts must return zero matches.` | `- **All prompts live in \`packages/docintel-generate/src/docintel_generate/prompts.py\`**, versioned with a hash. Grep for inline string-literal prompts must return zero matches.` |
| `.planning/PROJECT.md` | 31 | `- [ ] **Phase 6** Generation: prompts module (\`src/docintel/generation/prompts.py\`) with version hashes; all LLM calls wrapped in tenacity retry with \`before_sleep_log\`.` | `- [ ] **Phase 6** Generation: prompts module (\`packages/docintel-generate/src/docintel_generate/prompts.py\`) with version hashes; all LLM calls wrapped in tenacity retry with \`before_sleep_log\`.` |
| `.planning/PROJECT.md` | 66 | `- **Prompts are versioned**: all prompts live in \`src/docintel/generation/prompts.py\` with a hash. Grep for inline string-literal prompts must return zero matches.` | `- **Prompts are versioned**: all prompts live in \`packages/docintel-generate/src/docintel_generate/prompts.py\` with a hash. Grep for inline string-literal prompts must return zero matches.` |
| `.planning/REQUIREMENTS.md` | 56 | `- [ ] **GEN-01**: All prompts live in \`src/docintel/generation/prompts.py\`; grep for inline string-literal prompts outside this file returns zero matches (CI gate)` | `- [ ] **GEN-01**: All prompts live in \`packages/docintel-generate/src/docintel_generate/prompts.py\`; grep for inline string-literal prompts outside this file returns zero matches (CI gate)` |
| `.planning/ROADMAP.md` | 210 | `**Provides:** \`src/docintel/generation/prompts.py\` with versioned prompts, generator wrapping \`LLMClient\`, refusal path` | `**Provides:** \`packages/docintel-generate/src/docintel_generate/prompts.py\` with versioned prompts, generator wrapping \`LLMClient\`, refusal path` |
| `.planning/config.json` | 15 | `    "prompt_home": "src/docintel/generation/prompts.py",` | `    "prompt_home": "packages/docintel-generate/src/docintel_generate/prompts.py",` |

**Deviation notes for Phase 6 (D-02):**
- All five files are doc-only updates (no code changes). Group into a single commit (planner picks the wave — researcher recommends Wave 0 so the doc-truth aligns with the new package skeleton landing in the same wave).
- Each find-and-replace is BYTE-EXACT — the path string `src/docintel/generation/prompts.py` becomes `packages/docintel-generate/src/docintel_generate/prompts.py` everywhere it appears, no other text changes.
- A `git grep "src/docintel/generation/prompts.py"` after the edit MUST return zero matches across the tracked repo (excluding history). Add this as a verification step in the Wave 0 plan.

**Anti-pattern flag:**
- Do NOT rewrite the surrounding sentences for "improved clarity" while doing the path update — the rest of the line content is locked.
- Do NOT add the new path to documents that don't already mention the old path (e.g., `STATE.md`, individual phase CONTEXT.md files). The D-02 reconciliation list is exactly these five files.

---

## Shared Patterns (Cross-Cutting)

### Module-level `structlog` logger pattern

**Source:** `packages/docintel-retrieve/src/docintel_retrieve/retriever.py:68` + `packages/docintel-core/src/docintel_core/adapters/real/llm_anthropic.py:44-45` (two-logger SP-3 variant when tenacity is present).

**Apply to:** `packages/docintel-generate/src/docintel_generate/generator.py` (single-logger; no tenacity → no `_retry_log`).

**Single-logger pattern (Phase 6 default):**
```python
import structlog

log = structlog.stdlib.get_logger(__name__)
```

Comment per `retriever.py:65-67`: `# Single structlog logger — no tenacity in this module (CD-04), so the SP-3 two-logger pattern (_retry_log + log) is intentionally NOT applied; the dead _retry_log placeholder would be misleading here.`

### `from __future__ import annotations` discipline

**Source:** Every `docintel_*` module (e.g., `retriever.py:50`, `factory.py:29`, `judge.py:22`).

**Apply to:** All NEW `.py` files in Phase 6 (`prompts.py`, `parse.py`, `generator.py`).

**Excerpt:**
```python
from __future__ import annotations
```

First non-docstring line. Enables PEP 563 string-typed annotations + cleaner `from typing import` blocks.

### `ConfigDict(extra="forbid", frozen=True)` for shared contracts

**Source:** `RetrievedChunk` at `types.py:180`.

**Apply to:** `GenerationResult` at `types.py` (NEW).

**Excerpt:**
```python
model_config = ConfigDict(extra="forbid", frozen=True)
```

`extra="forbid"` raises on construction with unknown fields (defense against schema drift); `frozen=True` raises on post-construction mutation (defense against shared-list corruption in downstream phases).

### CI grep-gate test pattern (positive + negative fixture)

**Source:** `tests/test_index_wraps_gate.py` (full file, 84 lines).

**Apply to:** `tests/test_prompt_locality.py`.

**Excerpt — test_grep_gate_catches_unwrapped (lines 33-55):**
```python
def test_grep_gate_catches_unwrapped() -> None:
    """..."""
    assert _GATE_SCRIPT.is_file(), f"gate script missing: {_GATE_SCRIPT}"
    result = subprocess.run(
        ["bash", str(_GATE_SCRIPT), str(_FIXTURE_DIR)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "index grep gate did not catch the unwrapped qdrant_client fixture. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
```

**Deviation for Phase 6:** Negative fixture is `tests/fixtures/inline_prompt/offender.py` containing a triple-quoted string literal matching `PHRASE_PATTERN` AND `len > 80` (e.g., `_INLINE_PROMPT = """You are a helpful assistant. Based on the chunks below, cite using bracketed chunk_id markers..."""`); positive fixture is a tmp_path file containing one of the allowlisted strings BUT with `# noqa: prompt-locality` appended (verifies the escape hatch).

### `Final[...]` type-annotated module constants

**Source:** `retriever.py:71-105` (`TOP_N_PER_RETRIEVER`, `TOP_M_RERANK`, `TOP_K_FINAL`, `QUERY_TOKEN_HARD_CAP`, `_CLAUDE_MD_HARD_GATE`).

**Apply to:** `prompts.py` (`SYNTHESIS_PROMPT`, `REFUSAL_PROMPT`, `JUDGE_PROMPT`, `_SYNTHESIS_HASH`, `_REFUSAL_HASH`, `_JUDGE_HASH`, `PROMPT_VERSION_HASH`) + `parse.py` (`_CHUNK_RE`, optional `REFUSAL_TEXT_SENTINEL`).

**Excerpt:**
```python
from typing import Final

TOP_K_FINAL: Final[int] = 5
"""D-06 — top-5 reranked chunks returned to the caller. ..."""
```

mypy `--strict` verifies `Final[...]` — the constants cannot be reassigned in another module.

### Lazy SDK init via `_get_client()` (Phase 6 only TOUCHES, does not create)

**Source:** `llm_anthropic.py:85-95` (`AnthropicAdapter._get_client`).

**Apply to:** Phase 6's `judge.py` migration accesses `self._llm._get_client()` to reach the raw SDK client for the structured-output call. The pattern is unchanged; Phase 6 just consumes it.

**Excerpt:**
```python
def _get_client(self) -> Any:
    """Lazy SDK construction. Raises if API key is missing at first use."""
    if self._client is not None:
        return self._client
    import anthropic  # lazy module import — only executed when real .complete() runs

    if self._cfg.anthropic_api_key is None:
        raise ValueError("DOCINTEL_ANTHROPIC_API_KEY is required when llm_provider='real'")
    self._client = anthropic.Anthropic(api_key=self._cfg.anthropic_api_key.get_secret_value())
    return self._client
```

This is what Phase 6 D-09's `_judge_via_anthropic(self._llm._get_client(), user_prompt)` dispatches through. First call to `.judge()` triggers SDK init; subsequent calls reuse the cached client. Verified working at commit `9ec4d36` (per CLAUDE.md / state.md).

---

## No Analog Found

None. Every Phase 6 file has at least a role-match analog. Per the RESEARCH "Key insight" (line 698): "Phase 6 is composition-heavy and net-new-logic-light. Almost everything Phase 6 needs already exists in some form: the LLM call surface is shipped, the retrieval seam is shipped, the citation regex is shipped, the cross-family judge wiring is shipped."

The two areas with no perfect analog (only role-match):
- **`prompts.py`** — no other file in the codebase carries module-level prompt constants with import-time hashes. The closest patterns are `Final[int]` constants in `retriever.py` (for the constant-shape pattern) and the `_STUB_REFUSAL` / `_CHUNK_RE` block in `stub/llm.py` (for the sentinel-string-with-docstring pattern). Phase 6 composes both.
- **`generator.py`'s structured-output judge dispatch via `isinstance(self._llm, AnthropicAdapter)`** — Phase 6 introduces a NEW SDK call site that doesn't go through `LLMClient.complete()`. The cleanest analog is `llm_anthropic.py`'s `@retry` + `client.messages.create` pattern, but planner must decide between (a) extending the protocol or (b) duplicating the `@retry` decorator on the two new helpers (PATTERNS recommends (b) per the CD-04 ADP-06 wrap-gate concern flagged above).

---

## Metadata

**Analog search scope:**
- `packages/docintel-core/src/docintel_core/` (entire core package)
- `packages/docintel-retrieve/src/docintel_retrieve/` (entire retrieve package — primary Phase 6 analog)
- `packages/docintel-index/` (pyproject + module conventions)
- `packages/docintel-ingest/` (pyproject)
- `scripts/check_*.sh` (all four when complete; three currently)
- `tests/test_*.py` (xfail scaffolds, factory tests, grep-gate tests, integration tests)
- `.github/workflows/ci.yml` (CI step shape)
- `CLAUDE.md` + `.planning/{PROJECT,REQUIREMENTS,ROADMAP,STATE}.md` + `.planning/config.json` (doc-reconciliation targets)
- `.planning/phases/05-retrieval-hybrid-rerank/05-PATTERNS.md` (output-schema reference)

**Files scanned (read fully):** 11 source + 5 test + 3 script + 6 doc + 2 prior context = 27 files.

**Pattern extraction date:** 2026-05-15.

**Wave assignment summary:**
- Wave 0 (parallel): `pyproject.toml` + `__init__.py` (skeleton) + `py.typed` + `scripts/check_prompt_locality.sh` + 6 test scaffolds + 5 doc-path updates.
- Wave 1: `prompts.py` (3 constants + 4 hashes + `build_judge_user_prompt`) + `parse.py` (`_CHUNK_RE`). Flip `test_prompt_locality.py` (positive case) + `test_prompt_version_hash.py`.
- Wave 2: `generator.py` (`Generator` class) + `make_generator(cfg)` in `factory.py` + `GenerationResult` in `types.py` + extend `__init__.py` re-exports. Flip `test_generator_stub_determinism.py` + `test_generator_refusal.py` + `test_make_generator.py`.
- Wave 3: `adapters/real/judge.py` (remove placeholder + structured-output dispatch) + `adapters/stub/llm.py` (sentinel value + `_CHUNK_RE` re-import). Flip `test_judge_structured_output.py`.
- Wave 4: `.github/workflows/ci.yml` step + xfail-removal sweep + real-mode hero question test + Decision-Coverage Audit + phase gate.
