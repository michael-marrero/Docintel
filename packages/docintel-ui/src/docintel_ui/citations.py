"""Pure citation-rendering helpers for the docintel Query tab (UI-02; D-06/07/08/09).

Renders ``Answer.citations`` into inline numbered ``<abbr title="...">[N]</abbr>``
badges so the Streamlit Query tab gets a hover-revealed excerpt + company +
section without any JavaScript. Also produces the always-visible "Sources" list
that lives below the answer (D-09) so the citations stay readable even when a
hover is not captured in the recruiter GIF.

Module split rationale (Plan 13-03 boundary): this file imports NO ``streamlit``
and reads NO environment variables (FND-11 — env reads live in
``docintel_core.config.Settings`` only). It is a pure, importable-on-its-own
helper so it is unit-testable WITHOUT a running Streamlit server (the contract
bound by ``tests/test_ui_citations.py`` since Wave 0 / Plan 13-01). The
Streamlit Query tab in ``streamlit_app.py`` consumes ``render_citation_badges``
and ``build_sources_list`` via ``st.markdown(..., unsafe_allow_html=True)``.

Security (V5 output encoding — T-13-01, the one real HIGH threat of Phase 13):
the ``title`` attribute of each ``<abbr>`` contains SEC 10-K prose that
legitimately includes ``&`` (e.g. "R&D"), ``"`` (e.g. quoted guidance), and
``<`` / ``>`` (e.g. "revenue < prior year"). Failing to escape would let the
excerpt break out of the attribute and inject markup into the rendered page.
``_html_escape`` defers to ``html.escape(..., quote=True)`` which encodes
``& < > "`` (and ``'``, harmless inside a double-quoted attribute) in the
correct order (ampersand first to avoid double-escaping). This is the bind
point for the ``test_citation_html_escaping`` red-test (Plan 13-01 scaffold).

Chunk-id replacement (RESEARCH Pitfall + Plan 13-03 read_first):
``Answer.text`` may carry citation markers in TWO equivalent forms — bare
``[chunk_id]`` tokens (Phase 7 ``Answer.from_generation_result`` strips the
pipe-delimited header form, so the stub generator emits the bare-id form per
Plan 06-05) OR bare ``[N]`` numbered markers (1-indexed; what a downstream
post-processor or hand-written answer might produce, and what the Wave 0
``test_citation_badge_html`` contract uses). The replacement is a SINGLE pass
per token form: build a ``chunk_id -> badge_html`` map and a ``[N] ->
badge_html`` map, iterate once with ``str.replace``. This avoids the
double-replacement bug where one badge's HTML could overlap with another
chunk_id substring. When the answer text contains NEITHER form, the badges
are appended to the end (space-separated) so the recruiter GIF still shows
discoverable hover badges — the Sources list (D-09) is the always-visible
fallback either way.

Confidence/cost rendering: NOT this module's job — the Streamlit tab owns the
confidence badge and the cost/latency meter (D-03). This module owns citations
only (D-06/07/08/09).
"""

from __future__ import annotations

import html

from docintel_core.types import Answer, Citation

__all__ = ["build_sources_list", "render_citation_badges"]


# Length budget for the hover excerpt — long enough to surface context for a
# multi-hop comparative read, short enough to fit a native browser tooltip
# (which has no scroll affordance). RESEARCH Focus Area 1 recommends ~300.
_HOVER_EXCERPT_CHARS = 300

# Length budget for the always-visible Sources list excerpt (D-09). Shorter
# than the hover budget so the list reads as a scannable index, not a
# wall-of-text duplicate of the answer.
_SOURCES_EXCERPT_CHARS = 200


def _html_escape(s: str) -> str:
    """Escape ``& < > "`` for safe insertion into an HTML attribute value.

    Defers to the stdlib ``html.escape(s, quote=True)``:

    * ``quote=True`` encodes the double-quote (``&quot;``) — required because
      the surrounding attribute is double-quoted. Single-quote is also encoded
      (``&#x27;``); over-escaping it is harmless inside a double-quoted
      attribute.
    * The stdlib runs ampersand FIRST internally so that a literal ``&`` in
      the input does not get re-encoded to ``&amp;amp;`` after a subsequent
      ``<`` → ``&lt;`` step (Pitfall 4 in 13-RESEARCH.md).

    The four-escape contract bound by ``test_citation_html_escaping``:
    ``& → &amp;``, ``< → &lt;``, ``> → &gt;``, ``" → &quot;``.
    """
    return html.escape(s, quote=True)


def _badge_html(index: int, citation: Citation) -> str:
    """Build one ``<abbr title="...">[N]</abbr>`` badge.

    The title is a header line ("Company · Item N[X]: Title") followed by a
    newline and the first ~300 chars of the excerpt. Newline-in-title-attribute
    is rendered by browsers as a soft break in the tooltip (HTML attribute
    values are allowed to contain newlines).

    The ``style="..."`` carries the cursor + dotted-underline so the badge is
    visually discoverable as hover-able. If Streamlit's markdown sanitizer
    strips the ``style`` attribute (RESEARCH Open Question 1), the badge still
    works semantically — it just loses the dotted underline.
    """
    section = f"{citation.item_code}: {citation.item_title}"
    # Collapse ALL whitespace BEFORE escaping. The 10-K excerpt carries `\n\n`
    # paragraph breaks; a blank line inside the title attribute breaks Streamlit's
    # markdown->HTML block rendering — it splits the <abbr> tag at the blank line,
    # leaking the raw `<abbr title=... style=...>` markup onto the page (the bug
    # seen in the hero demo). Flattening to one line renders as a clean tooltip.
    raw_title = f"[{citation.company} · {section}] {citation.text[:_HOVER_EXCERPT_CHARS]}"
    title_value = _html_escape(" ".join(raw_title.split()))
    return (
        f'<abbr title="{title_value}" '
        f'style="cursor:help; text-decoration:none; '
        f'border-bottom:1px dotted #888;">'
        f"[{index}]"
        f"</abbr>"
    )


