"""``docintel-ingest`` argparse CLI — fetch + normalize + chunk + all + verify.

D-17 + D-18: this is the fifth workspace package's CLI entry point. The
``[project.scripts] docintel-ingest = "docintel_ingest.cli:main"`` line in
``pyproject.toml`` makes ``uv run docintel-ingest <subcommand>`` invoke this
``main()``. ``make fetch-corpus`` (wired in Wave 5) ultimately wraps
``uv run docintel-ingest all``.

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

Wave 5 final state: every subcommand has a real implementation behind it.
The ``chunk`` subcommand accepts ``--normalized-root`` and ``--out-root``
overrides so ``tests/test_chunk_idempotency.py::test_chunks_byte_identical``
can re-chunk into a tmpdir for byte-identity diffing. The ``all`` subcommand
chains fetch + normalize + chunk + manifest sequentially. The ``verify``
subcommand re-runs ``verify_idempotency`` over the committed corpus.
"""

from __future__ import annotations

import argparse

import structlog
from docintel_core import __version__
from docintel_core.config import Settings
from docintel_core.log import configure_logging

log = structlog.stdlib.get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Entry point referenced by packages/docintel-ingest/pyproject.toml.

    Returns a shell exit code:
      * 0 — subcommand handler returned successfully.
      * 1 — subcommand handler error.
    """
    configure_logging()

    parser = argparse.ArgumentParser(prog="docintel-ingest")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="download 10-Ks from SEC EDGAR")
    sub.add_parser("normalize", help="parse raw HTML to per-Item JSON")
    # chunk: optional overrides for the normalized-root and chunks-out-root
    # so tests/test_chunk_idempotency.py::test_chunks_byte_identical can
    # re-chunk into a tmpdir for byte-identity diffing against committed
    # output (D-22 / ING-04). Production callers leave both unset and the
    # canonical data/corpus/normalized/ + data/corpus/chunks/ paths are used.
    chunk_parser = sub.add_parser(
        "chunk",
        help="chunk normalized filings into JSONL",
    )
    chunk_parser.add_argument(
        "--normalized-root",
        type=str,
        default=None,
        help="Override path to normalized JSON root (default: data/corpus/normalized)",
    )
    chunk_parser.add_argument(
        "--out-root",
        type=str,
        default=None,
        help="Override path to chunks JSONL output root (default: data/corpus/chunks)",
    )
    sub.add_parser("all", help="fetch + normalize + chunk + manifest")
    sub.add_parser("verify", help="re-chunk normalized; assert byte-identity")

    args = parser.parse_args(argv)
    cfg = Settings()  # the ONLY allowed env read site (FND-11)

    # Lazy-import dispatch (Pitfall 9 + D-12 discipline). Each branch imports
    # the implementation INSIDE the branch so --help / --version never pays
    # the torch / selectolax / SEC-downloader-SDK cold-start cost.
    if args.cmd == "fetch":
        from docintel_ingest.fetch import fetch_all

        return int(fetch_all(cfg))
    if args.cmd == "normalize":
        from docintel_ingest.normalize import normalize_all

        return int(normalize_all(cfg))
    if args.cmd == "chunk":
        from pathlib import Path

        from docintel_ingest.chunk import chunk_all

        normalized_root = Path(args.normalized_root) if args.normalized_root is not None else None
        out_root = Path(args.out_root) if args.out_root is not None else None
        return int(chunk_all(cfg, normalized_root=normalized_root, out_root=out_root))
    if args.cmd == "all":
        return _cmd_all(cfg)
    if args.cmd == "verify":
        from docintel_ingest.verify import verify_idempotency

        return int(verify_idempotency(cfg))

    # argparse with required=True guarantees args.cmd is one of the registered
    # subcommands, so this fallback is unreachable. Kept for defensive symmetry.
    return 1


def _cmd_all(cfg: Settings) -> int:
    """Orchestrate the full ingest pipeline: fetch + normalize + chunk + manifest.

    Each step is sequential — a failure in any earlier step short-circuits
    the run with that step's return code. After chunk completes the
    manifest writer runs unconditionally (it is read-only over the freshly-
    produced corpus).

    Returns:
        0 if every step exits 0; otherwise the first non-zero exit code.
    """
    from docintel_ingest.chunk import chunk_all
    from docintel_ingest.fetch import fetch_all
    from docintel_ingest.manifest import write_manifest
    from docintel_ingest.normalize import normalize_all

    rc = fetch_all(cfg)
    if rc != 0:
        log.error("all_step_failed", step="fetch", rc=rc)
        return rc
    rc = normalize_all(cfg)
    if rc != 0:
        log.error("all_step_failed", step="normalize", rc=rc)
        return rc
    rc = chunk_all(cfg)
    if rc != 0:
        log.error("all_step_failed", step="chunk", rc=rc)
        return rc
    write_manifest(cfg)
    log.info("all_complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
