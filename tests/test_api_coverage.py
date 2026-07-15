"""Story 1.5 — GET /coverage endpoint (against the committed corpus)."""

from __future__ import annotations

from fastapi.testclient import TestClient

_COMPANY_KEYS = {
    "ticker",
    "name",
    "sector",
    "forms",
    "fiscal_years",
    "filing_counts",
    "transcript_count",
    "latest_period",
    "in_corpus",
}
_CORPUS_KEYS = {"company_count", "forms", "fy_min", "fy_max", "has_transcripts", "snapshot_date"}


def test_get_coverage_200_and_shape(client: TestClient) -> None:
    resp = client.get("/coverage")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"corpus", "companies"}
    assert _CORPUS_KEYS <= set(body["corpus"])
    assert body["corpus"]["company_count"] >= 1
    assert "10-K" in body["corpus"]["forms"]  # committed corpus is 10-K
    assert body["companies"], "coverage should list the committed companies"
    assert _COMPANY_KEYS <= set(body["companies"][0])


def test_get_coverage_corpus_field_types(client: TestClient) -> None:
    body = client.get("/coverage").json()
    corpus = body["corpus"]
    assert isinstance(corpus["company_count"], int)
    assert corpus["fy_min"] is None or isinstance(corpus["fy_min"], int)
