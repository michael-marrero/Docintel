# docintel Eval Report

## Manifest

| Field | Value |
|-------|-------|
| embedder | bge-small-en-v1.5 |
| reranker | bge-reranker-base |
| generator | nvidia/llama-3.3-nemotron-super-49b-v1 |
| judge | z-ai/glm-5.2/judge |
| prompt_version_hash | 65da07f1ba3e |
| git_sha | d0561e284fe842f0fdc149850ee92e897aa1c038 |
| timestamp | 2026-07-10T21:39:26Z |
| provider | real |
| n_questions | 32 |
| dataset_hash | sha256:5d9f879207c6b8a0c363804eebb9add4babefaa63beadcea7dc80dbd8db88d82 |
| total_cost_usd | $0.000000 |
| wall_clock_s | 1382.28 |
| representative | true |

## Headline Results

| Metric | Value | 95% Wilson CI |
|--------|-------|---------------|
| Hit@1 | 0.222 | [0.106, 0.408] |
| Hit@3 | 0.481 | [0.307, 0.660] |
| Hit@5 | 0.556 | [0.373, 0.724] |
| Hit@10 | 0.667 | [0.478, 0.814] |
| MRR | 0.474 | — |
| Faithfulness (n=28) | 0.893 | [0.728, 0.963] |
| Citation Accuracy (n=28) | 0.630 | — |
| True Refusal Rate (n=5) | 0.200 | [0.036, 0.624] |
| False Answer Rate (n=5) | 0.800 | [0.376, 0.964] |
| False Refusal Rate (n=27) | 0.111 | [0.039, 0.281] |

## Latency & Cost

| Metric | Value |
|--------|-------|
| p50 latency | 21167.4 ms |
| p95 latency | 58615.0 ms |
| mean $/query | $0.000000 |
| n_queries | 32 |

## Per-Question-Type Breakdown

| Type | n | Hit@5 | Faithfulness | False-Refusal |
|------|---|-------|--------------|---------------|
| single_doc | 17 | 0.824 [0.590, 0.938] | n/a (see headline) | — |
| multi_doc | 10 | 0.100 [0.018, 0.404] | n/a (see headline) | — |
| refusal | 5 | — | — | 0.800 [0.376, 0.964] |

## Refusal 2x2 Confusion Matrix

| | Actually Refused | Actually Answered |
|-|-----------------|-------------------|
| Should Refuse (n=5) | 1 (TP) | 4 (FN) |
| Should Answer (n=27) | 3 (FP) | 24 (TN) |

- True Refusal Rate: 0.200 [0.036, 0.624]
- False Answer Rate: 0.800 [0.376, 0.964]
- False Refusal Rate: 0.111 [0.039, 0.281]

## Hero: GT-comparative-001 (Multi-hop Comparative)

**Question:** Which of AAPL, MSFT, NVDA, and TSLA grew R&D spending while their gross margins contracted in FY2024?

**Gold Answer:** Only Tesla grew R&D spending while its gross margin contracted in FY2024: Tesla's R&D expenses increased $571 million, or 14%, rising from 4% to 5% of revenue, while its total automotive gross margin decreased from 19.4% to 18.4%. Apple, Microsoft, and NVIDIA each also grew R&D expense in FY2024, but their gross margins expanded rather than contracted: Apple's Products and Services gross margin percentages both increased, Microsoft's gross margin increased $25.0 billion or 17% with gross margin percentage up slightly, and NVIDIA's gross margin rose to 75.0% from 72.7%. Therefore only Tesla satisfies both conditions.

**System Answer:** I cannot answer this question from the retrieved 10-K excerpts.

**Per-Component Coverage (D-14):**
| Company | Gold Chunks Required | Gold Chunks in Top-10 | Coverage |
|---------|---------------------|----------------------|---------|
| AAPL | AAPL-FY2024-Item-7-003 | ✗ | 0/1 |
| MSFT | MSFT-FY2024-Item-7-008, MSFT-FY2024-Item-7-005 | ✗ | 0/2 |
| NVDA | NVDA-FY2024-Item-7-013 | ✓ | 1/1 |
| TSLA | TSLA-FY2024-Item-7-017, TSLA-FY2024-Item-7-016 | ✗ | 1/2 |

**Coverage Flag:** False (stub retriever cannot find multi-hop golds — expected in stub mode)