"""Tests for docintel_core.adapters — Protocol contract + stub determinism.

Locks ADP-01..ADP-07 invariants in stub mode. Real-adapter tests
(requiring API keys) are decorated with @pytest.mark.skipif and
excluded from default CI runs. All tests are marked xfail until
Wave 1-4 land the production adapter code.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest


def _can_import(*names: str) -> bool:
    """Return True iff every listed module name is importable.

    Used by @pytest.mark.skipif to gate real-adapter tests on the presence
    of SDK dependencies (anthropic, openai) that land in Wave 5's lockfile.
    """
    for name in names:
        try:
            importlib.import_module(name)
        except ImportError:
            return False
    return True


# ---------------------------------------------------------------------------
# xfail marker applied to all tests in this file — waves 1-4 remove them
# ---------------------------------------------------------------------------
_XFAIL = pytest.mark.xfail(
    raises=(ImportError, AttributeError, NotImplementedError, AssertionError),
    strict=False,
    reason="awaits Wave 1-4 — see 02-VALIDATION.md",
)


# ---------------------------------------------------------------------------
# ADP-01: Embedder — shape + determinism
# ---------------------------------------------------------------------------


def test_stub_embedder_shape(stub_bundle) -> None:
    """StubEmbedder.embed(['a','b']) returns np.ndarray shape (2, 384)."""
    import numpy as np

    result = stub_bundle.embedder.embed(["hello", "world"])
    assert isinstance(result, np.ndarray)
    assert result.shape == (2, 384)


def test_stub_embedder_deterministic(stub_bundle) -> None:
    """Same text input always yields the identical 384-dim unit vector."""
    r1 = stub_bundle.embedder.embed(["same text here"])
    r2 = stub_bundle.embedder.embed(["same text here"])
    assert (r1 == r2).all()


# ---------------------------------------------------------------------------
# ADP-02: Reranker — sorted output + determinism
# ---------------------------------------------------------------------------


def test_stub_reranker_sorted(stub_bundle) -> None:
    """StubReranker.rerank returns list[RerankedDoc] sorted descending by score."""
    docs = ["revenue grew 20%", "net loss widened", "R&D investment doubled"]
    results = stub_bundle.reranker.rerank("revenue growth", docs)
    assert len(results) == 3
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True), "scores must be descending"
    # Each result has the required attributes
    for r in results:
        assert hasattr(r, "doc_id")
        assert hasattr(r, "text")
        assert hasattr(r, "score")
        assert hasattr(r, "original_rank")


def test_stub_reranker_deterministic(stub_bundle) -> None:
    """Same (query, docs) input always yields identical ranking."""
    docs = ["alpha document", "beta document", "gamma document"]
    r1 = stub_bundle.reranker.rerank("alpha query", docs)
    r2 = stub_bundle.reranker.rerank("alpha query", docs)
    assert [x.doc_id for x in r1] == [x.doc_id for x in r2]
    assert [x.score for x in r1] == [x.score for x in r2]


# ---------------------------------------------------------------------------
# ADP-03: LLMClient — complete + refusal
# ---------------------------------------------------------------------------


def test_stub_llm_complete(stub_bundle) -> None:
    """StubLLMClient.complete returns CompletionResponse with non-empty text and model='stub'."""
    prompt = "Context: [chunk_1] Revenue was $10B. [chunk_2] Margins improved.\n\nQuestion: What happened?"
    response = stub_bundle.llm.complete(prompt)
    assert hasattr(response, "text")
    assert isinstance(response.text, str)
    assert len(response.text) > 0
    assert response.model == "stub"
    assert response.cost_usd == 0.0
    assert response.latency_ms == 0.0
    assert hasattr(response, "usage")
    assert hasattr(response.usage, "prompt_tokens")
    assert hasattr(response.usage, "completion_tokens")


def test_stub_llm_refusal(stub_bundle) -> None:
    """StubLLMClient returns canonical refusal text when prompt contains no chunk IDs.

    Phase 6 D-11 + Plan 06-05: ``_STUB_REFUSAL`` now byte-equals
    ``REFUSAL_TEXT_SENTINEL`` from ``docintel_core.types`` (the canonical
    refusal sentinel ``"I cannot answer this question from the retrieved
    10-K excerpts."``). The Phase 2 placeholder substring assertions
    (``"REFUSAL" in upper`` / ``"No evidence" in text``) are retired in
    favour of a symbolic byte-identity assertion against the canonical
    constant — single source of truth, no byte-literal drift.
    """
    from docintel_core.adapters.stub.llm import _STUB_REFUSAL
    from docintel_core.types import REFUSAL_TEXT_SENTINEL

    response = stub_bundle.llm.complete("What is the weather today?")
    assert response.text == _STUB_REFUSAL, (
        f"refusal-path text must equal _STUB_REFUSAL: got {response.text!r}"
    )
    assert response.text == REFUSAL_TEXT_SENTINEL, (
        f"refusal-path text must equal REFUSAL_TEXT_SENTINEL: got {response.text!r}"
    )


# ---------------------------------------------------------------------------
# ADP-04: LLMJudge — verdict shape + no-match case
# ---------------------------------------------------------------------------


def test_stub_judge_score_range(stub_bundle) -> None:
    """StubLLMJudge.judge returns JudgeVerdict with score in [0, 1]."""
    prediction = "Revenue grew [chunk_1] and margins improved [chunk_2]."
    reference = ["chunk_1: revenue grew", "chunk_2: margins improved"]
    verdict = stub_bundle.judge.judge(prediction, reference)
    assert hasattr(verdict, "score")
    assert 0.0 <= verdict.score <= 1.0
    assert hasattr(verdict, "passed")
    assert isinstance(verdict.passed, bool)
    assert hasattr(verdict, "reasoning")
    assert isinstance(verdict.reasoning, str)
    assert hasattr(verdict, "unsupported_claims")
    assert isinstance(verdict.unsupported_claims, list)


def test_stub_judge_no_match(stub_bundle) -> None:
    """StubLLMJudge with no matching chunks returns score=0.0, passed=False."""
    prediction = "Revenue grew [chunk_99] and margins improved [chunk_100]."
    reference = ["chunk_1 content only", "chunk_2 content only"]
    verdict = stub_bundle.judge.judge(prediction, reference)
    assert verdict.score == 0.0
    assert verdict.passed is False


# ---------------------------------------------------------------------------
# ADP-05: make_adapters factory — stub mode + lazy import gate
# ---------------------------------------------------------------------------


def test_make_adapters_stub() -> None:
    """make_adapters(Settings(llm_provider='stub')) returns a valid AdapterBundle."""
    from docintel_core.adapters import make_adapters
    from docintel_core.config import Settings

    bundle = make_adapters(Settings(llm_provider="stub"))
    assert bundle is not None
    assert hasattr(bundle, "embedder")
    assert hasattr(bundle, "reranker")
    assert hasattr(bundle, "llm")
    assert hasattr(bundle, "judge")


def test_stub_no_sdk_import() -> None:
    """Stub-mode make_adapters must NOT introduce new heavy SDK imports.

    Validates D-12: lazy imports inside the real branch keep stub CI fast.
    The test snapshots sys.modules BEFORE calling the stub factory and verifies
    that no banned module appears AFTER the call. A prior test in the session
    may already have imported anthropic/openai (e.g. test_make_adapters_real_dispatch);
    the contract is that the STUB factory doesn't ADD them, not that they are globally
    absent from the process.
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.config import Settings

    banned = ("torch", "anthropic", "openai", "sentence_transformers")
    # Snapshot modules present BEFORE calling the stub factory.
    before = {name for name in banned if name in sys.modules}
    make_adapters(Settings(llm_provider="stub"))
    # Verify no NEW banned modules appeared as a result of calling the stub factory.
    for name in banned:
        if name not in before:
            assert (
                name not in sys.modules
            ), f"stub factory imported {name!r} — lazy import gate violated (D-12)"


@pytest.mark.skipif(
    not _can_import("anthropic", "openai"),
    reason=(
        "anthropic + openai SDKs not yet in lockfile — Wave 5 promotes them "
        "to direct deps of docintel-core; test runs automatically once importable"
    ),
)
def test_make_adapters_real_dispatch() -> None:
    """make_adapters in real/anthropic mode selects AnthropicAdapter as generator.

    Also verifies the cross-family judge (D-04): judge uses OpenAIAdapter when
    generator is Anthropic. No real API calls are made — dummy keys satisfy the
    Settings validation but complete() is never invoked.

    Skipped in Wave 3 (anthropic/openai not in lockfile yet).
    Runs automatically starting in Wave 5 when SDKs enter the lockfile.
    """
    from docintel_core.adapters import make_adapters
    from docintel_core.config import Settings
    from pydantic import SecretStr

    bundle = make_adapters(
        Settings(
            llm_provider="real",
            llm_real_provider="anthropic",
            anthropic_api_key=SecretStr("dummy-anthropic-key-for-test"),
            openai_api_key=SecretStr("dummy-openai-key-for-test"),
        )
    )
    assert type(bundle.llm).__name__ == "AnthropicAdapter"
    assert type(bundle.judge).__name__ == "CrossFamilyJudge"


# ---------------------------------------------------------------------------
# ADP-07: Stub determinism — 100-call fuzz across all four adapters
# ---------------------------------------------------------------------------


def test_stub_all_deterministic(stub_bundle) -> None:
    """All four stub adapters produce identical outputs across 100 repeated calls."""

    query = "R&D expenses increased significantly"
    docs = ["alpha", "beta", "gamma"]
    prompt_with_chunks = "[chunk_a] Alpha text. [chunk_b] Beta text. Query: R&D?"
    prediction = "Based on [chunk_a] and [chunk_b]."
    reference = ["chunk_a: alpha text present", "chunk_b: beta text present"]

    # Embedder determinism
    base_emb = stub_bundle.embedder.embed([query])
    for _ in range(100):
        assert (stub_bundle.embedder.embed([query]) == base_emb).all()

    # Reranker determinism
    base_ranks = [(r.doc_id, r.score) for r in stub_bundle.reranker.rerank(query, docs)]
    for _ in range(100):
        ranks = [(r.doc_id, r.score) for r in stub_bundle.reranker.rerank(query, docs)]
        assert ranks == base_ranks

    # LLMClient determinism
    base_llm = stub_bundle.llm.complete(prompt_with_chunks).text
    for _ in range(100):
        assert stub_bundle.llm.complete(prompt_with_chunks).text == base_llm

    # LLMJudge determinism
    base_verdict = stub_bundle.judge.judge(prediction, reference)
    for _ in range(100):
        v = stub_bundle.judge.judge(prediction, reference)
        assert v.score == base_verdict.score
        assert v.passed == base_verdict.passed


# ---------------------------------------------------------------------------
# ADP-01..07: Bundle Protocol conformance via @runtime_checkable isinstance
# ---------------------------------------------------------------------------


def test_bundle_protocol_conformance(stub_bundle) -> None:
    """Each bundle field satisfies its Protocol at runtime via @runtime_checkable."""
    from docintel_core.adapters.protocols import Embedder, LLMClient, LLMJudge, Reranker

    assert isinstance(stub_bundle.embedder, Embedder)
    assert isinstance(stub_bundle.reranker, Reranker)
    assert isinstance(stub_bundle.llm, LLMClient)
    assert isinstance(stub_bundle.judge, LLMJudge)


# ---------------------------------------------------------------------------
# Real-adapter smoke test — manual only, skipped in stub-mode CI
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("DOCINTEL_ANTHROPIC_API_KEY"),
    reason="real key not set — skipped in stub-mode CI",
)
def test_real_anthropic_adapter_complete() -> None:
    """One-shot smoke test against the live Anthropic API.

    Never runs in default CI — only executed when the user manually sets
    DOCINTEL_ANTHROPIC_API_KEY and invokes pytest with this key exported.
    """
    pytest.skip("Wave 4 implements — run manually after AnthropicAdapter lands")
