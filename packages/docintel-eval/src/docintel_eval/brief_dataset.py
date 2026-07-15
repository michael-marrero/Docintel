"""docintel-eval brief ground-truth contract (Story 3.1, FR-C1/FR-C6).

A brief is a company-scoped, four-section cited synthesis (Epic 2 `generate_brief`).
This is the eval-side contract for scoring one: the covered ticker + the
company's curated gold/expected chunks (ticker-prefixed subsets of the frozen
Q&A eval set — real chunk ids). Kept SEPARATE from the SHA-frozen Q&A
`eval_set.jsonl` (which must not change); brief cases live in their own file.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator

__all__ = ["BriefEvalRecord", "load_brief_questions"]


class BriefEvalRecord(BaseModel):
    """One brief eval case. Frozen + ``extra="forbid"`` (the harness contract pattern)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str
    company: str
    gold_passage_ids: list[str]
    """Chunk ids a good brief for this company should surface across its section
    retrievals (Hit@K / MRR target)."""
    expected_citation_ids: list[str]
    """Strict subset of gold a correct brief must cite (citation-accuracy target)."""
    rationale: str

    @model_validator(mode="after")
    def _expected_subset_of_gold(self) -> BriefEvalRecord:
        gold = set(self.gold_passage_ids)
        for cid in self.expected_citation_ids:
            if cid not in gold:
                raise ValueError(
                    f"BriefEvalRecord {self.ticker!r}: expected_citation_id {cid!r} "
                    f"not in gold_passage_ids"
                )
        return self


def load_brief_questions(path: Path) -> list[BriefEvalRecord]:
    """Load + validate brief eval cases from a JSONL file (mirrors load_questions)."""
    records: list[BriefEvalRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        records.append(BriefEvalRecord.model_validate(json.loads(stripped)))
    return records