def render_citation_badges(answer: Answer) -> str:
    """Return ``answer.text`` with citation markers replaced by numbered badges.

    For each citation (1-indexed), build a single ``<abbr title="...">[N]</abbr>``
    badge with an HTML-escaped tooltip carrying the company, section, and the
    first ~300 chars of the excerpt. Then walk the citations once and replace
    BOTH supported marker forms in ``answer.text`` with the matching badge:

    * ``[chunk_id]`` — bare-chunk-id form (Phase 6 stub generator output, the
      ``Answer.from_generation_result`` post-strip shape).
    * ``[N]`` — bare 1-indexed numeric form (what a downstream renderer or a
      hand-written demo answer uses, and what the Wave 0 contract uses).

    Single-pass replacement (RESEARCH Pitfall — chunk_id marker replacement):
    each token is replaced by its rendered badge in one ``str.replace`` per
    form per citation, so we never re-visit already-rendered HTML. After the
    replacements, if NEITHER token form was found in the answer text, the
    badges are appended at the end (space-separated) so the recruiter GIF
    still shows discoverable hover affordances; the Sources list (D-09) is
    the always-visible fallback either way.

    Answers with zero citations return the answer text unchanged.

    Args:
        answer: a fully-constructed Phase 7 ``Answer``. ``answer.refused=True``
            answers carry no citations by construction; this function returns
            ``answer.text`` (the refusal sentinel) unchanged.

    Returns:
        An HTML string safe to pass to ``st.markdown(..., unsafe_allow_html=True)``.
        The ``title`` content of every ``<abbr>`` is HTML-escaped (V5 / T-13-01).
    """
    if not answer.citations:
        return answer.text

    badges: list[tuple[int, str, str]] = [
        (index, citation.chunk_id, _badge_html(index, citation))
        for index, citation in enumerate(answer.citations, start=1)
    ]

    # Two-pass placeholder substitution (closes CR-02 from 13-REVIEW.md):
    # a citation excerpt can legitimately contain a later citation's marker
    # token (e.g. citation 1's excerpt says "see [2]"). With single-pass
    # ``str.replace``, replacing "[2]" then re-enters the already-rendered
    # badge HTML of citation 1 (the excerpt now lives inside ``<abbr
    # title="..."``), corrupting it. The pass-1 substitution swaps markers
    # for NUL-bracketed placeholders that ``html.escape`` leaves untouched
    # and that cannot legally appear in SEC 10-K prose; pass-2 swaps each
    # placeholder for its rendered badge. Because pass-2 inserts the badge
    # HTML only AFTER all marker tokens have been replaced with safe
    # placeholders, no badge's HTML can ever overlap a later citation's
    # marker. NUL (0x00) is not escaped by ``html.escape`` (it is preserved
    # verbatim), so the placeholder boundaries survive escaping unchanged.
    rendered = answer.text
    any_marker_replaced = False
    placeholders: list[tuple[str, str]] = []
    for index, chunk_id, badge in badges:
        chunk_id_token = f"[{chunk_id}]"
        numeric_token = f"[{index}]"
        placeholder = f"\x00CITE-{index}\x00"
        if chunk_id_token in rendered:
            rendered = rendered.replace(chunk_id_token, placeholder)
            placeholders.append((placeholder, badge))
            any_marker_replaced = True
        elif numeric_token in rendered:
            rendered = rendered.replace(numeric_token, placeholder)
            placeholders.append((placeholder, badge))
            any_marker_replaced = True

    # Pass 2: placeholders → badge HTML. Order doesn't matter because each
    # placeholder is unique (CITE-{index}) and contains the NUL byte, which
    # cannot collide with any badge HTML emitted by ``_badge_html``.
    for placeholder, badge in placeholders:
        rendered = rendered.replace(placeholder, badge)

    if not any_marker_replaced:
        # No markers in text — append badges so the inline hover affordance
        # is still present (and the Sources list, D-09, is the always-visible
        # readable fallback).
        trailing = " ".join(badge for _, _, badge in badges)
        rendered = f"{rendered} {trailing}" if rendered else trailing
    return rendered


def build_sources_list(answer: Answer) -> list[str]:
    """Return the D-09 Sources list — one Markdown line per citation.

    Each entry is ``**[N]** Company · Item N[X]: Title  \\n*excerpt...*``,
    matching the recruiter-skim shape called out in RESEARCH Focus Area 1.
    The excerpt is truncated to ``_SOURCES_EXCERPT_CHARS`` (200) and a
    trailing ellipsis is added if the underlying text was longer.

    This output is plain Markdown — NOT HTML — so it is rendered safely by
    ``st.markdown`` without ``unsafe_allow_html``. (The escapes in
    ``render_citation_badges`` are required because the title attribute is
    HTML; Markdown text content does not need the same treatment, though
    callers MAY still escape if they expect raw HTML in the excerpt.)

    Answers with zero citations return an empty list — callers can then
    skip rendering the Sources header entirely.
    """
    if not answer.citations:
        return []

    entries: list[str] = []
    for index, citation in enumerate(answer.citations, start=1):
        excerpt = citation.text[:_SOURCES_EXCERPT_CHARS]
        ellipsis = "..." if len(citation.text) > _SOURCES_EXCERPT_CHARS else ""
        section = f"{citation.item_code}: {citation.item_title}"
        entries.append(f"**[{index}]** {citation.company} · {section}  \n*{excerpt}{ellipsis}*")
    return entries
