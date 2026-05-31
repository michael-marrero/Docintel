"""Plan 13-03 (de-xfailed from Plan 13-01 Wave-0 scaffold) — citation-badge rendering (UI-02; D-06/07/08).

Locks the citation-badge HTML contract AND the V5 output-encoding (HTML-escaping)
security control. 13-03 shipped ``packages/docintel-ui/src/docintel_ui/citations.py``
with the pure ``render_citation_badges(answer) -> str`` helper (testable without a
running Streamlit server); the xfail-strict markers were swept in-wave when the
helper went green (a passing xfail-strict is an XPASS that fails the suite).

Node ids bound by ``13-VALIDATION.md``: ``test_citation_badge_html``,
``test_citation_html_escaping``.
"""

from __future__ import annotations

from docintel_core.types import Answer, Citation


def _answer_with_citation(text: str, excerpt: str) -> Answer:
    """Build a real (frozen, validated) ``Answer`` carrying exactly one ``Citation``."""
    return Answer(
        text=text,
        citations=[
            Citation(
                chunk_id="AAPL-FY2024-Item-1A-007",
                company="Apple Inc.",
                fiscal_year=2024,
                item_code="Item 1A",
                item_title="Risk Factors",
                text=excerpt,
                char_span_in_section=(0, len(excerpt)),
            )
        ],
        confidence="high",
        refused=False,
        prompt_version_hash="deadbeef0000",
    )


def test_citation_badge_html() -> None:
    """D-06/07/08 — each citation renders as a numbered ``<abbr title="...">[N]</abbr>`` badge."""
    from docintel_ui.citations import render_citation_badges

    html = render_citation_badges(
        _answer_with_citation("Apple cites supply risk.[1]", "A self-contained excerpt.")
    )
    assert "<abbr title=" in html, f"badge must be an abbr-title element: {html!r}"
    assert "[1]" in html, f"badge must be the numbered marker [1]: {html!r}"


def test_citation_html_escaping() -> None:
    """Security V5 (T-13-01) — dangerous chars in the excerpt are HTML-escaped in the title.

    The hover tooltip injects the excerpt into an ``abbr title="..."`` attribute
    via ``unsafe_allow_html``; ``& < > "`` MUST be escaped (``&amp; &lt; &gt;
    &quot;``) so the excerpt cannot break out of the attribute or inject markup.
    """
    from docintel_ui.citations import render_citation_badges

    dangerous = 'R&D rose; "guidance" < prior > target'
    html = render_citation_badges(_answer_with_citation("Margins fell.[1]", dangerous))
    assert "&amp;" in html and "&lt;" in html and "&gt;" in html and "&quot;" in html, (
        f"all four of & < > \" must be HTML-escaped in the rendered output: {html!r}"
    )
    assert dangerous not in html, "the raw, unescaped excerpt must NOT appear in the HTML"


def test_citation_marker_collision_does_not_corrupt_earlier_badge() -> None:
    """CR-02 regression (13-REVIEW.md): citation 1's excerpt may contain ``[2]``.

    Single-pass ``str.replace`` would later replace ``[2]`` inside citation 1's
    already-rendered ``<abbr title="...">`` (since ``html.escape`` doesn't escape
    ``[``/``]``), mangling the earlier badge. The two-pass placeholder
    substitution closes this: citation 1's rendered badge must survive
    citation 2's marker pass intact.

    Concrete shape of the bug: the rendered HTML must contain exactly ONE opening
    ``<abbr`` for citation 1 — the previous implementation produced a corrupted
    string where citation 2's ``<abbr ...>[2]</abbr>`` was substituted INTO
    citation 1's ``title`` attribute, breaking the attribute boundary.
    """
    from docintel_ui.citations import render_citation_badges

    answer = Answer(
        text="First claim [1]. Second claim [2].",
        citations=[
            Citation(
                chunk_id="cite-001",
                company="Apple Inc.",
                fiscal_year=2024,
                item_code="Item 1A",
                item_title="Risk Factors",
                # citation 1's excerpt CONTAINS the literal token "[2]" — the
                # trigger for the CR-02 corruption bug.
                text="Per cross-reference, see [2] for related disclosures.",
                char_span_in_section=(0, 50),
            ),
            Citation(
                chunk_id="cite-002",
                company="Apple Inc.",
                fiscal_year=2024,
                item_code="Item 7",
                item_title="MD&A",
                text="Independent risk excerpt.",
                char_span_in_section=(0, 25),
            ),
        ],
        confidence="high",
        refused=False,
        prompt_version_hash="deadbeef0000",
    )
    html = render_citation_badges(answer)

    # The rendered text should contain exactly two opening <abbr tags — one per
    # citation, neither corrupted by the other's marker substitution.
    assert html.count("<abbr ") == 2, (
        f"two citations must produce exactly two badges, not more, not nested: {html!r}"
    )
    # The numeric marker [2] in citation 1's excerpt should be HTML-escape-safe
    # (it appears verbatim inside the title attribute) and must NOT have been
    # replaced by citation 2's badge HTML.
    assert "<abbr" not in html.split('">[1]</abbr>')[0].split("title=\"")[1], (
        f"citation 1's title attribute must not contain any nested <abbr> "
        f"(would indicate citation 2's badge was injected into it): {html!r}"
    )
    # Both numbered markers must end up as outermost-rendered badges.
    assert ">[1]</abbr>" in html and ">[2]</abbr>" in html, (
        f"both [1] and [2] markers must render as complete badges: {html!r}"
    )
