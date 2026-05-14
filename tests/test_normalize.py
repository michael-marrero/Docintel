"""Tests for ``docintel_ingest.normalize`` — HTML → NormalizedFiling JSON.

Covers VALIDATION.md task 3-0X-03 (ING-02): the sample fixture HTML in
``tests/fixtures/sample_10k/aapl_FY2024_trimmed.html`` normalizes to the
committed golden JSON at ``aapl_FY2024_normalized.json`` (sans
``fetched_at``, per RESEARCH.md anti-pattern line 428). Also asserts:

* The ``<table>`` element is dropped (D-08, ``manifest.tables_dropped >= 1``).
* The ``<ix:nonNumeric>`` wrapper prose survives normalization
  (Pitfall §424 — unwrap, do not decompose).
* Every section key matches the ``Item N[X]`` D-14 canonical format.

The tests xfail until Wave 3 ships ``normalize_html``. The golden JSON
itself is a placeholder in Plan 03-01 (Wave 3 regenerates it from real
output and commits the bytes in the same wave-flip commit that removes
these xfail markers).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_SAMPLE_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_10k"

_XFAIL = pytest.mark.xfail(
    raises=(ImportError, AttributeError, AssertionError, NotImplementedError, FileNotFoundError),
    strict=False,
    reason="awaits Wave 3 — normalize_html + regenerated golden JSON (ING-02)",
)


@_XFAIL
def test_normalize_golden_matches() -> None:
    """Sample HTML → NormalizedFiling matches committed golden JSON (sans fetched_at)."""
    from docintel_ingest.normalize import normalize_html

    html = (_SAMPLE_DIR / "aapl_FY2024_trimmed.html").read_text(encoding="utf-8")
    expected = json.loads((_SAMPLE_DIR / "aapl_FY2024_normalized.json").read_text(encoding="utf-8"))
    # The placeholder marker key is stripped by Wave 3 when regenerating; ignore here.
    expected.pop("_comment", None)

    actual = normalize_html(
        html,
        ticker="AAPL",
        fiscal_year=2024,
        accession="0000320193-24-000123",
    )

    # ``fetched_at`` varies per run; exclude per RESEARCH.md anti-pattern line 428.
    assert actual.model_dump(exclude={"fetched_at"}) == expected


@_XFAIL
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


@_XFAIL
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


@_XFAIL
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
