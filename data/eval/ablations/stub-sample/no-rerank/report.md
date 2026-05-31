# docintel Eval Report

> STUB RUN — latency & $/query are non-representative. representative: false
> Run with DOCINTEL_LLM_PROVIDER=real for published numbers.

## Manifest

| Field | Value |
|-------|-------|
| embedder | stub-embedder |
| reranker | null-reranker |
| generator | stub-llm |
| judge | stub-judge |
| prompt_version_hash | 65da07f1ba3e |
| git_sha | stub-deterministic |
| timestamp | 1970-01-01T00:00:00Z |
| provider | stub |
| n_questions | 32 |
| dataset_hash | sha256:5d9f879207c6b8a0c363804eebb9add4babefaa63beadcea7dc80dbd8db88d82 |
| total_cost_usd | $0.000000 |
| wall_clock_s | 0.00 |
| representative | false |

## Headline Results

| Metric | Value | 95% Wilson CI |
|--------|-------|---------------|
| Hit@1 | 0.148 | [0.059, 0.325] |
| Hit@3 | 0.185 | [0.082, 0.367] |
| Hit@5 | 0.222 | [0.106, 0.408] |
| Hit@10 | 0.333 | [0.186, 0.522] |
| MRR | 0.247 | — |
| Faithfulness (n=32) | 0.000 | [0.000, 0.107] |
| Citation Accuracy (n=32) | 0.050 | — |
| True Refusal Rate (n=5) | 0.000 | [0.000, 0.434] |
| False Answer Rate (n=5) | 1.000 | [0.566, 1.000] |
| False Refusal Rate (n=27) | 0.000 | [0.000, 0.125] |

## Latency & Cost

> Non-representative (stub mode). See manifest.representative.

| Metric | Value |
|--------|-------|
| p50 latency | 0.0 ms |
| p95 latency | 0.0 ms |
| mean $/query | $0.000000 |
| n_queries | 32 |

## Per-Question-Type Breakdown

| Type | n | Hit@5 | Faithfulness | False-Refusal |
|------|---|-------|--------------|---------------|
| single_doc | 17 | 0.353 [0.173, 0.587] | 0.000 [0.000, 0.184] | — |
| multi_doc | 10 | 0.000 [0.000, 0.278] | 0.000 [0.000, 0.278] | — |
| refusal | 5 | — | — | 1.000 [0.566, 1.000] |

## Refusal 2x2 Confusion Matrix

| | Actually Refused | Actually Answered |
|-|-----------------|-------------------|
| Should Refuse (n=5) | 0 (TP) | 5 (FN) |
| Should Answer (n=27) | 0 (FP) | 27 (TN) |

- True Refusal Rate: 0.000 [0.000, 0.434]
- False Answer Rate: 1.000 [0.566, 1.000]
- False Refusal Rate: 0.000 [0.000, 0.125]

## Hero: GT-comparative-001 (Multi-hop Comparative)

**Question:** Which of AAPL, MSFT, NVDA, and TSLA grew R&D spending while their gross margins contracted in FY2024?

**Gold Answer:** Only Tesla grew R&D spending while its gross margin contracted in FY2024: Tesla's R&D expenses increased $571 million, or 14%, rising from 4% to 5% of revenue, while its total automotive gross margin decreased from 19.4% to 18.4%. Apple, Microsoft, and NVIDIA each also grew R&D expense in FY2024, but their gross margins expanded rather than contracted: Apple's Products and Services gross margin percentages both increased, Microsoft's gross margin increased $25.0 billion or 17% with gross margin percentage up slightly, and NVIDIA's gross margin rose to 75.0% from 72.7%. Therefore only Tesla satisfies both conditions.

**System Answer:** Stub synthesis grounded in the provided context. Citations: [AAPL-FY2025-Item-7-003] [AAPL-FY2023-Item-7-004] [MSFT-FY2023-Item-7-007] [MSFT-FY2024-Item-7-006] [MSFT-FY2023-Item-8-034]

**Per-Component Coverage (D-14):**
| Company | Gold Chunks Required | Gold Chunks in Top-10 | Coverage |
|---------|---------------------|----------------------|---------|
| AAPL | AAPL-FY2024-Item-7-003 | ✓ | 1/1 |
| MSFT | MSFT-FY2024-Item-7-008, MSFT-FY2024-Item-7-005 | ✗ | 0/2 |
| NVDA | NVDA-FY2024-Item-7-013 | ✗ | 0/1 |
| TSLA | TSLA-FY2024-Item-7-017, TSLA-FY2024-Item-7-016 | ✓ | 2/2 |

**Coverage Flag:** False (stub retriever cannot find multi-hop golds — expected in stub mode)