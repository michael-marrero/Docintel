"""Tests for ``docintel_ingest.normalize`` — HTML → NormalizedFiling JSON.

Covers VALIDATION.md task 3-0X-03 (ING-02): the sample fixture HTML in
``tests/fixtures/sample_10k/aapl_FY2024_trimmed.html`` normalizes to the
committed golden JSON at ``aapl_FY2024_normalized.json`` (sans
``fetched_at`` and ``raw_path``, per RESEARCH.md anti-pattern line 428
and the path-stamping convention documented in Plan 03-05). Also asserts:

* The ``<table>`` element is dropped (D-08, ``manifest.tables_dropped >= 1``).
* The ``<ix:nonNumeric>`` wrapper prose survives normalization
  (Pitfall §424 — unwrap, do not decompose; here selectolax preserves
  inner text of unknown tags naturally).
* Every section key matches the ``Item N[X]`` D-14 canonical format.

Wave 3 (Plan 03-05) ships ``normalize_html`` and regenerates the golden
JSON from real normalizer output; the xfail markers are flipped in the
same commit that lands ``normalize.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_SAMPLE_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_10k"


def test_normalize_golden_matches() -> None:
    """Sample HTML → NormalizedFiling matches committed golden JSON (sans fetched_at, raw_path)."""
    from docintel_ingest.normalize import normalize_html

    html = (_SAMPLE_DIR / "aapl_FY2024_trimmed.html").read_text(encoding="utf-8")
    expected = json.loads(
        (_SAMPLE_DIR / "aapl_FY2024_normalized.json").read_text(encoding="utf-8")
    )
    # The placeholder marker key is stripped by Plan 03-05 when regenerating;
    # tolerate its absence here (it should not be present after regeneration).
    expected.pop("_comment", None)
    # The golden fixture stamps ``raw_path`` to the fixture path for clarity;
    # ``normalize_html`` writes the production path. The golden also stamps
    # ``fetched_at`` to a fixed sentinel because timestamps vary per run.
    # Exclude both fields from the golden comparison — they are sidecar
    # metadata, not section content.
    expected.pop("raw_path", None)
    expected.pop("fetched_at", None)

    actual = normalize_html(
        html,
        ticker="AAPL",
        fiscal_year=2024,
        accession="0000320193-24-000123",
    )

    # ``fetched_at`` varies per run; exclude per RESEARCH.md anti-pattern line 428.
    # ``raw_path`` is also excluded (see comment above on the golden side).
    assert actual.model_dump(exclude={"fetched_at", "raw_path"}) == expected


def test_tables_dropped() -> None:
    """The fixture's one ``<table>`` is dropped; ``manifest.tables_dropped >= 1`` (D-08)."""
    from docintel_ingest.normalize import normalize_html

    html = (_SAMPLE_DIR / "aapl_FY2024_trimmed.html").read_text(encoding="utf-8")
    result = normalize_html(
        html,
        ticker="AAPL",
        fiscal_year=2024,
        accession="0000320193-24-000123",
    )
    assert result.manifest.tables_dropped >= 1


def test_ix_nonNumeric_prose_preserved() -> None:
    """``<ix:nonNumeric>`` inner text survives normalization (Pitfall §424 — unwrap not decompose)."""
    from docintel_ingest.normalize import normalize_html

    html = (_SAMPLE_DIR / "aapl_FY2024_trimmed.html").read_text(encoding="utf-8")
    result = normalize_html(
        html,
        ticker="AAPL",
        fiscal_year=2024,
        accession="0000320193-24-000123",
    )
    # The fixture's ix:nonNumeric wrapper contains the canary phrase below.
    canary = "this is the prose the canary is testing"
    assert canary.lower() in result.sections["Item 1A"].lower()


def test_normalized_sections_keys_format() -> None:
    """Every section key matches the D-14 ``Item N[X]`` canonical form."""
    from docintel_ingest.normalize import normalize_html

    html = (_SAMPLE_DIR / "aapl_FY2024_trimmed.html").read_text(encoding="utf-8")
    result = normalize_html(
        html,
        ticker="AAPL",
        fiscal_year=2024,
        accession="0000320193-24-000123",
    )
    pattern = re.compile(r"^Item \d+[A-C]?$")
    for key in result.sections:
        assert pattern.match(key), f"non-canonical section key: {key!r}"
