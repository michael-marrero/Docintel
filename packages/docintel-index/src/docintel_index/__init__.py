"""docintel-index: Dense + BM25 index build/verify CLI.

Phase 4 implementation — builds the dense (NumPy stub / Qdrant real) and
sparse BM25 indices over Phase 3's citation-anchored chunk JSONL. The CLI
will expose ``docintel-index {build|verify|all}`` (Plan 04-05); ``make
build-indices`` invokes ``uv run docintel-index all`` (Plan 04-06).

This Plan 04-03 lands the package skeleton only — ``__init__.py`` is empty
of public re-exports because ``docintel_index.cli`` does not exist yet. Plan
04-05 lands ``build.py``, ``verify.py``, ``manifest.py``, ``cli.py`` AND
amends this file to re-export ``main`` so the ``[project.scripts]`` console
script ``docintel-index = "docintel_index.cli:main"`` resolves.

Stub-mode CI builds indices on every PR via ``LLM_PROVIDER=stub`` (D-20).
The real-mode index build is gated behind ``workflow_dispatch`` to avoid
paying the Qdrant docker start-up + real BGE inference cost on every PR.
"""

__all__: list[str] = []
