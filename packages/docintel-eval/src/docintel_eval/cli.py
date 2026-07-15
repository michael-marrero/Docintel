"""``docintel-eval`` argparse CLI — run + validate subcommands.

EVAL-01 / D-01 / D-03: the ``[project.scripts]`` entrypoint
``docintel-eval = "docintel_eval.cli:main"`` in ``pyproject.toml`` routes
``uv run docintel-eval <subcommand>`` here.

FND-11 single-env-reader rule: ``Settings()`` is constructed exactly ONCE in
``main()`` and passed (not re-read) to each subcommand handler.
``cfg = Settings()  # the ONLY allowed env read site (FND-11)``
is the canonical marker comment. No direct env-reading calls (os dot environ /
os dot getenv) live anywhere else in this package — the grep gate at
``tests/test_no_env_outside_config.py`` enforces this.

Lazy-import dispatch (Pitfall 3 / D-01): subcommand implementations import
heavyweight modules (torch, sentence-transformers, the full pipeline) — each
costs several seconds cold-start. They MUST stay out of module-level imports.
Each subcommand dispatch lazily imports its implementation INSIDE the
``if args.cmd == ...`` branch so ``--help`` / ``--version`` stays fast (<5s).

Subcommand handlers:
  run      — executes the full eval pipeline + writes report.md + results.json.
             Implemented in this wave (Wave 2 / Plan 10-02).
  ablate   — runs baseline + ablation arms in one process and emits per-arm
             sidecars + a comparison table (ABL-01/ABL-02). Flag-free like run
             (D-03 — fixed arm set, no --arms knob). Phase 11 / Plan 11-02.
  validate — EVAL-04 well-formedness gate. Dispatches to cmd_validate for a
             single-run report dir (under data/eval/reports/) or to
             cmd_validate_ablation for an ablation dir (under
             data/eval/ablations/, D-11). The arg is resolved + confined under
             one of those two roots before dispatch (T-10-03 / T-11-05); paths
             outside both are rejected.
"""

from __future__ import annotations

import argparse

import structlog
from docintel_core import __version__
from docintel_core.config import Settings
from docintel_core.log import configure_logging

log = structlog.stdlib.get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Entry point referenced by packages/docintel-eval/pyproject.toml.

    Returns a shell exit code:
      * 0 — subcommand handler returned successfully.
      * 1 — subcommand handler error or unreachable fallback.
      * 2 — argparse error (e.g. no subcommand given).
    """
    configure_logging()

    parser = argparse.ArgumentParser(
        prog="docintel-eval",
        description="docintel eval CLI — run eval pipeline and validate reports.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    # run: execute eval pipeline and write report
    sub.add_parser("run", help="execute eval pipeline and write report")

    # ablate: run baseline + ablation arms; emit comparison table (flag-free, D-03)
    sub.add_parser(
        "ablate",
        help="run baseline + ablation arms; emit comparison table (ABL-01/ABL-02)",
    )

    # calibrate: FR-C5 confidence calibration (Story 3.6) — Brier/ECE/reliability.
    # Flag-free like run/ablate; writes data/eval/calibration/<ts>/.
    sub.add_parser(
        "calibrate",
        help="run confidence calibration (Brier/ECE/reliability curve) — FR-C5",
    )

    # validate: EVAL-04 well-formedness gate (handler lands in Plan 10-03)
    validate_parser = sub.add_parser(
        "validate",
        help="EVAL-04 well-formedness gate for a report directory",
    )
    validate_parser.add_argument(
        "report_dir",
        type=str,
        help="path to the report directory to validate",
    )

    args = parser.parse_args(argv)
    cfg = Settings()  # the ONLY allowed env read site (FND-11)

    # Lazy-import dispatch — each branch imports INSIDE the branch body so
    # --help / --version never pays the torch / sentence-transformers cost.
    if args.cmd == "run":
        from docintel_eval.runner import run_eval

        return run_eval(cfg)

    if args.cmd == "ablate":
        # Lazy import INSIDE the branch (keeps --help < 5s; test_eval_cli_help_fast).
        from docintel_eval.ablate import run_ablations

        return run_ablations(cfg)

    if args.cmd == "calibrate":
        # Lazy import INSIDE the branch (Story 3.6, FR-C5).
        from docintel_eval.calibration import run_calibration

        return run_calibration(cfg)

    if args.cmd == "validate":
        from pathlib import Path

        from docintel_eval.validate import cmd_validate, cmd_validate_ablation

        resolved = Path(args.report_dir).resolve()
        # Path traversal mitigation (T-10-03 / T-11-05): confine the arg under
        # data/eval/reports/ (single-run) OR data/eval/ablations/ (ablation)
        # before dispatching. Reject paths outside BOTH roots.
        reports_root = Path("data/eval/reports").resolve()
        ablations_root = Path("data/eval/ablations").resolve()
        is_under_reports = resolved == reports_root or reports_root in resolved.parents
        is_under_ablations = resolved == ablations_root or ablations_root in resolved.parents
        if is_under_ablations:
            # Ablation gate (D-11) — confined under data/eval/ablations/ (T-11-05).
            return cmd_validate_ablation(resolved)
        if is_under_reports:
            return cmd_validate(resolved)
        log.error(
            "validate_path_outside_roots",
            report_dir=str(resolved),
            reports_root=str(reports_root),
            ablations_root=str(ablations_root),
        )
        return 1

    # argparse with required=True guarantees args.cmd is a registered subcommand,
    # so this fallback is unreachable. Kept for defensive completeness.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
