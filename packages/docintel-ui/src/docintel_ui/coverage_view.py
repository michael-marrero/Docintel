"""Story 1.5 — pure rendering helpers for the browsable coverage view.

Kept separate from ``streamlit_app`` (like ``eval_view``/``citations``) so the
label + HTML builders are unit-testable without importing Streamlit. The values
here are built to the UX mockup ``screen-coverage.html`` (dark terminal, teal
accent, mono for tickers/counts). No Streamlit, no network — pure functions over
the ``/coverage`` payload.
"""

from __future__ import annotations

import html
from typing import Any

# Design tokens lifted from the UX mockup screen-coverage.html.
ACCENT = "#2DD4BF"
CARD = "#12161B"
RULE = "#1C2229"
INK = "#E6E8EB"
DIM = "#8B939C"
FAINT = "#5A626B"
MONO = "ui-monospace,'SF Mono',Menlo,Consolas,monospace"


def scope_label(corpus: dict[str, Any]) -> str:
    """`CORPUS · N FILERS · FY..-FY..` scope label (epics 1.5 AC-1)."""
    fy_min, fy_max = corpus.get("fy_min"), corpus.get("fy_max")
    span = f"FY{fy_min}-FY{fy_max}" if fy_min is not None and fy_max is not None else "—"
    return f"CORPUS · {corpus.get('company_count', 0)} FILERS · {span}"


def transcript_label(count: int) -> str:
    """UX-DR19: transcript availability as a count/text label, NOT a dot alone."""
    return f"{count} calls" if count else "none"


def status_html(corpus: dict[str, Any]) -> str:
    """The persistent corpus status indicator bar."""
    forms = html.escape(" / ".join(corpus.get("forms", [])) or "—")
    tr = " + EARNINGS TRANSCRIPTS" if corpus.get("has_transcripts") else ""
    fy_min, fy_max = corpus.get("fy_min"), corpus.get("fy_max")
    span = f"FY{fy_min}&ndash;FY{fy_max}" if fy_min is not None and fy_max is not None else "—"
    updated = html.escape(str(corpus.get("snapshot_date", "")))
    seg = f"padding-left:14px;border-left:1px solid {RULE};"
    return (
        f'<div style="display:flex;gap:14px;flex-wrap:wrap;background:{CARD};'
        f"border:1px solid {RULE};border-radius:4px;padding:12px 16px;"
        f'font-family:{MONO};font-size:11.5px;letter-spacing:.04em;color:{DIM};">'
        f'<span style="color:{INK};">● CORPUS</span>'
        f'<span style="{seg}"><b style="color:{INK};">{corpus.get("company_count", 0)}</b> FILERS</span>'
        f'<span style="{seg}">SEC <b style="color:{INK};">{forms}</b>{tr}</span>'
        f'<span style="{seg}"><b style="color:{INK};">{span}</b></span>'
        f'<span style="margin-left:auto;color:{FAINT};">UPDATED {updated}</span></div>'
    )


def table_html(rows: list[dict[str, Any]]) -> str:
    """The browsable coverage table (ticker, company, filing chips, period, transcript count)."""
    ths = "".join(
        f'<th style="text-align:left;font-family:{MONO};font-size:10px;letter-spacing:.12em;'
        f"text-transform:uppercase;color:{FAINT};padding:10px 14px;"
        f'border-bottom:1px solid {RULE};">{h}</th>'
        for h in ("Ticker", "Company", "Filings available", "Latest period", "Transcripts")
    )
    body = []
    for r in rows:
        counts = r.get("filing_counts") or {}
        if counts:
            chips = "".join(
                f'<span style="font-family:{MONO};font-size:9.5px;padding:2px 6px;border-radius:4px;'
                f'background:#0F1318;border:1px solid {RULE};color:{DIM};margin-right:5px;">'
                f"{html.escape(form)} &times;{int(cnt)}</span>"
                for form, cnt in counts.items()
            )
        else:
            declared = html.escape(" / ".join(r.get("forms", [])))
            chips = (
                f'<span style="font-family:{MONO};font-size:10px;color:{FAINT};">'
                f"declared: {declared} · not yet indexed</span>"
            )
        tcount = int(r.get("transcript_count", 0))
        tcolor = ACCENT if tcount else FAINT
        period = html.escape(str(r.get("latest_period") or "—"))
        body.append(
            f'<tr style="border-bottom:1px solid {RULE};">'
            f'<td style="padding:11px 14px;font-family:{MONO};font-size:12px;color:{INK};">'
            f'{html.escape(r["ticker"])}</td>'
            f'<td style="padding:11px 14px;"><span style="font-size:13px;color:{INK};'
            f'font-weight:500;">{html.escape(r["name"])}</span>'
            f'<span style="display:block;font-size:11px;color:{DIM};">'
            f'{html.escape(r.get("sector", ""))}</span></td>'
            f'<td style="padding:11px 14px;">{chips}</td>'
            f'<td style="padding:11px 14px;font-family:{MONO};font-size:11px;color:#C7CCD2;">{period}</td>'
            f'<td style="padding:11px 14px;font-family:{MONO};font-size:10.5px;color:{tcolor};">'
            f"{transcript_label(tcount)}</td></tr>"
        )
    return (
        f'<div style="background:{CARD};border:1px solid {RULE};border-radius:4px;'
        f'overflow:auto;margin-top:12px;"><table style="width:100%;border-collapse:collapse;">'
        f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )
