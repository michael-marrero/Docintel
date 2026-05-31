#!/usr/bin/env python3
"""Phase 14 EMP-02 / D-10: paste real numbers from baseline.json into README.

Reads ``data/eval/baseline.json`` (locked by ``make baseline-lock`` per D-08),
follows the ``report_dir`` pointer to ``<report_dir>/results.json``, and
rewrites the ``<!-- PASTE-REAL-NUMBERS: ... <!-- END-PASTE-REAL-NUMBERS -->``
anchor block in ``README.md`` with the real headline metrics + a
``representative: true`` honest-disclosure note.

CONTEXT.md D-10 (mechanical, deferred to plan) recommends a helper over a
hand-edit or sed-in-Makefile (Pitfall 4: sed across multi-line HTML-comment
anchors is fragile). This helper uses ``re.sub(..., flags=re.DOTALL, count=1)``
so the replacement is auditable and the regex is anchored on the
HTML-comment markers that survive markdown rendering.

Per Pitfall 5, this helper does NOT touch ``packages/docintel-ui/`` — the
Streamlit Eval-Results tab auto-flips on disk-read at
``packages/docintel-ui/src/docintel_ui/eval_view.py:128-137`` once a
``representative: true`` report directory is on disk.

Usage::

    uv run python scripts/readme_paste.py
    uv run python scripts/readme_paste.py --baseline data/eval/baseline.json
    uv run python scripts/readme_paste.py --dry-run   # preview only

Wired to ``make readme-paste`` per the EMP-02 user-owned sequence in
``docs/REAL-RUN-CHECKLIST.md``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Final

# Anchor pattern (multi-line HTML comments around the real-numbers block).
# CONTEXT.md D-10 + 14-PATTERNS.md "MODIFY README.md" — the anchors exist
# verbatim at README.md:42-77 today.
_ANCHOR_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"<!-- PASTE-REAL-NUMBERS:.*?<!-- END-PASTE-REAL-NUMBERS -->",
    flags=re.DOTALL,
)


def _fmt_ci(ci: list[float] | None) -> str:
    """Format a 95% Wilson CI tuple as '[lo, hi]' (3-decimal-place rounding)."""
    if ci is None or len(ci) != 2:
        return "—"
    return f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def _build_replacement_block(
    baseline: dict[str, Any],
    results: dict[str, Any],
) -> str:
    """Format the new headline-metrics block per the README.md anchor structure.

    Reads the 7 D-07 baseline.json fields + the report's retrieval +
    faithfulness + latency sections. Mirrors the existing
    ``README.md:42-77`` table shape exactly so the diff is small.

    Raises:
        KeyError: with a clear message naming the missing key.
    """
    try:
        locked_at: str = baseline["locked_at"]
        git_sha: str = baseline["git_sha"]
        report_dir: str = baseline["report_dir"]
    except KeyError as exc:
        raise KeyError(
            f"baseline.json missing required field: {exc.args[0]!r} "
            f"(D-07 schema: report_dir, git_sha, eval_set_sha256, "
            f"prompt_version_hash, phase_locked, cost_usd, locked_at)"
        ) from exc

    short_sha: str = git_sha[:12]

    try:
        manifest: dict[str, Any] = results["manifest"]
        retrieval: dict[str, Any] = results["retrieval"]
        faithfulness: dict[str, Any] = results["faithfulness"]
        latency: dict[str, Any] = results["latency"]
    except KeyError as exc:
        raise KeyError(
            f"{report_dir}results.json missing top-level section: {exc.args[0]!r} "
            f"(expected: manifest, retrieval, faithfulness, latency)"
        ) from exc

    try:
        run_ts: str = manifest["run_timestamp_utc"]
        n_questions: int = manifest["n_questions"]
        hit5: float = retrieval["hit_at_5"]
        hit5_ci: list[float] = retrieval["hit_at_5_ci"]
        hit3: float = retrieval["hit_at_3"]
        hit3_ci: list[float] = retrieval["hit_at_3_ci"]
        mrr: float = retrieval["mrr"]
        faith_pass: float = faithfulness["faithfulness_pass_rate"]
        faith_ci: list[float] = faithfulness["faithfulness_ci"]
        p50_ms: float = latency["p50_ms"]
        p95_ms: float = latency["p95_ms"]
        cost_per_q: float = latency["cost_per_query_usd"]
    except KeyError as exc:
        raise KeyError(
            f"{report_dir}results.json missing metric: {exc.args[0]!r}"
        ) from exc

    # Build the markdown block. Keep the headline-metrics table shape identical
    # to the existing README.md:51-61 stub block — only the values change.
    lines: list[str] = [
        f"<!-- PASTE-REAL-NUMBERS: real numbers from baseline.json @ {locked_at} (git_sha={short_sha}) -->",
        f"> **`representative: true` — real-mode measurements**",
        f"> from the v1.0 baseline run committed at {run_ts}",
        f"> (`{report_dir}`, locked via `make baseline-lock`).",
        "",
        f"**Headline metrics (real-mode, n={n_questions}):**",
        "",
        "| Metric                | Value | 95% Wilson CI    |",
        "| --------------------- | ----- | ---------------- |",
        f"| Hit@5                 | {hit5:.3f} | {_fmt_ci(hit5_ci)}   |",
        f"| Hit@3                 | {hit3:.3f} | {_fmt_ci(hit3_ci)}   |",
        f"| MRR                   | {mrr:.3f} | —                |",
        f"| Faithfulness (pass)   | {faith_pass:.3f} | {_fmt_ci(faith_ci)}   |",
        f"| Latency p50           | {p50_ms:.1f} ms   | — |",
        f"| Latency p95           | {p95_ms:.1f} ms   | — |",
        f"| $/query               | ${cost_per_q:.6f} | — |",
        "",
        "<!-- END-PASTE-REAL-NUMBERS -->",
    ]
    return "\n".join(lines)


def main(args: argparse.Namespace) -> int:
    """Read baseline + results, rewrite the README anchor block atomically.

    Returns 0 on success, 1 on missing-field errors with a clear error
    message naming the missing key. Per CONTEXT.md D-10, never crashes
    silently — the user owns the trigger so the error must be actionable.
    """
    repo_root = Path(args.repo_root).resolve()
    baseline_path = (repo_root / args.baseline) if not Path(args.baseline).is_absolute() else Path(args.baseline)

    if not baseline_path.is_file():
        print(
            f"FAIL: {baseline_path} not found "
            f"(run `make baseline-lock TS=<ts>` first per D-08)",
            file=sys.stderr,
        )
        return 1

    try:
        baseline: dict[str, Any] = json.loads(baseline_path.read_text("utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: {baseline_path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    report_dir_field = baseline.get("report_dir")
    if not isinstance(report_dir_field, str):
        print(
            "FAIL: baseline.json missing or malformed 'report_dir' "
            "(D-07: must be a string like 'data/eval/reports/<ts>/')",
            file=sys.stderr,
        )
        return 1

    results_path = repo_root / report_dir_field / "results.json"
    if not results_path.is_file():
        print(
            f"FAIL: {results_path} not found "
            f"(baseline.json points at a missing report directory)",
            file=sys.stderr,
        )
        return 1

    try:
        results: dict[str, Any] = json.loads(results_path.read_text("utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: {results_path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    try:
        new_block = _build_replacement_block(baseline, results)
    except KeyError as exc:
        # KeyError.args[0] is already the formatted message.
        print(f"FAIL: {exc.args[0]}", file=sys.stderr)
        return 1

    readme_path = repo_root / "README.md"
    if not readme_path.is_file():
        print(f"FAIL: {readme_path} not found", file=sys.stderr)
        return 1

    content = readme_path.read_text("utf-8")
    if not _ANCHOR_PATTERN.search(content):
        print(
            f"FAIL: {readme_path} does not contain a PASTE-REAL-NUMBERS anchor block "
            "(searched for '<!-- PASTE-REAL-NUMBERS: ... <!-- END-PASTE-REAL-NUMBERS -->')",
            file=sys.stderr,
        )
        return 1

    # count=1 — defensive single-replacement per CONTEXT.md D-10 + Pitfall 4.
    new_content, n_subs = _ANCHOR_PATTERN.subn(new_block, content, count=1)
    if n_subs != 1:
        print(
            f"FAIL: expected exactly 1 anchor block replacement, got {n_subs}",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print("--- DRY RUN: proposed replacement block ---")
        print(new_block)
        print("--- DRY RUN: no files written ---")
        return 0

    # Atomic write: write to a temp file in the same dir, then os.replace.
    # os.replace is atomic on POSIX (same filesystem) per stdlib docs.
    tmp_path = readme_path.with_suffix(".md.tmp")
    tmp_path.write_text(new_content, "utf-8")
    os.replace(tmp_path, readme_path)
    print(f"OK: rewrote {readme_path} PASTE-REAL-NUMBERS block ({n_subs} replacement)")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 14 EMP-02 / D-10: paste real numbers from baseline.json "
            "into the README.md PASTE-REAL-NUMBERS anchor block."
        ),
    )
    parser.add_argument(
        "--baseline",
        default="data/eval/baseline.json",
        help="Path to baseline.json (default: data/eval/baseline.json)",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root (default: cwd)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the proposed replacement block to stdout without writing",
    )
    return parser


if __name__ == "__main__":
    sys.exit(main(_build_parser().parse_args()))
