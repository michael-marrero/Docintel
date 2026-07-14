"""Story 1.2 — firm-supplied earnings-call transcript ingestion.

Transcripts are a NON-SEC source: firm-licensed JSON files under
``data/corpus/transcripts/{ticker}/*.json``, segmented by speaker turn and
normalized into the same ``NormalizedFiling`` shape the chunker consumes
(``filing_type="transcript"``). No network (local files), no corpus re-baseline
(the schema change is a Literal expansion, see ADR/Story 1.2). Optional: an
absent/empty transcripts dir is a clean no-op (AC-2).

Input contract (Story 1.2 Design decision #1)::

    {
      "ticker": "AAPL", "fiscal_year": 2024, "fiscal_period": "Q1",
      "call_date": "2024-02-01", "title": "Q1 FY2024 Earnings Call",
      "turns": [ {"speaker": "Operator", "role": "", "text": "..."},
                 {"speaker": "Tim Cook", "role": "CEO", "text": "..."} ]
    }
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import structlog
from docintel_core.config import Settings
from docintel_core.types import NormalizedFiling, NormalizedFilingManifest

from docintel_ingest.snapshot import load_snapshot

log = structlog.stdlib.get_logger(__name__)

_REQUIRED_KEYS = {"ticker", "fiscal_year", "fiscal_period", "turns"}


def parse_transcript(path: Path) -> NormalizedFiling:
    """Parse one firm-supplied transcript JSON into a ``NormalizedFiling``.

    Each turn becomes one section keyed ``Turn {n:03d}`` in document order, with
    the speaker heading as the section's first line so the chunker derives
    ``item_title=speaker`` AND the embedded chunk text carries the attribution
    (good for retrieval). Turns with empty text are dropped.

    Raises:
        ValueError: the JSON is missing a required key or ``turns`` is not a
            non-empty list (caller logs + skips that one file, per AC-2 tolerance).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"transcript {path.name}: missing required keys {sorted(missing)}")
    turns = data["turns"]
    if not isinstance(turns, list) or not turns:
        raise ValueError(f"transcript {path.name}: 'turns' must be a non-empty list")

    sections: dict[str, str] = {}
    items_found: list[str] = []
    for n, turn in enumerate(turns):
        text = str(turn.get("text", "")).strip()
        if not text:
            continue
        speaker = str(turn.get("speaker", "")).strip() or "Unknown Speaker"
        role = str(turn.get("role", "")).strip()
        heading = f"{speaker} ({role})" if role else speaker
        code = f"Turn {n:03d}"
        sections[code] = f"{heading}\n\n{text}"
        items_found.append(code)

    if not sections:
        raise ValueError(f"transcript {path.name}: no non-empty turns")

    call_date = str(data.get("call_date", "")).strip()
    # 8-K uses accession as the per-filing identity; a transcript uses call_date.
    accession = f"CALL-{call_date}" if call_date else "CALL"
    manifest = NormalizedFilingManifest(
        items_found=items_found,
        items_missing=[],  # a transcript has no canonical "expected" section set
        ordering_valid=True,
        tables_dropped=0,
    )
    return NormalizedFiling(
        ticker=data["ticker"],
        fiscal_year=int(data["fiscal_year"]),
        accession=accession,
        fetched_at=datetime.now(UTC).isoformat(),
        # Repo-relative so the committed manifest is portable; the manifest
        # writer resolves it against cfg.data_dir for the sha256 read.
        raw_path=f"data/corpus/transcripts/{data['ticker']}/{path.name}",
        sections=sections,
        manifest=manifest,
        filing_type="transcript",
        fiscal_period=str(data["fiscal_period"]),
    )


def normalize_transcripts_all(cfg: Settings, transcripts_root: Path | None = None) -> int:
    """Normalize every firm-supplied transcript into ``data/corpus/normalized/``.

    Globs ``data/corpus/transcripts/{ticker}/*.json`` for each snapshot ticker;
    writes ``normalized/{ticker}/CALL-{period}FY{year}.json``. Optional (AC-2):
    if the transcripts dir is absent or empty, this is a no-op returning 0.

    Returns:
        Shell exit code: 0 if every transcript parsed (or none present); 1 if
        at least one file failed to parse (logged, non-fatal to the others).
    """
    if transcripts_root is None:
        transcripts_root = Path(cfg.data_dir) / "corpus" / "transcripts"
    out_root = Path(cfg.data_dir) / "corpus" / "normalized"
    companies = load_snapshot(cfg)

    n_ok = 0
    n_failed = 0
    for entry in companies:
        tdir = transcripts_root / entry.ticker
        if not tdir.is_dir():
            continue
        for path in sorted(tdir.glob("*.json")):
            try:
                nf = parse_transcript(path)
            except Exception as exc:
                n_failed += 1
                log.error(
                    "transcript_parse_failed",
                    ticker=entry.ticker,
                    path=str(path),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                continue
            stem = f"CALL-{nf.fiscal_period}FY{nf.fiscal_year}"
            out_path = out_root / entry.ticker / f"{stem}.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            # sort_keys=True is the byte-identity guarantor (mirrors normalize_all).
            out_path.write_text(
                json.dumps(nf.model_dump(), indent=2, sort_keys=True), encoding="utf-8"
            )
            n_ok += 1
            log.info(
                "transcript_normalized", ticker=entry.ticker, stem=stem, turns=len(nf.sections)
            )

    log.info("transcripts_complete", n_succeeded=n_ok, n_failed=n_failed)
    return 0 if n_failed == 0 else 1
