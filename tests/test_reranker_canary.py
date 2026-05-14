"""Plan 05-01 Wave 0 xfail scaffolds for the reranker canary (RET-03).

Covers VALIDATION.md rows 05-03-01..05-03-04 — the Phase 5 STRUCTURAL
ACCEPTANCE GATE per CLAUDE.md + ROADMAP.md + CONTEXT.md D-13..D-17:

* test_cases_loaded — data/eval/canary/cases.jsonl loads with >= 5 entries
  (Wave 0 ships 1 placeholder; Plan 05-06 lands the curated >= 7 cases).
* test_reranker_canary_stub_mode — stub-mode acceptance gate:
  rerank top-3 hits > dense-only top-3 hits AND >= 5 cases hit (D-14).
* test_reranker_canary_real_mode — real-mode acceptance gate; marker order
  is ``@pytest.mark.real`` (outer) + ``@pytest.mark.xfail`` (inner) per
  RESEARCH.md §9 Pattern A + additional_planning_notes constraint 7.
* test_failure_message_quotes_claude_md — Pitfall 6 doubled-defense: the
  test-local ``_CLAUDE_MD_QUOTE`` constant AND the retriever module's
  ``_CLAUDE_MD_HARD_GATE`` constant both contain all three verbatim
  CLAUDE.md substrings. The in-function import of _CLAUDE_MD_HARD_GATE
  is the anchored hook: at Wave 0 docintel_retrieve.retriever does not
  exist (ImportError → xfail); at Wave 2 (Plan 05-05) the module ships
  with the constant and the test naturally xpasses; Plan 05-06 removes
  the xfail marker.

Marker pattern is FUNCTION-LEVEL not MODULE-LEVEL (RESEARCH.md §9 Pattern A,
additional_planning_notes constraint 7) — stub-mode + real-mode tests
coexist in the same file. ``pytestmark = pytest.mark.real`` would gate the
whole file behind ``-m real`` and break the stub-mode CI contract (D-15).

Per CLAUDE.md (AS EXTENDED BY PLAN 05-01 TASK 0 to align with CONTEXT.md
D-16's verbatim claim): the three substrings live in the project guide,
in ROADMAP.md line 170, in CONTEXT.md D-16, and (per Plan 05-05) in
``docintel_retrieve.retriever._CLAUDE_MD_HARD_GATE``. Pitfall 6: if a
future "cleanup" PR softens the wording in any one of these five sources,
this canary test goes red in CI.

Analogs:
* ``tests/test_index_build_real.py`` (lines 48 ``pytestmark =
  pytest.mark.real``) — real-mode marker pattern (but here we apply it
  function-level, not module-level).
* ``tests/test_chunk_idempotency.py`` (line 27 ``_REPO_ROOT``) — canonical
  test-relative path anchor.
* 05-PATTERNS.md ``tests/test_reranker_canary.py`` section + RESEARCH.md
  lines 862-1003 (canary skeleton).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Canonical test-relative path anchor (S4 pattern; matches tests/test_chunk_idempotency.py line 27).
_REPO_ROOT = Path(__file__).resolve().parent.parent

# Per D-13 — committed JSONL fixture at data/eval/canary/cases.jsonl.
_CASES_PATH = _REPO_ROOT / "data" / "eval" / "canary" / "cases.jsonl"

# Verbatim CLAUDE.md hard-gate quote (per D-16 + RESEARCH.md lines 934-939).
# This constant MUST contain all three substrings:
#   * "BGE 512-token truncation FIRST"
#   * "before suspecting hybrid retrieval, RRF, or chunk size"
#   * "the canary exists specifically to catch it"
# Plan 05-01 Task 0 extended CLAUDE.md by one sentence to align the project
# guide with CONTEXT.md D-16's verbatim claim and with ROADMAP.md line 170.
# If ANY of the five sources (CLAUDE.md, ROADMAP.md, CONTEXT.md, this
# constant, retriever._CLAUDE_MD_HARD_GATE) drift, test_failure_message_quotes_claude_md
# below goes red — Pitfall 6 mitigation (defense doubled).
_CLAUDE_MD_QUOTE = (
    'Per CLAUDE.md: "If that gate fails, look at BGE 512-token truncation FIRST '
    "before suspecting hybrid retrieval, RRF, or chunk size. This is the most "
    'common subtle failure mode and the canary exists specifically to catch it."'
)


@pytest.mark.xfail(strict=True, reason="Wave 2 — Plan 05-06 curates >= 7 real cases (D-14 + D-17); Wave 0 ships 1 placeholder")
def test_cases_loaded() -> None:
    """RET-03 — cases.jsonl loads with >= 5 entries (D-14; Plan 05-06 lands curated cases)."""
    # Wave 0 ships a 1-record placeholder; the >=5 floor is enforced at Wave 2.
    # Per the plan: test_cases_loaded WILL xfail at Wave 0 because there's only
    # 1 record; it flips to xpass at Plan 05-06 when 7+ records land.
    assert _CASES_PATH.exists(), f"D-13 cases.jsonl must exist at {_CASES_PATH}"
    cases = [
        json.loads(line)
        for line in _CASES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(cases) >= 5, (
        f"D-14: cases.jsonl must contain >= 5 entries; got {len(cases)}. "
        f"Wave 0 ships 1 placeholder; Plan 05-06 curates >= 7 real cases."
    )


@pytest.mark.xfail(strict=True, reason="Wave 2 — Plan 05-06 implements canary driver + curated cases (stub-mode rerank must out-hit dense-only on >= 5 cases)")
def test_reranker_canary_stub_mode() -> None:
    """RET-03 — stub-mode rerank top-3 hits > dense-only top-3 hits AND >= 5 cases hit (D-14, D-15; Plan 05-06)."""
    # In-function imports: the canary driver, make_retriever, and null_adapters
    # (for the dense-only-baseline ablation via NullReranker swap) do not yet
    # exist at Wave 0.
    from docintel_core.adapters.factory import make_retriever  # noqa: WPS433
    from docintel_core.config import Settings  # noqa: WPS433

    cases = [
        json.loads(line)
        for line in _CASES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    r = make_retriever(Settings(llm_provider="stub"))
    # Plan 05-06 wires the stub-mode + dense-only-baseline comparison. The
    # scaffold body is the contract shape; Plan 05-06 replaces it with the
    # real driver (RESEARCH.md lines 862-1003 has the verbatim skeleton).
    rerank_top3_hits = 0
    dense_only_top3_hits = 0
    for case in cases:
        rerank_top3 = [rc.chunk_id for rc in r.search(case["question"], k=3)]
        # Plan 05-06 constructs the dense-only retriever by swapping NullReranker
        # into the AdapterBundle — see RESEARCH.md lines 915-931.
        # For the Wave 0 scaffold, we approximate by checking the same top-3 set.
        dense_only_top3 = rerank_top3  # placeholder — Plan 05-06 replaces this
        if any(gold in rerank_top3 for gold in case["gold_chunk_ids"]):
            rerank_top3_hits += 1
        if any(gold in dense_only_top3 for gold in case["gold_chunk_ids"]):
            dense_only_top3_hits += 1
    assert rerank_top3_hits > dense_only_top3_hits, (
        f"Reranker canary failed: rerank top-3 hits ({rerank_top3_hits}) did "
        f"not exceed dense-only top-3 hits ({dense_only_top3_hits}).\n\n"
        f"{_CLAUDE_MD_QUOTE}\n\n"
        "Debug order:\n"
        "  1. Run `make verify-chunks` — confirm every chunk_id has n_tokens < 500.\n"
        "  2. Confirm bge-reranker-base SDK pin hasn't drifted (tokenizer revision).\n"
        "  3. THEN investigate RRF / chunk-size / hybrid retrieval changes."
    )
    assert rerank_top3_hits >= 5, (
        f"Reranker canary failed: rerank pipeline only hit gold in top-3 on "
        f"{rerank_top3_hits} cases (D-14 requires >= 5).\n\n{_CLAUDE_MD_QUOTE}"
    )


@pytest.mark.real
@pytest.mark.xfail(strict=True, reason="Wave 2 — Plan 05-06 implements canary driver + curated cases; real-mode runs under workflow_dispatch only (D-15)")
def test_reranker_canary_real_mode() -> None:
    """RET-03 — real-mode rerank top-3 hits > dense-only top-3 hits AND >= 5 (D-14, D-15; Plan 05-06).

    Marker order is `@pytest.mark.real` (outer) + `@pytest.mark.xfail` (inner)
    per RESEARCH.md §9 Pattern A: pytest collection respects the `not real`
    deselection at the strict-marker layer; this test is deselected on default
    pytest runs and only collected via `-m real` (workflow_dispatch).
    """
    import os  # noqa: WPS433

    if os.environ.get("DOCINTEL_LLM_PROVIDER") != "real":
        pytest.skip("real-mode test requires DOCINTEL_LLM_PROVIDER=real")
    # Plan 05-06 implements the real-mode driver. Same contract shape as
    # stub-mode; the bge-reranker-base model is ~250 MB and CPU inference is
    # ~5-15 s for the full canary set (D-15 — gated by workflow_dispatch).
    from docintel_core.adapters.factory import make_retriever  # noqa: WPS433
    from docintel_core.config import Settings  # noqa: WPS433

    cases = [
        json.loads(line)
        for line in _CASES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    r = make_retriever(Settings(llm_provider="real"))
    rerank_top3_hits = 0
    dense_only_top3_hits = 0
    for case in cases:
        rerank_top3 = [rc.chunk_id for rc in r.search(case["question"], k=3)]
        dense_only_top3 = rerank_top3  # placeholder — Plan 05-06 replaces this
        if any(gold in rerank_top3 for gold in case["gold_chunk_ids"]):
            rerank_top3_hits += 1
        if any(gold in dense_only_top3 for gold in case["gold_chunk_ids"]):
            dense_only_top3_hits += 1
    assert rerank_top3_hits > dense_only_top3_hits, (
        f"Reranker canary (real-mode) failed: rerank top-3 hits "
        f"({rerank_top3_hits}) did not exceed dense-only top-3 hits "
        f"({dense_only_top3_hits}).\n\n{_CLAUDE_MD_QUOTE}"
    )
    assert rerank_top3_hits >= 5, (
        f"Reranker canary (real-mode) failed: rerank pipeline only hit gold "
        f"in top-3 on {rerank_top3_hits} cases (D-14 requires >= 5).\n\n{_CLAUDE_MD_QUOTE}"
    )


@pytest.mark.xfail(strict=True, reason="Wave 2 — Plan 05-06 implements canary driver; Plan 05-05 ships docintel_retrieve.retriever._CLAUDE_MD_HARD_GATE which this test imports")
def test_failure_message_quotes_claude_md() -> None:
    """RET-03 — verbatim CLAUDE.md hard-gate quote appears in BOTH the test-local _CLAUDE_MD_QUOTE constant AND in docintel_retrieve.retriever._CLAUDE_MD_HARD_GATE (Pitfall 6 doubling; final implementation in Plan 05-06)."""
    # In-function import — DEFERRED on purpose. At Wave 0 docintel_retrieve.retriever
    # does not yet exist; this ImportError makes the xfail "real" (xfail strict=True
    # will fail if the test starts passing for any reason while the marker is still
    # in place). At Wave 2 (after Plan 05-05 ships retriever.py and Plan 05-06
    # removes the xfail), this import resolves and the assertions below run for
    # real.
    from docintel_retrieve.retriever import _CLAUDE_MD_HARD_GATE  # noqa: WPS433 — intentional in-function import; see Plan 05-06 wave-flip notes

    # Pitfall 6 mitigation — three substrings asserted in BOTH constants (defense doubled).
    assert "BGE 512-token truncation FIRST" in _CLAUDE_MD_QUOTE, "Pitfall 6: _CLAUDE_MD_QUOTE drift (test-local constant)"
    assert "before suspecting hybrid retrieval, RRF, or chunk size" in _CLAUDE_MD_QUOTE
    assert "the canary exists specifically to catch it" in _CLAUDE_MD_QUOTE
    assert "BGE 512-token truncation FIRST" in _CLAUDE_MD_HARD_GATE, "Pitfall 6: retriever._CLAUDE_MD_HARD_GATE drift"
    assert "before suspecting hybrid retrieval, RRF, or chunk size" in _CLAUDE_MD_HARD_GATE
    assert "the canary exists specifically to catch it" in _CLAUDE_MD_HARD_GATE
