"""Factory that constructs an AdapterBundle + IndexStoreBundle from Settings.

The ONLY place in the codebase that instantiates concrete adapters.
Lazy imports inside the ``real`` branch keep stub-mode CI free of
torch / sentence-transformers / SDK import cost (D-12).

stub mode: deterministic stubs, no external deps.
real mode: lazy-imports torch + SDK deps; constructs real adapters per
           cfg.llm_real_provider; judge always uses the complement provider (D-04).

Phase 4 amendment (D-03): ``make_index_stores(cfg)`` returns an
``IndexStoreBundle`` of dense + sparse stores. Stub mode pairs
``NumpyDenseStore`` + ``Bm25sStore`` (in-process, no network). Real mode pairs
``QdrantDenseStore`` + ``Bm25sStore`` (BM25 is unified across modes per D-07).
The qdrant_client import lives lazily inside the real branch (D-12) — stub-
mode CI never pays the import cost.

Phase 5 amendment (D-04): ``make_retriever(cfg)`` is the third sibling factory
alongside ``make_adapters`` and ``make_index_stores``. It composes both
bundles and constructs ``docintel_retrieve.retriever.Retriever``. The
Retriever import lives INSIDE the function body (Pattern S5 lazy-import
discipline) — module-load of ``docintel_core.adapters.factory`` stays
cheap and does NOT pull in ``docintel_retrieve`` transitively. The
return-type annotation uses a string forward reference (``-> "Retriever"``)
to keep that discipline pure: no top-level (even TYPE_CHECKING) import
is required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docintel_core.adapters.stub.embedder import StubEmbedder
from docintel_core.adapters.stub.reranker import StubReranker
from docintel_core.adapters.types import AdapterBundle, IndexStoreBundle

# TYPE_CHECKING guard: these imports run only under mypy/pyright, never at runtime.
# The real adapter modules (Wave 4) do not exist yet; this guard keeps mypy happy
# for the type annotations in make_adapters() without importing non-existent modules.
#
# Phase 5 D-04: ``Retriever`` is added here under TYPE_CHECKING so mypy --strict
# can resolve the ``-> "Retriever"`` string forward reference annotation on
# ``make_retriever``. At runtime ``Retriever`` is imported INSIDE the
# ``make_retriever`` function body (Pattern S5 lazy-import discipline) — the
# TYPE_CHECKING block is the type-checker's view only and does NOT cause
# ``docintel_retrieve`` to be loaded at module import time
# (``tests/test_make_retriever.py::test_factory_lazy_imports_retriever_module``
# enforces the runtime gate).
if TYPE_CHECKING:
    from docintel_retrieve.retriever import Retriever

    from docintel_core.adapters.real.judge import CrossFamilyJudge
    from docintel_core.adapters.real.llm_anthropic import AnthropicAdapter
    from docintel_core.adapters.real.llm_openai import OpenAIAdapter
    from docintel_core.config import Settings


def make_adapters(cfg: Settings) -> AdapterBundle:
    """Construct and return an AdapterBundle keyed on cfg.llm_provider.

    stub mode: returns deterministic stub adapters with no external deps.
    real mode: lazily imports torch + SDK modules; dispatches per
               cfg.llm_real_provider; judge always uses the complement
               provider to avoid circular-judge bias (D-04).

    Args:
        cfg: Settings instance with llm_provider (and optionally llm_real_provider) set.

    Returns:
        AdapterBundle with embedder, reranker, llm, and judge adapters.
    """
    if cfg.llm_provider == "stub":
        from docintel_core.adapters.stub.judge import StubLLMJudge
        from docintel_core.adapters.stub.llm import StubLLMClient

        return AdapterBundle(
            embedder=StubEmbedder(),
            reranker=StubReranker(),
            llm=StubLLMClient(),
            judge=StubLLMJudge(),
        )

    # Real branch — lazy imports keep stub-mode CI free of SDK import cost (D-12).
    # These imports will raise ImportError until Wave 4 ships the real adapter modules.
    from docintel_core.adapters.real.embedder_bge import BGEEmbedder
    from docintel_core.adapters.real.judge import CrossFamilyJudge
    from docintel_core.adapters.real.llm_anthropic import AnthropicAdapter
    from docintel_core.adapters.real.llm_openai import OpenAIAdapter
    from docintel_core.adapters.real.reranker_bge import BGEReranker

    # Cross-family judge dispatch (D-04): generator and judge always use DIFFERENT providers.
    # Avoids circular-judge bias where a model rubber-stamps its own output.
    llm: AnthropicAdapter | OpenAIAdapter
    judge_inner: OpenAIAdapter | AnthropicAdapter
    if cfg.llm_real_provider == "anthropic":
        llm = AnthropicAdapter(cfg)
        judge_inner = OpenAIAdapter(cfg)
    else:
        llm = OpenAIAdapter(cfg)
        judge_inner = AnthropicAdapter(cfg)

    judge: CrossFamilyJudge = CrossFamilyJudge(judge_inner, cfg)

    return AdapterBundle(
        embedder=BGEEmbedder(cfg),
        reranker=BGEReranker(cfg),
        llm=llm,
        judge=judge,
    )


def make_index_stores(cfg: Settings) -> IndexStoreBundle:
    """Construct and return an IndexStoreBundle keyed on cfg.llm_provider.

    Phase 4 D-03 dispatch:
        * stub mode → ``NumpyDenseStore`` + ``Bm25sStore`` (in-process, no network).
        * real mode → ``QdrantDenseStore`` + ``Bm25sStore`` (BM25 is unified
          across modes per D-07 — there is no "tiered" BM25).

    Lazy-import discipline (D-12): the qdrant_client SDK is imported only
    inside the real branch. Stub-mode CI never pays the qdrant_client import
    cost. The Bm25sStore import is also lazy (mirrors the stub-branch
    NumpyDenseStore import) — same Phase 2 ``make_adapters`` pattern.

    Args:
        cfg: Settings instance with llm_provider set.

    Returns:
        IndexStoreBundle with ``dense`` (NumpyDenseStore | QdrantDenseStore)
        and ``bm25`` (Bm25sStore) adapters. Phase 10's eval manifest header
        reads ``bundle.dense.name`` and ``bundle.bm25.name`` from this bundle.
    """
    if cfg.llm_provider == "stub":
        from docintel_core.adapters.real.bm25s_store import Bm25sStore
        from docintel_core.adapters.real.numpy_dense import NumpyDenseStore

        return IndexStoreBundle(
            dense=NumpyDenseStore(cfg),
            bm25=Bm25sStore(cfg),
        )

    # Real branch — lazy-import the qdrant_client-backed dense store (D-12).
    # BM25 is unified across modes per D-07 (single bm25s implementation).
    from docintel_core.adapters.real.bm25s_store import Bm25sStore
    from docintel_core.adapters.real.qdrant_dense import QdrantDenseStore

    return IndexStoreBundle(
        dense=QdrantDenseStore(cfg),
        bm25=Bm25sStore(cfg),
    )


def make_retriever(cfg: Settings) -> Retriever:
    """Construct and return a Retriever composed of adapter + store bundles.

    Phase 5 D-04: third sibling factory alongside ``make_adapters(cfg)`` and
    ``make_index_stores(cfg)``. Calls both internally and constructs
    ``Retriever(bundle, stores, cfg)``. Lives in ``docintel_core.adapters.factory``
    (NOT in ``docintel-retrieve``) so the import direction matches every prior
    phase: ``docintel-retrieve`` imports from ``docintel-core``, never the reverse.

    Lazy-import discipline (D-12 + Pattern S5): ``from
    docintel_retrieve.retriever import Retriever`` lives INSIDE the function
    body so ``import docintel_core.adapters.factory`` stays cheap. This is the
    same lazy-import pattern that ``make_index_stores`` uses for
    ``Bm25sStore`` / ``NumpyDenseStore`` and that ``make_adapters`` uses for
    the real-mode SDK imports. ``tests/test_make_retriever.py::
    test_factory_lazy_imports_retriever_module`` enforces the gate.

    The return-type annotation uses a string forward reference
    (``-> "Retriever"``) so no top-level (even TYPE_CHECKING) import of
    ``Retriever`` is required. mypy resolves the string by reading the
    function body's import.

    CD-01: eager-load. Constructing the Retriever loads the
    chunk_id → Chunk map (~600 ms one-time on the 6,053-chunk corpus)
    AND warms the index-store lazy-load paths (~100 ms via the warm-up
    queries inside ``Retriever.__init__``). The caller pays this cost
    once per process; Phase 13's FastAPI lru-caches the result so
    subsequent requests reuse the warm instance.

    CD-08: NO factory-level cache — Phase 13 lru-caches at the FastAPI
    dependency layer; Phase 10 eval harness constructs once per run;
    Phase 11 ablations construct directly via ``Retriever(bundle, stores, cfg)``
    so they can inject null adapters (D-08). Mirrors the
    ``make_adapters(cfg)`` precedent of no factory cache.

    Args:
        cfg: Settings instance with ``llm_provider`` set (and ``data_dir``
            + ``index_dir`` consulted by the Retriever's eager chunk-map
            load + MANIFEST cardinality check).

    Returns:
        Retriever ready to call ``.search(query, k)``. The instance holds
        ``AdapterBundle`` + ``IndexStoreBundle`` references; subsequent
        ``.search`` calls do not re-trigger factory dispatch.
    """
    # Lazy import — keeps `import docintel_core.adapters.factory` cheap
    # (D-12 + Pattern S5). The test_factory_lazy_imports_retriever_module
    # gate fails if this import is hoisted to module scope.
    from docintel_retrieve.retriever import Retriever

    bundle = make_adapters(cfg)
    stores = make_index_stores(cfg)
    return Retriever(bundle=bundle, stores=stores, cfg=cfg)
