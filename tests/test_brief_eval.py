"""Story 3.1 (FR-C1/FR-C6) — brief eval: pure scoring + the AC-2 defect gate.

The retrieval/citation scoring is pure and tested here over duck-typed section
results; the judge-backed faithfulness + the full runner are exercised by the
CLI smoke in CI. AC-2: a fabricated/mis-cited claim must lower citation
accuracy — it cannot silently pass.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from docintel_eval.brief_dataset import BriefEvalRecord, load_brief_questions
from docintel_eval.brief_runner import brief_citation_hits, merge_rankings, score_brief


def _cit(chunk_id: str) -> SimpleNamespace:
    return SimpleNamespace(chunk_id=chunk_id)


def _section(cited: list[str]) -> SimpleNamespace:
    return SimpleNamespace(answer=SimpleNamespace(citations=[_cit(c) for c in cited]))


def test_merge_rankings_by_best_position_deduped() -> None:
    # Merge two section rankings by best (lowest) position across sections.
    merged = merge_rankings([["B", "A"], ["C", "A"]])
    assert merged[0] in {"B", "C"}  # both at position 0
    assert merged.index("A") == len(merged) - 1  # A best position is 1, last


def test_brief_citation_hits_counts_across_sections() -> None:
    secs = [_section(["A", "X"]), _section(["B"])]
    hits, n = brief_citation_hits(secs, expected={"A", "B"})
    assert (hits, n) == (2, 3)  # A,B expected; X not


def test_score_brief_clean_brief_scores_high() -> None:
    gold = ["AAPL-FY2024-Item-7-003", "AAPL-FY2024-Item-1A-022"]
    ranking = ["AAPL-FY2024-Item-7-003", "AAPL-FY2024-Item-1A-022", "OTHER-1"]
    secs = [_section(["AAPL-FY2024-Item-7-003"]), _section(["AAPL-FY2024-Item-1A-022"])]
    s = score_brief(ranking, secs, gold, gold)
    assert s["hit_at_5"] == 1  # both golds in the merged top-5
    assert s["recall_at_10"] == 1.0  # both golds surfaced
    assert s["citation_precision"] == 1.0  # every citation is expected


def test_score_brief_recall_is_fractional_for_partial_gold() -> None:
    # Recall@k = fraction of golds surfaced — the meaningful brief metric when a
    # brief has many golds spanning items (strict Hit@K would be all-or-nothing 0).
    gold = ["G1", "G2", "G3", "G4"]
    ranking = ["G1", "OTHER", "G2", "X", "Y"]  # 2 of 4 golds in top-5
    s = score_brief(ranking, [], gold, [])
    assert s["recall_at_5"] == 0.5
    assert s["hit_at_5"] == 0  # strict: not ALL golds in top-5


def test_score_brief_defect_is_reflected_not_silently_passed() -> None:
    # AC-2: a brief that cites a fabricated/mis-cited chunk (not in expected) has
    # citation precision < 1.0 — the defect is reflected, not silently passed.
    gold = ["AAPL-FY2024-Item-7-003"]
    ranking = ["AAPL-FY2024-Item-7-003"]
    secs = [
        _section(["AAPL-FY2024-Item-7-003"]),
        _section(["GHOST-FY2099-Item-9-999"]),  # fabricated citation
    ]
    s = score_brief(ranking, secs, gold, gold)
    assert s["citation_precision"] == 0.5  # 1 of 2 citations expected
    assert s["n_citations"] == 2


def test_brief_dataset_validates_and_loads() -> None:
    # expected must be a subset of gold
    with pytest.raises(ValueError):
        BriefEvalRecord(
            ticker="X",
            company="X",
            gold_passage_ids=["A"],
            expected_citation_ids=["B"],
            rationale="r",
        )
    recs = load_brief_questions(Path("data/eval/brief_ground_truth/brief_set.jsonl"))
    assert len(recs) >= 3
    for r in recs:
        assert set(r.expected_citation_ids) <= set(r.gold_passage_ids)
        assert all(cid.startswith(f"{r.ticker}-") for cid in r.gold_passage_ids)
