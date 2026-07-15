"""Structured company brief (Story 2.2) — the largest NEW build of Epic 2.

A brief is FOUR section-scoped, independently-cited syntheses over ONE company's
filings, reusing the existing retrieve→rerank→synthesize→cite pipeline once per
section (FR-B7, AD-9) — not a new RAG mechanism. Each section calls
``Generator.generate(query, ticker=…)`` so retrieval is ticker-scoped and the
answer carries inline ``[chunk_id]`` citations, refusal, and confidence exactly
as the Q&A path does. No new prompt: ``SYNTHESIS_PROMPT`` (already in
``prompts.py``, hashed) drives it (AC-3); the section intents below are data
queries, not instructional prompts, so ``PROMPT_VERSION_HASH`` is unchanged.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, NamedTuple

from docintel_core.types import Answer


class BriefSection(NamedTuple):
    """One brief section: a stable key, a display title, and the retrieval query
    (``{company}`` is filled with the company name)."""

    key: str
    title: str
    query: str


# The four sections of a company brief (FR-B1). "Concisely" + a small k keep the
# brief bounded to ~1-2 screens, not a full report. These are DATA queries, not
# prompts — the instructional prompt is SYNTHESIS_PROMPT.
BRIEF_SECTIONS: tuple[BriefSection, ...] = (
    BriefSection(
        "business_moat",
        "Business & moat",
        "Summarize {company}'s core business, segments, and competitive moat, concisely.",
    ),
    BriefSection(
        "financial_trajectory",
        "Financial trajectory",
        "Summarize {company}'s recent revenue, margin, and cash-flow trajectory, concisely.",
    ),
    BriefSection(
        "risk_factors",
        "Risk factors",
        "Summarize the principal risk factors {company} discloses, concisely.",
    ),
    BriefSection(
        "recent_events",
        "Recent material events",
        "Summarize {company}'s recent material events — acquisitions, buybacks, "
        "legal proceedings — concisely.",
    ),
)


class BriefSectionResult(NamedTuple):
    """A rendered brief section: its metadata + the cited ``Answer``."""

    index: int
    key: str
    title: str
    answer: Answer


def generate_brief(
    generator: Any, ticker: str, company_name: str, k: int = 5
) -> Iterator[BriefSectionResult]:
    """Yield each brief section as it is generated (lazy — drives SSE streaming).

    Each section is retrieval-scoped to ``ticker`` (so a brief on NWL cites only
    NWL) and synthesized with inline citations. A section whose retrieval starves
    (no ticker passages) yields a refused ``Answer`` — an honest "not in the
    filings", never a fabricated section — while the other sections still render.
    """
    for index, section in enumerate(BRIEF_SECTIONS):
        query = section.query.format(company=company_name)
        gr = generator.generate(query, k=k, ticker=ticker)
        yield BriefSectionResult(
            index=index,
            key=section.key,
            title=section.title,
            answer=Answer.from_generation_result(gr),
        )
