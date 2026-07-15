"""docintel-eval per-tier proof reporting (Story 3.8, FR-C9).

Reports eval numbers SEPARATELY for the open tier (BYO hosted provider key) and
the sealed tier (local-only / air-gapped models), side by side. Each tier's
numbers are produced by an ordinary ``docintel-eval run`` under that tier's
Settings (Story 3.5) — this module only COMBINES the resulting ``results.json``
files into one honest comparison. No metric math here.

FR-C9 / PRD RISK-2 honesty bar: sealed-tier numbers are published transparently
whatever they are — gated only to the no-fabrication bar, NEVER to open-tier
parity. The combined report labels each tier with its provider + representative
flag and never hides or clips a tier.

Additive: does not touch ``run_eval`` or any committed report bytes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from docintel_core.config import Settings

log = structlog.stdlib.get_logger(__name__)

__all__ = ["parse_tier_specs", "render_per_tier_markdown", "run_per_tier", "tier_row"]

_REPORTS_ROOT = Path("data/eval/reports")


def parse_tier_specs(specs: list[str]) -> list[tuple[str, Path]]:
    """Parse ``["open:data/eval/reports/AAA", "sealed:.../BBB"]`` into
    ``[(tier, report_dir), ...]``. Each report_dir is confined under
    ``data/eval/reports/`` (T-10-03 path-traversal guard). Raises ValueError on a
    malformed spec or an out-of-root path.
    """
    out: list[tuple[str, Path]] = []
    reports_root = _REPORTS_ROOT.resolve()
    for spec in specs:
        if ":" not in spec:
            raise ValueError(f"per-tier spec must be '<tier>:<report_dir>', got {spec!r}")
        tier, _, raw = spec.partition(":")
        tier = tier.strip()
        resolved = Path(raw.strip()).resolve()
        under = resolved == reports_root or reports_root in resolved.parents
        if not tier or not under:
            raise ValueError(f"per-tier spec {spec!r}: tier empty or path outside {reports_root}")
        out.append((tier, resolved))
    return out


def tier_row(tier: str, results: dict[str, Any]) -> dict[str, Any]:
    """Pull the headline row for one tier from its ``results.json`` dict. Missing
    fields degrade to ``None`` rather than raising — an incomplete report should
    still appear in the table, honestly labeled."""
    manifest = results.get("manifest", {})
    retrieval = results.get("retrieval", {})
    faithfulness = results.get("faithfulness", {})
    latency = results.get("latency", {})
    return {
        "tier": tier,
        "provider": manifest.get("provider"),
        "representative": manifest.get("representative"),
        "hit_at_5": retrieval.get("hit_at_5"),
        "faithfulness": faithfulness.get("faithfulness_pass_rate"),
        "faithfulness_ci": faithfulness.get("faithfulness_ci"),
        "p50_ms": latency.get("p50_ms"),
        "p95_ms": latency.get("p95_ms"),
        "cost_per_query_usd": latency.get("cost_per_query_usd"),
    }


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def render_per_tier_markdown(rows: list[dict[str, Any]]) -> str:
    """Render the per-tier comparison (FR-C9). Pure. Every tier appears; sealed is
    never hidden. Non-representative tiers are flagged inline."""
    lines: list[str] = ["# docintel Per-Tier Proof Report (FR-C9)", ""]
    lines += [
        "Numbers reported SEPARATELY per tier. Sealed-tier numbers are published "
        "transparently whatever they are (PRD RISK-2) — gated only to the no-fabrication "
        "bar, never to open-tier parity.",
        "",
        "| tier | provider | representative | Hit@5 | faithfulness | p50 ms | p95 ms | $/query |",
        "|------|----------|----------------|-------|--------------|--------|--------|---------|",
    ]
    for r in rows:
        lines.append(
            f"| {_fmt(r['tier'])} | {_fmt(r['provider'])} | {_fmt(r['representative'])} "
            f"| {_fmt(r['hit_at_5'])} | {_fmt(r['faithfulness'])} | {_fmt(r['p50_ms'])} "
            f"| {_fmt(r['p95_ms'])} | {_fmt(r['cost_per_query_usd'])} |"
        )
    non_rep = [r["tier"] for r in rows if not r.get("representative")]
    if non_rep:
        lines += [
            "",
            f"> NON-REPRESENTATIVE tiers (stub or non-real run): {', '.join(map(str, non_rep))}. "
            "These numbers are not publishable proof — run the tier with real models.",
        ]
    lines += [
        "",
        "_Each tier's numbers come from an independent `docintel-eval run` under that "
        "tier's Settings; this report only combines them._",
        "",
    ]
    return "\n".join(lines)


def run_per_tier(cfg: Settings, specs: list[str], *, output_dir: Path | None = None) -> int:
    """Combine per-tier ``results.json`` into one report. ``specs`` are
    ``<tier>:<report_dir>`` strings. Returns 0 on success, 1 on a bad spec/missing
    report."""
    try:
        parsed = parse_tier_specs(specs)
    except ValueError as exc:
        log.error("per_tier_bad_spec", error=str(exc))
        return 1

    rows: list[dict[str, Any]] = []
    for tier, report_dir in parsed:
        results_path = report_dir / "results.json"
        if not results_path.is_file():
            log.error("per_tier_missing_results", tier=tier, path=str(results_path))
            return 1
        results = json.loads(results_path.read_text(encoding="utf-8"))
        rows.append(tier_row(tier, results))

    ts = datetime.now(UTC)
    out_dir = output_dir or (Path("data/eval/per-tier") / ts.strftime("%Y%m%d_%H%M%S_%fZ"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "per-tier-report.md").write_text(render_per_tier_markdown(rows), encoding="utf-8")
    (out_dir / "per-tier.json").write_text(
        json.dumps({"tiers": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    log.info("per_tier_report_written", n_tiers=len(rows), output_dir=str(out_dir))
    return 0
