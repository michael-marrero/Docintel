"""Structural tests for the committed corpus layout (ING-01 + Pitfall 6).

Covers VALIDATION.md task 3-0X-08:

* ``data/corpus/companies.snapshot.csv`` exists with the expected header
  (D-01 + Pitfall 1 — ``fiscal_years`` is per-row, not a global pin).
* For every (ticker, year) in the snapshot, the raw / normalized / chunks
  files exist.
* ``data/corpus/.cache/`` is gitignored (Pitfall 6 — the SDK working
  directory is the only thing under ``data/corpus/`` that stays out
  of git).
* ``data/corpus/raw/``, ``data/corpus/normalized/``, ``data/corpus/chunks/``,
  ``MANIFEST.json``, and ``companies.snapshot.csv`` are NOT gitignored
  (the negation pattern from RESEARCH.md Pitfall 6 line 528-542).

Tests xfail until Plan 03-02 amends ``.gitignore`` and Wave 5 commits
the corpus artifacts.
"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CORPUS_DIR = _REPO_ROOT / "data" / "corpus"
_SNAPSHOT_CSV = _CORPUS_DIR / "companies.snapshot.csv"

_XFAIL = pytest.mark.xfail(
    raises=(
        ImportError,
        AttributeError,
        AssertionError,
        NotImplementedError,
        FileNotFoundError,
    ),
    strict=False,
    reason="awaits Plan 03-02 — .gitignore amend; awaits Wave 5 — corpus committed (ING-01)",
)

_EXPECTED_SNAPSHOT_HEADER = [
    "ticker",
    "name",
    "sector",
    "market_cap_usd",
    "fiscal_years",
    "snapshot_date",
]


@_XFAIL
def test_snapshot_csv_present() -> None:
    """``companies.snapshot.csv`` exists and carries the D-01 header (Pitfall 1 per-row years)."""
    assert _SNAPSHOT_CSV.is_file(), f"missing snapshot file: {_SNAPSHOT_CSV}"
    with _SNAPSHOT_CSV.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
    assert (
        header == _EXPECTED_SNAPSHOT_HEADER
    ), f"snapshot header drift — got {header!r}, expected {_EXPECTED_SNAPSHOT_HEADER!r}"


@_XFAIL
def test_committed_corpus_files_present() -> None:
    """For each (ticker, year) row, the raw / normalized / chunks files exist; MANIFEST too."""
    assert _SNAPSHOT_CSV.is_file(), f"missing snapshot file: {_SNAPSHOT_CSV}"
    with _SNAPSHOT_CSV.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert rows, "snapshot CSV has no data rows"

    for row in rows:
        ticker = row["ticker"]
        # Per-row fiscal years — Pitfall 1 — split on a separator that the
        # snapshot generator commits. We tolerate `;` (most common in CSVs
        # to avoid clashing with the column separator) and `,`.
        sep = ";" if ";" in row["fiscal_years"] else ","
        years = [y.strip() for y in row["fiscal_years"].split(sep) if y.strip()]
        for year in years:
            raw = _CORPUS_DIR / "raw" / ticker / f"FY{year}.html"
            normalized = _CORPUS_DIR / "normalized" / ticker / f"FY{year}.json"
            chunks = _CORPUS_DIR / "chunks" / ticker / f"FY{year}.jsonl"
            assert raw.is_file(), f"missing raw filing: {raw}"
            assert normalized.is_file(), f"missing normalized JSON: {normalized}"
            assert chunks.is_file(), f"missing chunks JSONL: {chunks}"

    assert (_CORPUS_DIR / "MANIFEST.json").is_file(), "missing MANIFEST.json"


def test_corpus_cache_gitignored() -> None:
    """``data/corpus/.cache/`` is gitignored AND the new Pitfall-6 negation is in place."""
    result = subprocess.run(
        [
            "git",
            "check-ignore",
            str(_REPO_ROOT / "data" / "corpus" / ".cache" / "sec-edgar-filings" / "foo"),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    # git check-ignore exits 0 when the path IS ignored.
    assert result.returncode == 0, (
        "data/corpus/.cache/ should be gitignored but check-ignore returned "
        f"{result.returncode}; stdout={result.stdout!r}"
    )
    # The Pitfall-6 specific negation block must be present in .gitignore —
    # the old wholesale ``data/corpus/`` pattern is too coarse for ING-04.
    # Until Plan 03-02 lands the amended .gitignore, this assertion fires
    # the xfail. Once the negation block ships, this test flips to green.
    gitignore = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "!data/corpus/raw/" in gitignore, (
        ".gitignore does not carry the Pitfall-6 negation block (data/corpus/raw/ "
        "must be re-included so committed filings are tracked)."
    )


def test_corpus_raw_not_gitignored() -> None:
    """Raw / normalized / chunks / MANIFEST / snapshot are tracked, not ignored."""
    tracked_paths = (
        _REPO_ROOT / "data" / "corpus" / "raw" / "AAPL" / "FY2024.html",
        _REPO_ROOT / "data" / "corpus" / "normalized" / "AAPL" / "FY2024.json",
        _REPO_ROOT / "data" / "corpus" / "chunks" / "AAPL" / "FY2024.jsonl",
        _REPO_ROOT / "data" / "corpus" / "MANIFEST.json",
        _REPO_ROOT / "data" / "corpus" / "companies.snapshot.csv",
    )
    for path in tracked_paths:
        result = subprocess.run(
            ["git", "check-ignore", str(path)],
            check=False,
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
        )
        # git check-ignore exits 1 when the path is NOT ignored.
        assert result.returncode == 1, (
            f"{path} should NOT be gitignored but check-ignore returned "
            f"{result.returncode}; stdout={result.stdout!r}"
        )
