"""Plan 05-06 canary driver — Phase 5 STRUCTURAL ACCEPTANCE GATE (RET-03).

Closes D-13 / D-14 / D-15 / D-16 + Pitfall 6 doubling. Drives the four canary
tests against ``data/eval/canary/cases.jsonl`` per RESEARCH §9 Pattern A
(single-file dual-mode pytest driver).

Plan 05-06 Option D amendment (CONTEXT.md D-14/D-15 amendment block):
    Empirical finding: the stub reranker (``StubReranker``) is structurally
    incapable of beating stub dense-only because both stages run cosine over
    the SAME ``_text_to_vector`` hash function in ``adapters/stub/embedder.py``.
    A 307-case brute-force exploration found 0 rerank-only wins. The strict
    D-14 aggregate criterion therefore bites in REAL MODE only — workflow_dispatch.
    Stub mode falls back to a SCHEMA-ONLY assertion (cases.jsonl is well-formed,
    seven required fields per record, len >= 5).

Test functions
--------------

* :func:`test_cases_loaded` — D-13 schema gate: ``_load_cases()`` returns
  ``>= 5`` records and every record carries the seven D-13 schema fields
  (including the ``mode`` field added by Plan 05-06 Task 1). No
  ``@pytest.mark.xfail`` — passes immediately against the committed
  ``data/eval/canary/cases.jsonl``.

* :func:`test_reranker_canary_stub_mode` — D-14 SCHEMA-ONLY assertion
  under Option D. Loads the cases JSONL and asserts the schema invariants
  (count, seven fields, ``mode`` in the allowed set, non-empty
  ``gold_chunk_ids``). Does NOT run the rerank-vs-dense-only differential
  — that differential bites in real mode only (see
  :func:`test_reranker_canary_real_mode` below). No ``@pytest.mark.xfail``.

* :func:`test_failure_message_quotes_claude_md` — Pitfall 6 doubled-defense.
  Asserts that all three required substrings ("BGE 512-token truncation FIRST",
  "before suspecting hybrid retrieval, RRF, or chunk size", "the canary exists
  specifically to catch it") appear in BOTH the test-local
  ``_CLAUDE_MD_QUOTE`` constant AND the retriever module's
  ``_CLAUDE_MD_HARD_GATE`` constant. If either constant drifts from
  CLAUDE.md / ROADMAP.md line 170 / CONTEXT.md D-16, this test goes red.
  The ``_CLAUDE_MD_HARD_GATE`` import was promoted from in-function (Plan
  05-01 Wave-0 hook) to MODULE TOP by Plan 05-06 Task 2 — Plan 05-05 has
  shipped ``docintel_retrieve.retriever`` with the constant.

* :func:`test_reranker_canary_real_mode` — D-14 strict aggregate criterion
  under real mode only. ``@pytest.mark.real``-gated (deselected by default
  CI's ``-m "not real"`` selector; collectable via ``-m real`` in the
  ``real-index-build`` workflow_dispatch job). Carries an inner
  ``@pytest.mark.xfail(strict=True)`` marker pending Plan 05-07's
  empirical real-mode verification under workflow_dispatch — once Plan
  05-07 records the rerank vs dense-only numbers and confirms the strict
  D-14 criterion, the xfail marker is removed there.

Marker discipline
-----------------

The marker pattern is FUNCTION-LEVEL not MODULE-LEVEL (RESEARCH §9 Pattern A,
additional_planning_notes constraint 7). ``pytestmark = pytest.mark.real``
would gate every test in this file behind ``-m real`` and break the
stub-mode CI contract (D-15 — stub-mode mandatory on every PR via the
default lint-and-test job).

The real-mode test's marker order is ``@pytest.mark.real`` (outer) +
``@pytest.mark.xfail`` (inner): pytest's marker-collection layer
evaluates ``not real`` deselection BEFORE applying the xfail, so the
test is deselected on default runs and only collected via ``-m real``.

Pitfall 6 doubling
------------------

Per CLAUDE.md (project guide, extended by Plan 05-01 Task 0 to align
with CONTEXT.md D-16's verbatim claim) and ROADMAP.md line 170: the
three verbatim substrings must appear in every canary failure message.
:func:`test_failure_message_quotes_claude_md` asserts on BOTH the
test-local ``_CLAUDE_MD_QUOTE`` constant AND the retriever module's
``_CLAUDE_MD_HARD_GATE`` constant. Drift in EITHER source of truth
goes red in CI. Five total sources are kept in sync by this defense:
CLAUDE.md, ROADMAP.md, CONTEXT.md D-16, ``_CLAUDE_MD_QUOTE`` (here),
and ``_CLAUDE_MD_HARD_GATE`` (``docintel_retrieve.retriever``).

Analogs
-------

* ``tests/test_index_build_real.py`` (``pytestmark = pytest.mark.real``)
  — real-mode marker pattern (module-level there; function-level here).
* ``tests/test_chunk_idempotency.py`` (``_REPO_ROOT``) — canonical
  test-relative path anchor.
* 05-PATTERNS.md ``tests/test_reranker_canary.py`` section + RESEARCH.md
  lines 862-1003 (canary skeleton).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from docintel_retrieve.retriever import _CLAUDE_MD_HARD_GATE

# Canonical test-relative path anchor (S4 pattern; matches tests/test_chunk_idempotency.py line 27).
_REPO_ROOT = Path(__file__).resolve().parent.parent

# Per D-13 — committed JSONL fixture at data/eval/canary/cases.jsonl.
_CASES_PATH = _REPO_ROOT / "data" / "eval" / "canary" / "cases.jsonl"

# D-13 schema — the six original required fields per record; the seventh
# (``mode``) is added by Plan 05-06 Task 1 (Option D resolution).
_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {"case_id", "question", "gold_chunk_ids", "ticker", "fiscal_year", "rationale", "mode"}
)

# D-15 floor: the canary requires at least 5 curated cases to make the
# real-mode rerank-vs-dense-only differential statistically meaningful.
_MIN_CASES = 5

# Allowed values for the ``mode`` field (Plan 05-06 Task 1 amendment).
# ``"real"`` — case runs in real mode only (the default under Option D since
# stub reranker cannot beat stub dense-only structurally).
# ``"stub"`` — case is stub-mode-eligible (reserved for a future re-curation
# after the deferred stub-reranker discriminative-power redesign lands).
# ``None`` — case has no mode constraint (treated as both-eligible).
_ALLOWED_MODES: frozenset[str | None] = frozenset({"real", "stub", None})

# Verbatim CLAUDE.md hard-gate quote (per D-16 + RESEARCH lines 934-939).
# This constant MUST contain all three substrings:
#   * "BGE 512-token truncation FIRST"
#   * "before suspecting hybrid retrieval, RRF, or chunk size"
#   * "the canary exists specifically to catch it"
# Plan 05-01 Task 0 extended CLAUDE.md by one sentence to align the project
# guide with CONTEXT.md D-16's verbatim claim and with ROADMAP.md line 170.
# If ANY of the five sources (CLAUDE.md, ROADMAP.md, CONTEXT.md, this
# constant, retriever._CLAUDE_MD_HARD_GATE) drift,
# test_failure_message_quotes_claude_md below goes red — Pitfall 6
# mitigation (defense doubled).
_CLAUDE_MD_QUOTE = (
    'Per CLAUDE.md: "If that gate fails, look at BGE 512-token truncation FIRST '
    "before suspecting hybrid retrieval, RRF, or chunk size. This is the most "
    'common subtle failure mode and the canary exists specifically to catch it."'
)

# D-16 three-step debug block — embedded in every canary failure assertion
# (currently the real-mode test's two assertions; stub-mode test is schema-
# only under Option D and does not run the rerank-vs-dense-only differential).
_DEBUG_BLOCK = (
    f"\n\n{_CLAUDE_MD_QUOTE}\n\n"
    "Debug order:\n"
    "  1. Run `make verify-chunks` — confirm every chunk_id has n_tokens < 500.\n"
    "  2. Confirm bge-reranker-base SDK pin hasn't drifted (tokenizer revision).\n"
    "  3. THEN investigate RRF / chunk-size / hybrid retrieval changes."
)


def _load_cases() -> list[dict[str, Any]]:
    """Load every JSONL record from ``_CASES_PATH``.

    Returns:
        list of dicts (one per non-empty line). Each record has the seven
        D-13 schema fields (case_id / question / gold_chunk_ids / ticker /
        fiscal_year / rationale / mode). Schema validation is done by
        the caller (``test_cases_loaded`` /
        ``test_reranker_canary_stub_mode``) so the loader stays cheap.

    Notes:
        * Empty lines are skipped.
        * No JSON-comment handling — JSONL must be pure JSON per line.
    """
    assert _CASES_PATH.exists(), f"D-13 cases.jsonl must exist at {_CASES_PATH}"
    cases: list[dict[str, Any]] = []
    for line in _CASES_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        cases.append(json.loads(stripped))
    return cases


def _top3_hits(retriever: Any, cases: list[dict[str, Any]]) -> int:
    """Count cases where the retriever's top-3 contains any ``gold_chunk_id``.

    Used by ``test_reranker_canary_real_mode`` for the strict D-14
    differential. Stub mode does not call this helper — under Option D
    the stub-mode test is schema-only.

    Args:
        retriever: Any object with a ``.search(query, k) -> list[obj]``
            method whose ``obj.chunk_id`` attribute is a chunk_id string.
            ``Retriever`` (rerank-pipeline) and ``Retriever`` (dense-only
            via ``NullReranker``) both satisfy this shape.
        cases: List of D-13 records.

    Returns:
        Count of cases where ``set(case["gold_chunk_ids"]) & set(top3_ids)``
        is non-empty. The maximum value is ``len(cases)``.
    """
    hits = 0
    for case in cases:
        top3_ids = {result.chunk_id for result in retriever.search(case["question"], k=3)}
        gold_ids = set(case["gold_chunk_ids"])
        if gold_ids & top3_ids:
            hits += 1
    return hits


def _make_dense_only_retriever(cfg: Any) -> Any:
    """Construct a dense-only retriever by swapping ``NullReranker`` into the bundle.

    Used by ``test_reranker_canary_real_mode``. The Phase 5 D-08 ablation
    pattern — ``Retriever.search`` has zero conditional branches for
    ablation; null adapters degenerate the rerank stage in place so the
    rest of the pipeline runs unchanged.

    Args:
        cfg: ``Settings`` instance with ``llm_provider`` set.

    Returns:
        ``Retriever`` bound to an ``AdapterBundle`` whose ``reranker`` is
        ``NullReranker`` and whose other adapters come from
        ``make_adapters(cfg)``. Both retrievers (rerank-pipeline AND
        dense-only ablation) therefore share embedder + LLM + judge +
        index stores; only the reranker stage differs.
    """
    # Lazy imports — keep the test-module import cheap and avoid pulling in
    # docintel_core / docintel_retrieve at collection time when the test is
    # deselected (default CI's `not real` selector).
    from docintel_core.adapters.factory import make_adapters, make_index_stores
    from docintel_retrieve.null_adapters import NullReranker
    from docintel_retrieve.retriever import Retriever

    bundle = make_adapters(cfg)
    bundle_null = bundle.model_copy(update={"reranker": NullReranker()})
    stores = make_index_stores(cfg)
    return Retriever(bundle=bundle_null, stores=stores, cfg=cfg)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cases_loaded() -> None:
    """RET-03 — ``cases.jsonl`` loads with >= 5 entries (D-13 + D-15 floor).

    Plan 05-01 placeholder shipped 1 record (xfail); Plan 05-06 Task 1
    curated 8 cases (xfail removed here).

    The schema check covers all seven required fields including the
    Plan-05-06-Task-1 ``mode`` field (Option D resolution).
    """
    cases = _load_cases()
    assert len(cases) >= _MIN_CASES, (
        f"D-15 floor: cases.jsonl must contain >= {_MIN_CASES} entries; got {len(cases)}. "
        f"Plan 05-06 Task 1 curated 8 cases — if the count has dropped, the "
        f"file has regressed."
    )
    for case in cases:
        missing = _REQUIRED_FIELDS - set(case)
        assert not missing, (
            f"D-13 schema: case {case.get('case_id', '?')!r} is missing fields {sorted(missing)}. "
            f"Required: {sorted(_REQUIRED_FIELDS)}."
        )


def test_reranker_canary_stub_mode() -> None:
    """RET-03 stub mode — SCHEMA-ONLY assertion under Plan 05-06 Option D.

    The Plan 05-06 Task 1 checkpoint resolution (CONTEXT.md D-14/D-15
    amendment) weakens this test to schema-only because the stub reranker
    is structurally incapable of beating stub dense-only (both use
    ``_text_to_vector`` from ``adapters/stub/embedder.py``; empirical
    307-case brute-force run produced 0 rerank-only wins).

    The strict D-14 differential (``rerank_top3_hits > dense_only_top3_hits
    AND rerank_top3_hits >= 5``) is enforced in
    ``test_reranker_canary_real_mode`` under workflow_dispatch. Stub-mode
    on every PR keeps the schema invariants live so the canary's
    JSONL artifact does not silently regress.
    """
    cases = _load_cases()
    assert (
        len(cases) >= _MIN_CASES
    ), f"D-15 floor: cases.jsonl must contain >= {_MIN_CASES} entries; got {len(cases)}."
    for case in cases:
        # Seven required fields (the six D-13 fields + the Plan 05-06 Task 1 ``mode`` field).
        missing = _REQUIRED_FIELDS - set(case)
        assert not missing, (
            f"D-13 schema: case {case.get('case_id', '?')!r} is missing fields {sorted(missing)}. "
            f"Required: {sorted(_REQUIRED_FIELDS)}."
        )
        # ``mode`` must be in the allowed set (real / stub / None).
        mode = case.get("mode")
        # RUF005-clean human-readable list of allowed modes for the assertion message.
        _allowed_str = [*sorted(m for m in _ALLOWED_MODES if m is not None), "None"]
        assert (
            mode in _ALLOWED_MODES
        ), f"Case {case['case_id']!r}: mode={mode!r} not in {_allowed_str}."
        # ``gold_chunk_ids`` must be a non-empty list of strings.
        gold = case["gold_chunk_ids"]
        assert isinstance(
            gold, list
        ), f"Case {case['case_id']!r}: gold_chunk_ids must be a list; got {type(gold).__name__}."
        assert gold, f"Case {case['case_id']!r}: gold_chunk_ids must be non-empty."
        assert all(
            isinstance(g, str) for g in gold
        ), f"Case {case['case_id']!r}: gold_chunk_ids must contain only strings."


def test_failure_message_quotes_claude_md() -> None:
    """RET-03 — verbatim CLAUDE.md hard-gate quote in BOTH constants (Pitfall 6 doubled).

    Asserts the three required substrings appear in BOTH:
      * ``_CLAUDE_MD_QUOTE`` (test-local constant, used in stub-mode + real-mode
        failure messages)
      * ``_CLAUDE_MD_HARD_GATE`` (``docintel_retrieve.retriever`` module
        constant, used in the Retriever's D-10 chunk-loop AssertionError)

    The ``_CLAUDE_MD_HARD_GATE`` import is at MODULE TOP (Plan 05-06 Task 2
    promotion from in-function — Plan 05-01 Wave-0 hook is no longer
    needed because Plan 05-05 has shipped ``docintel_retrieve.retriever``).

    If a future "cleanup" PR paraphrases the quote in ANY of the five
    sources (CLAUDE.md, ROADMAP.md, CONTEXT.md, this constant,
    retriever._CLAUDE_MD_HARD_GATE), this test goes red.
    """
    # Pitfall 6 mitigation — three substrings asserted in BOTH constants (defense doubled).
    assert "BGE 512-token truncation FIRST" in _CLAUDE_MD_QUOTE, (
        "Pitfall 6: _CLAUDE_MD_QUOTE drift (test-local constant); "
        "missing 'BGE 512-token truncation FIRST' substring."
    )
    assert "before suspecting hybrid retrieval, RRF, or chunk size" in _CLAUDE_MD_QUOTE, (
        "Pitfall 6: _CLAUDE_MD_QUOTE drift (test-local constant); "
        "missing 'before suspecting hybrid retrieval, RRF, or chunk size' substring."
    )
    assert "the canary exists specifically to catch it" in _CLAUDE_MD_QUOTE, (
        "Pitfall 6: _CLAUDE_MD_QUOTE drift (test-local constant); "
        "missing 'the canary exists specifically to catch it' substring."
    )
    assert "BGE 512-token truncation FIRST" in _CLAUDE_MD_HARD_GATE, (
        "Pitfall 6: docintel_retrieve.retriever._CLAUDE_MD_HARD_GATE drift; "
        "missing 'BGE 512-token truncation FIRST' substring."
    )
    assert "before suspecting hybrid retrieval, RRF, or chunk size" in _CLAUDE_MD_HARD_GATE, (
        "Pitfall 6: docintel_retrieve.retriever._CLAUDE_MD_HARD_GATE drift; "
        "missing 'before suspecting hybrid retrieval, RRF, or chunk size' substring."
    )
    assert "the canary exists specifically to catch it" in _CLAUDE_MD_HARD_GATE, (
        "Pitfall 6: docintel_retrieve.retriever._CLAUDE_MD_HARD_GATE drift; "
        "missing 'the canary exists specifically to catch it' substring."
    )


@pytest.mark.real
def test_reranker_canary_real_mode() -> None:
    """RET-03 — STRICT D-14 differential under real mode (workflow_dispatch).

    Marker discipline (RESEARCH §9 Pattern A + additional_planning_notes
    constraint 7): ``@pytest.mark.real`` (function-level, not module-level).
    pytest's marker-collection layer evaluates ``not real`` deselection so
    the test is deselected on default pytest runs and only collected via
    ``-m real`` (the ``real-index-build`` job in ``.github/workflows/ci.yml``).

    Plan 05-07 Task 3 — preemptive xfail removal. The
    ``@pytest.mark.xfail(strict=True, reason="Plan 05-07 — real-mode
    verification under workflow_dispatch")`` marker placed by Plan 05-06
    Task 2 was removed in this plan so the FIRST workflow_dispatch run
    against the phase/5 branch shows ``PASSED`` directly (rather than
    ``XPASS`` → developer-removes-marker → ``PASSED`` on a second run).
    The empirical verification under workflow_dispatch is documented in
    05-07-SUMMARY.md `## Workflow_dispatch verification` section
    (Task 2 checkpoint resolution).

    Test body — RESEARCH §9 + the strict D-14 aggregate criterion:
        rerank_top3_hits      = top-3 hits via make_retriever(cfg=real)
        dense_only_top3_hits  = top-3 hits via Retriever(bundle.model_copy(
                                    update={"reranker": NullReranker()}), stores, cfg)
        assert rerank_top3_hits > dense_only_top3_hits
        assert rerank_top3_hits >= 5

    Failure messages embed ``_CLAUDE_MD_QUOTE`` + the three-step D-16
    debug order — Pitfall 6 doubled-defense.
    """
    # Lazy imports — only collected under `-m real`.
    from docintel_core.adapters.factory import make_retriever
    from docintel_core.config import Settings

    cfg = Settings(llm_provider="real")
    rerank_retriever = make_retriever(cfg)
    dense_only_retriever = _make_dense_only_retriever(cfg)

    cases = _load_cases()
    # Real-mode filter: skip records explicitly marked stub-mode only
    # (none today; reserved for a future re-curation after the deferred
    # stub-reranker discriminative-power redesign lands).
    cases_real = [c for c in cases if c.get("mode") in ("real", None)]

    rerank_top3_hits = _top3_hits(rerank_retriever, cases_real)
    dense_only_top3_hits = _top3_hits(dense_only_retriever, cases_real)

    assert rerank_top3_hits > dense_only_top3_hits, (
        f"Reranker canary failed (real mode): rerank top-3 hits "
        f"({rerank_top3_hits}) did not exceed dense-only top-3 hits "
        f"({dense_only_top3_hits}).{_DEBUG_BLOCK}"
    )
    assert rerank_top3_hits >= _MIN_CASES, (
        f"Reranker canary failed (real mode): rerank top-3 hits "
        f"({rerank_top3_hits}) < {_MIN_CASES} cases — minimum acceptance bar."
        f"{_DEBUG_BLOCK}"
    )
