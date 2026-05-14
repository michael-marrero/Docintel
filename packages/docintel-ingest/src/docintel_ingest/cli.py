"""``docintel-ingest`` argparse CLI — fetch + normalize + chunk + all + verify.

D-17 + D-18: this is the fifth workspace package's CLI entry point. The
``[project.scripts] docintel-ingest = "docintel_ingest.cli:main"`` line in
``pyproject.toml`` makes ``uv run docintel-ingest <subcommand>`` invoke this
``main()``. Wave 5's ``make fetch-corpus`` ultimately wraps ``uv run
docintel-ingest all``.

FND-11 single-env-reader rule: ``Settings()`` is constructed exactly ONCE in
``main()`` and passed (not re-read) to each subcommand. ``cfg = Settings()  #
the ONLY allowed env read site`` is the canonical marker comment. No
direct env-reading calls (os dot environ / os dot getenv) live anywhere else
in this package — the grep gate at ``tests/test_no_env_outside_config.py``
enforces this. Tokens spelled with the dot in this docstring deliberately
sidestep the substring matcher (which intentionally accepts false positives
in docstrings — see the test docstring).

Pitfall 9 (torch import cost on --help): subcommand implementations import
heavyweight modules (transformers / selectolax / the SEC downloader SDK) —
each costs ~2-3s cold-start. They MUST stay out of module-level imports
here. Each subcommand dispatch lazily imports its implementation INSIDE the
``if args.cmd == ...:`` branch so ``--help`` / ``--version`` cold-start stays
well under the 5s budget. The Pattern 2 D-12 lazy-import discipline from
Phase 2's adapter factory is replicated here verbatim. (Likewise, the
ingest-wraps grep gate looks for an exact SDK-call pattern; this docstring
avoids the literal token so the gate's surface stays a true positive
indicator.)

Until each subsequent wave (2 fetch / 3 normalize / 4 chunk / 5 verify) lands
its implementation module, the lazy ``from docintel_ingest.<mod> import
<fn>`` call raises ``ImportError``. The dispatch catches that and prints a
``lands in Wave N`` message, returning exit 1. This keeps ``--help`` working
TODAY while signaling "not yet implemented" cleanly to anyone who tries to
run e.g. ``docintel-ingest fetch`` before Wave 2 ships.
"""

from __future__ import annotations

import argparse
import sys

from docintel_core import __version__
from docintel_core.config import Settings
from docintel_core.log import configure_logging

_DEFERRED_WAVES = {
    "fetch": "Wave 2 (docintel_ingest.fetch)",
    "normalize": "Wave 3 (docintel_ingest.normalize)",
    "chunk": "Wave 4 (docintel_ingest.chunk)",
    "all": "Wave 5 (docintel_ingest composition + make fetch-corpus)",
    "verify": "Wave 5 (docintel_ingest.verify — chunk-idempotency canary)",
}


def main(argv: list[str] | None = None) -> int:
    """Entry point referenced by packages/docintel-ingest/pyproject.toml.

    Returns a shell exit code:
      * 0 — subcommand handler returned successfully (Wave 5+).
      * 1 — subcommand not yet implemented OR handler error.
    """
    configure_logging()

    parser = argparse.ArgumentParser(prog="docintel-ingest")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="download 10-Ks from SEC EDGAR")
    sub.add_parser("normalize", help="parse raw HTML to per-Item JSON")
    sub.add_parser("chunk", help="chunk normalized filings into JSONL")
    sub.add_parser("all", help="fetch + normalize + chunk")
    sub.add_parser("verify", help="re-chunk normalized; assert byte-identity")

    args = parser.parse_args(argv)
    cfg = Settings()  # the ONLY allowed env read site (FND-11)

    # Lazy-import dispatch (Pitfall 9 + D-12 discipline). Each branch imports
    # the wave-specific implementation INSIDE the branch so --help / --version
    # never pays the torch / selectolax / SEC-downloader-SDK cold-start cost.
    # Until the implementing wave ships, the import raises ImportError and the
    # try/except surfaces a clean "lands in Wave N" message.
    #
    # The ``type: ignore`` comments below are necessary because the Wave 2-5
    # modules (fetch / normalize / chunk / composer / verify) do not exist yet
    # at the time this file lands. mypy strict (workspace-wide setting in the
    # repo-root pyproject.toml) cannot resolve the import targets. Once each
    # wave ships its module, mypy will resolve naturally and the ignores can be
    # removed in the same wave-flip commit that ships the implementation.
    if args.cmd == "fetch":
        try:
            from docintel_ingest.fetch import fetch_all  # type: ignore[import-not-found]
        except ImportError:
            return _not_yet_implemented(args.cmd)
        return int(fetch_all(cfg))
    if args.cmd == "normalize":
        try:
            from docintel_ingest.normalize import normalize_all  # type: ignore[import-not-found]
        except ImportError:
            return _not_yet_implemented(args.cmd)
        return int(normalize_all(cfg))
    if args.cmd == "chunk":
        try:
            from docintel_ingest.chunk import chunk_all  # type: ignore[import-not-found]
        except ImportError:
            return _not_yet_implemented(args.cmd)
        return int(chunk_all(cfg))
    if args.cmd == "all":
        try:
            from docintel_ingest.composer import run_all  # type: ignore[import-not-found]
        except ImportError:
            return _not_yet_implemented(args.cmd)
        return int(run_all(cfg))
    if args.cmd == "verify":
        try:
            from docintel_ingest.verify import verify_idempotency  # type: ignore[import-not-found]
        except ImportError:
            return _not_yet_implemented(args.cmd)
        return int(verify_idempotency(cfg))

    # argparse with required=True guarantees args.cmd is one of the registered
    # subcommands, so this fallback is unreachable. Kept for defensive symmetry.
    return 1


def _not_yet_implemented(cmd: str) -> int:
    """Print ``lands in Wave N`` and return 1. Used by subcommand stubs."""
    where = _DEFERRED_WAVES.get(cmd, "a future wave")
    print(
        f"docintel-ingest {cmd}: not yet implemented (lands in {where})",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
