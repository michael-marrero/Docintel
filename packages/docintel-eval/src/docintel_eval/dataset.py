"""docintel-eval dataset module: EvalRecord Pydantic v2 model + load_questions() loader.

Phase 8 (GT-01..GT-03) ground-truth evaluation dataset contract.

D-02: A Pydantic v2 model validates every record at load time (extra="forbid",
frozen=True — the ConfigDict contract-model precedent from docintel_core.types).

D-03: Per-record fields are the Phase 9 metrics contract. Locking the model first
turns a typo'd field or imagined chunk_id into a ValidationError at load time
rather than a silent Phase 9 miss.

Importers use: ``from docintel_eval.dataset import EvalRecord, load_questions``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from docintel_core.types import REFUSAL_TEXT_SENTINEL  # noqa: F401 — re-exported for tests

__all__ = ["EvalRecord", "load_questions"]


class EvalRecord(BaseModel):
    """D-03 ground-truth eval set record. Phase 9 metrics contract.

    All fields are required. Cross-field validators (mode="after") enforce:
    - D-04: expected_citation_ids ⊆ gold_passage_ids (always)
    - D-05: refusal records have gold_passage_ids=[] and expected_citation_ids=[]

    mode="after" is required so self.gold_passage_ids is already list[str] (not
    the raw JSON array) — same reasoning as Answer._citations_required_when_not_refused
    in docintel_core.types (PATTERNS.md lines 59–65).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    """Stable ID, e.g. 'GT-factual-001' / 'GT-comparative-001' / 'GT-refusal-001'."""

    question_type: Literal["single_doc", "multi_doc", "refusal"]
    """Question category driving test semantics in Phase 9."""

    question: str
    """The evaluation question text."""

    companies: list[str]
    """Tickers involved. single_doc = 1 element; refusal may be [] or the falsely-premised ticker."""

    fiscal_years: list[int]
    """Fiscal years involved (list so cross-year comparatives are expressible)."""

    gold_passage_ids: list[str]
    """chunk_ids; every chunk independently supporting the answer (Hit@K / MRR target). [] for refusal."""

    expected_citation_ids: list[str]
    """Strict subset of gold_passage_ids a correct answer must reference (MET-04 precision target); [] for refusal."""

    gold_answer: str
    """Extractive reference answer (MET-03 faithfulness target). Sentinel string for refusal (D-18)."""

    rationale: str
    """Why this is a good test case / why these gold passages (for the senior-engineer reader)."""

    difficulty: Literal["easy", "medium", "hard"]
    """Difficulty label for slice analysis."""

    tags: list[str]
    """Free-form slice tags, e.g. ['numeric', 'long-gold', 'cross-company', 'false-premise']."""

    @model_validator(mode="after")
    def _citations_subset_of_golds(self) -> "EvalRecord":
        """D-04: expected_citation_ids must be a subset of gold_passage_ids.

        Raises ValueError naming the record id and the offending citation id so
        the error message is actionable during curation.
        """
        gold_set = set(self.gold_passage_ids)
        for cid in self.expected_citation_ids:
            if cid not in gold_set:
                raise ValueError(
                    f"D-04: expected_citation_ids must be a subset of gold_passage_ids. "
                    f"Record {self.id!r}: citation id {cid!r} is in expected_citation_ids "
                    f"but not in gold_passage_ids {sorted(gold_set)!r}."
                )
        return self

    @model_validator(mode="after")
    def _refusal_fields_empty(self) -> "EvalRecord":
        """D-05: refusal records must have both gold lists empty.

        Raises ValueError if question_type='refusal' but either gold_passage_ids
        or expected_citation_ids is non-empty.
        """
        if self.question_type == "refusal":
            if self.gold_passage_ids or self.expected_citation_ids:
                raise ValueError(
                    f"D-05: refusal records must have gold_passage_ids=[] and "
                    f"expected_citation_ids=[]. Record {self.id!r} has "
                    f"gold_passage_ids={self.gold_passage_ids!r}, "
                    f"expected_citation_ids={self.expected_citation_ids!r}."
                )
        return self


def load_questions(path: Path) -> list[EvalRecord]:
    """Load and validate all EvalRecord objects from a JSONL file.

    Follows the canary loader shape (splitlines + strip + skip empty) from
    tests/test_reranker_canary.py _load_cases() (PATTERNS.md lines 113–125).
    Each line is validated by EvalRecord.model_validate — any schema violation
    raises pydantic.ValidationError at load time.

    Args:
        path: Path to the JSONL file (one JSON object per line).

    Returns:
        list[EvalRecord]: All validated records in file order.

    Raises:
        pydantic.ValidationError: If any line fails EvalRecord validation.
        json.JSONDecodeError: If any line is not valid JSON.
    """
    records: list[EvalRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        records.append(EvalRecord.model_validate(json.loads(stripped)))
    return records
