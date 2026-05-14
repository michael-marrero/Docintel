"""docintel-index: Dense + BM25 index build/verify CLI.

Phase 4 implementation — builds the dense (NumPy stub / Qdrant real) and
sparse BM25 indices over Phase 3's citation-anchored chunk JSONL. The CLI
exposes ``docintel-index {build|verify|all}`` (D-16); ``make build-indices``
invokes ``uv run docintel-index all`` (Plan 04-06).

Plan 04-05 lands ``build.py``, ``verify.py``, ``manifest.py``, ``cli.py``
and amends this file to re-export ``main`` so the ``[project.scripts]``
console script ``docintel-index = "docintel_index.cli:main"`` resolves.

Stub-mode CI builds indices on every PR via ``LLM_PROVIDER=stub`` (D-20).
The real-mode index build is gated behind ``workflow_dispatch`` to avoid
paying the Qdrant docker start-up + real BGE inference cost on every PR.

Public surface:
    * ``main`` — argparse entry point (cli.py).

Library-call entry points (``build_indices``, ``verify_indices``) stay
lazy and are imported INSIDE the cli's branches; they are not re-exported
here so callers reach them via their canonical modules
(``docintel_index.build`` and ``docintel_index.verify``).
"""

__all__ = ["main"]

from docintel_index.cli import main
