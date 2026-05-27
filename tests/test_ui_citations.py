"""Plan 13-01 Wave-0 xfail-strict scaffold for citation-badge rendering (UI-02; D-06/07/08).

Locks the citation-badge HTML contract AND the V5 output-encoding (HTML-escaping)
security control BEFORE 13-03 implements ``render_citation_badges``. Strict-xfail:
``docintel_ui.citations`` does not exist yet, so the in-body import raises
``ModuleNotFoundError`` at call time (NOT collection — the import is inside the
test, so collection still succeeds) and xfail-strict absorbs it. 13-03 ships the
pure ``render_citation_badges(answer) -> str`` helper (testable without a running
Streamlit server) and removes these markers.

Node ids bound by ``13-VALIDATION.md``: ``test_citation_badge_html``,
``test_citation_html_escaping``.
"""

from __future__ import annotations

import pytest

from docintel_core.types import Answer, Citation

_XFAIL_REASON = "Implemented in 13-03 (render_citation_badges helper)"


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


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
def test_citation_badge_html() -> None:
    """D-06/07/08 — each citation renders as a numbered ``<abbr title="...">[N]</abbr>`` badge."""
    from docintel_ui.citations import render_citation_badges

    html = render_citation_badges(
        _answer_with_citation("Apple cites supply risk.[1]", "A self-contained excerpt.")
    )
    assert "<abbr title=" in html, f"badge must be an abbr-title element: {html!r}"
    assert "[1]" in html, f"badge must be the numbered marker [1]: {html!r}"


@pytest.mark.xfail(strict=True, reason=_XFAIL_REASON)
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
