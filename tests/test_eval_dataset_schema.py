"""Well-formedness + resolution gate for the Phase 8 ground-truth eval set.

Tests the EvalRecord Pydantic v2 model (D-02/D-03) and the committed
questions.jsonl dataset against a 12-function well-formedness suite.

Wave-0 semantics (Plan 01): the schema + gold-ID-resolution gates run green
against the single-record seed. Curation-volume gates (test_record_count,
test_question_type_mix, test_refusal_flavor_coverage) are xfail-strict until
the curation waves (Plans 02-04) populate the dataset to ≥30 records; Plan 05
removes exactly these 3 markers once curation completes.

All tests are stub-mode eligible — they read committed corpus chunk files from
disk, never a live index. Do NOT add the real marker to any test in this file.

Follows the test_reranker_canary.py skeleton (_REPO_ROOT anchor, session-scoped
fixtures, assertion-message style — PATTERNS.md lines 90-184).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from docintel_core.types import REFUSAL_TEXT_SENTINEL

# ---------------------------------------------------------------------------
# Module-level path anchor (canary test pattern — test_reranker_canary.py:100)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_QUESTIONS_PATH = _REPO_ROOT / "data" / "eval" / "ground_truth" / "questions.jsonl"

# ---------------------------------------------------------------------------
# Dataset volume floors (D-06 — curation gates; xfail-strict until Plans 02-04)
# ---------------------------------------------------------------------------
_MIN_RECORDS = 30
_MIN_SINGLE_DOC = 15
_MIN_MULTI_DOC = 10
_MIN_REFUSAL = 5

# ---------------------------------------------------------------------------
# Consistency thresholds (D-15 — BGE token threshold for "long-gold" tag)
# ---------------------------------------------------------------------------
_LONG_GOLD_TOKEN_THRESHOLD = 449

# ---------------------------------------------------------------------------
# Corpus coverage constraint (D-08 — FY2022 removed from corpus)
# ---------------------------------------------------------------------------
_FORBIDDEN_FY = 2022

# ---------------------------------------------------------------------------
# D-17 refusal flavor controlled vocabulary (5 flavors, one each required)
# ---------------------------------------------------------------------------
_REFUSAL_FLAVOR_TAGS: frozenset[str] = frozenset(
    {
        "absent-company",
        "out-of-range-year",
        "uncovered-topic",
        "false-premise",
        "unextracted-section",
    }
)

# ---------------------------------------------------------------------------
# Session-scoped fixtures (scope="session" is critical — corpus rglob over
# 5,248 chunks is expensive; rebuild once per test session, not per test)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def questions_file() -> Path:
    """Return the path to questions.jsonl, asserting it exists (GT-03)."""
    p = _QUESTIONS_PATH
    assert p.exists(), (
        f"GT-03: questions.jsonl must exist at {p}. "
        "Run Plan 01 (Wave 0) to create the seed file."
    )
    return p


@pytest.fixture(scope="session")
def all_records(questions_file: Path) -> list[object]:
    """Load and validate all EvalRecord objects from questions.jsonl.

    Triggers Pydantic validation for every record at fixture-setup time;
    any schema violation surfaces here, not inside individual test bodies.
    """
    from docintel_eval.dataset import EvalRecord, load_questions

    records: list[EvalRecord] = load_questions(questions_file)
    return records  # type: ignore[return-value]  # narrowed by load_questions return type


@pytest.fixture(scope="session")
def corpus_chunk_index() -> set[str]:
    """Build a set of all valid chunk_ids from the committed corpus.

    Rglob over data/corpus/chunks/**/*.jsonl (45 files, ~5,248 chunks).
    scope="session" is critical — rebuilding this index per test would
    add seconds of IO for each of the two resolution-gate tests.
    """
    chunk_ids: set[str] = set()
    corpus_dir = _REPO_ROOT / "data" / "corpus" / "chunks"
    for path in corpus_dir.rglob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                chunk_ids.add(json.loads(stripped)["chunk_id"])
    return chunk_ids


@pytest.fixture(scope="session")
def corpus_chunk_tokens() -> dict[str, int]:
    """Build chunk_id -> n_tokens mapping from the committed corpus.

    Used by test_long_gold_tag_consistent (D-15) to check whether a
    "long-gold"-tagged record's gold chunk actually exceeds the BGE
    512-token truncation threshold (_LONG_GOLD_TOKEN_THRESHOLD = 449).
    """
    tokens: dict[str, int] = {}
    corpus_dir = _REPO_ROOT / "data" / "corpus" / "chunks"
    for path in corpus_dir.rglob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                obj = json.loads(stripped)
                tokens[obj["chunk_id"]] = obj.get("n_tokens", 0)
    return tokens


# ---------------------------------------------------------------------------
# Test functions — 12 total (9 model/seed GREEN at Wave 0; 3 xfail-strict)
# ---------------------------------------------------------------------------

# --- Filesystem & load gate -------------------------------------------------


def test_file_exists() -> None:
    """GT-03: questions.jsonl must exist at the committed path."""
    assert _QUESTIONS_PATH.exists(), (
        f"GT-03: questions.jsonl not found at {_QUESTIONS_PATH}. "
        "Run Plan 01 (Wave 0) to create the seed file."
    )


def test_all_records_parse(all_records: list[object]) -> None:
    """GT-02: every JSONL line must parse as a valid EvalRecord.

    Pydantic validation fires inside load_questions() (called by the
    all_records fixture). If any line fails, the fixture itself raises —
    this test body is just the green-confirmation that the fixture loaded.
    """
    assert len(all_records) >= 1, (
        "GT-02: questions.jsonl must contain at least 1 valid EvalRecord. "
        "Check that the seed record was written correctly."
    )


# --- Curation-volume gates (xfail-strict until Plans 02-04) -----------------


@pytest.mark.xfail(strict=True, reason="curation-volume gate — populated in Plans 02-04")
def test_record_count(all_records: list[object]) -> None:
    """GT-01: dataset must contain at least 30 records (D-06 floor)."""
    assert len(all_records) >= _MIN_RECORDS, (
        f"GT-01: questions.jsonl has {len(all_records)} records; "
        f"need >= {_MIN_RECORDS}. Curation populates this in Plans 02-04."
    )


@pytest.mark.xfail(strict=True, reason="curation-volume gate — populated in Plans 02-04")
def test_question_type_mix(all_records: list[object]) -> None:
    """GT-01: dataset must cover the required type mix (D-06).

    ~15 single_doc / ~10 multi_doc / ~5 refusal.
    """
    from docintel_eval.dataset import EvalRecord

    records: list[EvalRecord] = all_records  # type: ignore[assignment]
    single_doc = sum(1 for r in records if r.question_type == "single_doc")
    multi_doc = sum(1 for r in records if r.question_type == "multi_doc")
    refusal = sum(1 for r in records if r.question_type == "refusal")
    assert single_doc >= _MIN_SINGLE_DOC, (
        f"GT-01: need >= {_MIN_SINGLE_DOC} single_doc records; got {single_doc}."
    )
    assert multi_doc >= _MIN_MULTI_DOC, (
        f"GT-01: need >= {_MIN_MULTI_DOC} multi_doc records; got {multi_doc}."
    )
    assert refusal >= _MIN_REFUSAL, (
        f"GT-01: need >= {_MIN_REFUSAL} refusal records; got {refusal}."
    )


# --- Model-validator defense-in-depth gates (pass against seed) -------------


def test_citations_subset_of_golds(all_records: list[object]) -> None:
    """GT-02 (D-04): expected_citation_ids ⊆ gold_passage_ids for every record.

    Defense-in-depth beyond the EvalRecord model_validator — confirms the
    property holds on the loaded dataset, not just at construction time.
    """
    from docintel_eval.dataset import EvalRecord

    records: list[EvalRecord] = all_records  # type: ignore[assignment]
    for rec in records:
        gold_set = set(rec.gold_passage_ids)
        for cid in rec.expected_citation_ids:
            assert cid in gold_set, (
                f"Record {rec.id}: expected_citation_id {cid!r} is not in "
                f"gold_passage_ids {sorted(gold_set)!r}. "
                "D-04: citations must be a strict subset of gold passages."
            )


def test_refusal_fields_empty(all_records: list[object]) -> None:
    """GT-02 (D-05): refusal records must have both gold lists empty.

    Defense-in-depth beyond the EvalRecord model_validator — confirms the
    property holds on the loaded dataset.
    """
    from docintel_eval.dataset import EvalRecord

    records: list[EvalRecord] = all_records  # type: ignore[assignment]
    for rec in records:
        if rec.question_type == "refusal":
            assert rec.gold_passage_ids == [], (
                f"Record {rec.id}: refusal record has non-empty gold_passage_ids "
                f"{rec.gold_passage_ids!r}. D-05: refusal records must have gold_passage_ids=[]."
            )
            assert rec.expected_citation_ids == [], (
                f"Record {rec.id}: refusal record has non-empty expected_citation_ids "
                f"{rec.expected_citation_ids!r}. "
                "D-05: refusal records must have expected_citation_ids=[]."
            )


# --- Corpus resolution gates (the load-bearing test_gold_ids_resolve gate) --


def test_gold_ids_resolve(
    all_records: list[object], corpus_chunk_index: set[str]
) -> None:
    """GT-02 (T-08-03): every gold_passage_id must resolve to a real corpus chunk.

    This is the load-bearing gate that turns a typo'd or imagined chunk_id
    into a red test instead of a silent Phase 9 miss. Resolves against the
    session-scoped corpus_chunk_index built from committed chunk JSONL files.
    """
    from docintel_eval.dataset import EvalRecord

    records: list[EvalRecord] = all_records  # type: ignore[assignment]
    for rec in records:
        for cid in rec.gold_passage_ids:
            assert cid in corpus_chunk_index, (
                f"Record {rec.id}: gold_passage_id {cid!r} does not resolve to "
                f"any chunk in data/corpus/chunks/. Verify ticker, FY, item_code, "
                f"and ordinal are correct."
            )


def test_expected_citation_ids_resolve(
    all_records: list[object], corpus_chunk_index: set[str]
) -> None:
    """GT-02 (T-08-03): every expected_citation_id must resolve to a real corpus chunk.

    Second half of the load-bearing resolution check — both gold_passage_ids
    AND expected_citation_ids must point to real committed chunk_ids.
    """
    from docintel_eval.dataset import EvalRecord

    records: list[EvalRecord] = all_records  # type: ignore[assignment]
    for rec in records:
        for cid in rec.expected_citation_ids:
            assert cid in corpus_chunk_index, (
                f"Record {rec.id}: expected_citation_id {cid!r} does not resolve to "
                f"any chunk in data/corpus/chunks/. Verify ticker, FY, item_code, "
                f"and ordinal are correct."
            )


# --- Curation-coverage gates (xfail-strict) ---------------------------------


@pytest.mark.xfail(strict=True, reason="curation-volume gate — populated in Plans 02-04")
def test_refusal_flavor_coverage(all_records: list[object]) -> None:
    """GT-01 (D-17): dataset must cover all 5 refusal out-of-corpus flavors.

    The union of refusal-record tags must include all 5 D-17 flavor tags:
    absent-company, out-of-range-year, uncovered-topic, false-premise,
    unextracted-section.
    """
    from docintel_eval.dataset import EvalRecord

    records: list[EvalRecord] = all_records  # type: ignore[assignment]
    refusal_records = [r for r in records if r.question_type == "refusal"]
    covered_flavors: set[str] = set()
    for rec in refusal_records:
        covered_flavors |= set(rec.tags) & _REFUSAL_FLAVOR_TAGS
    missing = _REFUSAL_FLAVOR_TAGS - covered_flavors
    assert not missing, (
        f"D-17: refusal records must cover all 5 flavor tags. "
        f"Missing: {sorted(missing)!r}. "
        f"Covered so far: {sorted(covered_flavors)!r}."
    )


# --- Consistency gates (pass against seed: vacuously or positively) ---------


def test_long_gold_tag_consistent(
    all_records: list[object], corpus_chunk_tokens: dict[str, int]
) -> None:
    """D-15: 'long-gold' tag must be consistent with n_tokens > 449.

    Two-direction check:
    (1) If a record is tagged 'long-gold', at least one of its gold_passage_ids
        must have n_tokens > _LONG_GOLD_TOKEN_THRESHOLD.
    (2) Converse: if any gold chunk exceeds the threshold, the record must carry
        the 'long-gold' tag (so Phase 9 reports can separate truncation cases).

    Passes vacuously on the Wave-0 seed (no 'long-gold'-tagged records; seed's
    gold chunk n_tokens=402 ≤ 449).
    """
    from docintel_eval.dataset import EvalRecord

    records: list[EvalRecord] = all_records  # type: ignore[assignment]
    for rec in records:
        has_long_gold_tag = "long-gold" in rec.tags
        gold_token_counts = [
            corpus_chunk_tokens.get(gid, 0) for gid in rec.gold_passage_ids
        ]
        has_long_chunk = any(t > _LONG_GOLD_TOKEN_THRESHOLD for t in gold_token_counts)

        if has_long_gold_tag:
            assert has_long_chunk, (
                f"Record {rec.id}: tagged 'long-gold' but no gold chunk exceeds "
                f"{_LONG_GOLD_TOKEN_THRESHOLD} tokens. "
                f"Gold n_tokens: {gold_token_counts!r}. "
                "D-15: remove the 'long-gold' tag or verify the chunk token count."
            )
        if has_long_chunk:
            assert has_long_gold_tag, (
                f"Record {rec.id}: gold chunk exceeds {_LONG_GOLD_TOKEN_THRESHOLD} tokens "
                f"({max(gold_token_counts)} tokens) but missing 'long-gold' tag. "
                "D-15: add 'long-gold' tag so Phase 9 can separate truncation-affected cases."
            )


def test_refusal_sentinel_value(all_records: list[object]) -> None:
    """D-18: refusal gold_answer must be '' or the locked REFUSAL_TEXT_SENTINEL.

    Passes vacuously on Wave-0 seed (no refusal records yet). When refusal
    records are added in Plans 02-04, this gate enforces the planner's D-18
    decision: gold_answer is either empty or the canonical 63-char sentinel.
    """
    from docintel_eval.dataset import EvalRecord

    records: list[EvalRecord] = all_records  # type: ignore[assignment]
    for rec in records:
        if rec.question_type == "refusal":
            assert rec.gold_answer in ("", REFUSAL_TEXT_SENTINEL), (
                f"Record {rec.id}: refusal gold_answer must be '' or the locked "
                f"REFUSAL_TEXT_SENTINEL. Got {rec.gold_answer!r}. "
                "D-18: use the sentinel from docintel_core.types.REFUSAL_TEXT_SENTINEL."
            )


def test_no_fy2022_in_golds(all_records: list[object]) -> None:
    """D-08 (corpus correction): no gold_passage_id may reference FY2022.

    The corpus is FY2023–FY2025 only (D-08). Any FY2022 chunk_id is an error
    — it would resolve against no real corpus chunk and fail test_gold_ids_resolve.
    This regression gate catches the substring 'FY2022' in any gold ID directly.
    """
    from docintel_eval.dataset import EvalRecord

    records: list[EvalRecord] = all_records  # type: ignore[assignment]
    forbidden = f"FY{_FORBIDDEN_FY}"
    for rec in records:
        for gid in rec.gold_passage_ids:
            assert forbidden not in gid, (
                f"Record {rec.id}: gold_passage_id {gid!r} contains {forbidden!r}. "
                "D-08: the corpus covers FY2023–FY2025 only. "
                "Remove or replace this gold ID."
            )
