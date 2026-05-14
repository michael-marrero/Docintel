"""docintel-ingest: SEC 10-K corpus ingestion CLI.

Phase 3 implementation — fetches 10-Ks from SEC EDGAR (D-03 sec-edgar-downloader),
normalizes them via selectolax + Item-boundary regex (D-06, D-07), and chunks
them with the real BGE tokenizer (D-10, D-11) into citation-anchored JSONL.

CLI entry: ``docintel-ingest {fetch|normalize|chunk|all|verify}``. Invoked by
``make fetch-corpus`` (Wave 5). Stub-mode CI never exercises the live fetch
path; ``tests/test_chunk_idempotency.py`` re-runs the chunker on committed
normalized JSON to assert ING-04 byte-identity.
"""

__all__ = ["main"]

from docintel_ingest.cli import main
