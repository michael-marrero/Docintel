"""``docintel-index`` argparse CLI — build + verify + all (D-16).

D-16 + D-17: this is the sixth workspace package's CLI entry point. The
``[project.scripts] docintel-index = "docintel_index.cli:main"`` line in
``pyproject.toml`` makes ``uv run docintel-index <subcommand>`` invoke this
``main()``. ``make build-indices`` (Plan 04-06) wraps ``uv run docintel-index all``.

FND-11 single-env-reader rule: ``Settings()`` is constructed exactly ONCE in
``main()`` and passed (not re-read) to each subcommand. The single
construction site carries the canonical marker comment "the ONLY allowed
env read site (FND-11)". No direct env-reading calls (os dot environ /
os dot getenv) live anywhere else in this package — the grep gate at
``tests/test_no_env_outside_config.py`` enforces this. Tokens spelled
with the dot in this docstring deliberately sidestep the substring
matcher (which intentionally accepts false positives in docstrings).

Lazy-import dispatch (D-12 + Phase 3 cli.py pattern): subcommand
implementations import heavyweight modules (torch / sentence-transformers
via embedder factory, qdrant-client via QdrantDenseStore lazy real branch).
Each subcommand dispatch lazily imports its implementation INSIDE the
``if args.cmd == ...:`` branch so ``--help`` / ``--version`` cold-start
stays well under the 5s budget. The same pattern Phase 2's adapter factory
uses for stub-vs-real lazy SDK imports.
"""

from __future__ import annotations

import argparse

import structlog
from docintel_core import __version__
from docintel_core.config import Settings
from docintel_core.log import configure_logging

log = structlog.stdlib.get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Entry point referenced by packages/docintel-index/pyproject.toml.

    Returns a shell exit code:
      * 0 — subcommand handler returned successfully.
      * 1 — subcommand handler error.
    """
    configure_logging()

    parser = argparse.ArgumentParser(prog="docintel-index")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="build dense + BM25 indices from data/corpus/chunks/")
    sub.add_parser("verify", help="verify data/indices/MANIFEST.json against on-disk artifacts")
    sub.add_parser("all", help="build then verify (short-circuits on nonzero)")

    args = parser.parse_args(argv)
    cfg = Settings()  # the ONLY allowed env read site (FND-11)

    # Lazy-import dispatch (D-12 discipline). Each branch imports the
    # implementation INSIDE the branch so --help / --version never pays the
    # torch / sentence-transformers / qdrant-client cold-start cost.
    if args.cmd == "build":
        from docintel_index.build import build_indices

        build_indices(cfg)
        return 0
    if args.cmd == "verify":
        from docintel_index.verify import verify_indices

        return int(verify_indices(cfg))
    if args.cmd == "all":
        return _cmd_all(cfg)

    # argparse with required=True guarantees args.cmd is one of the registered
    # subcommands, so this fallback is unreachable. Kept for defensive symmetry.
    return 1


def _cmd_all(cfg: Settings) -> int:
    """Orchestrate build then verify (short-circuit on nonzero).

    ``build_indices`` raises on failure (does NOT return an error code).
    ``verify_indices`` returns 0 / 1. The composite exit code is the verify
    return value (build either succeeds-and-returns-the-manifest or raises).

    Returns:
        0 if build succeeded AND verify exited 0; otherwise verify's nonzero
        exit code. A build-time exception propagates to argparse and exits 1.
    """
    from docintel_index.build import build_indices
    from docintel_index.verify import verify_indices

    build_indices(cfg)
    rc = verify_indices(cfg)
    if rc != 0:
        log.error("all_verify_failed", rc=rc)
        return rc
    log.info("all_complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
