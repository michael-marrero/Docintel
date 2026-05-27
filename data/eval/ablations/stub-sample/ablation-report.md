# docintel Ablation Report

> STUB RUN — component-insensitive stub adapters yield ≈0 deltas; non-representative. representative: false
> Run with DOCINTEL_LLM_PROVIDER=real for published deltas.

## Ablation: Reranking (no-rerank arm)
Reranking adds -0.156 Hit@3 [95% CI -0.281, -0.031].

## Ablation: BM25 (dense-only arm)
BM25 adds -0.000 Hit@3 [95% CI -0.000, -0.000].

## Comparison Table

| Arm | Hit@5 (Δ [95% CI]) | Hit@3 (Δ [95% CI]) | MRR (Δ [95% CI]) |
|---|---|---|---|
| baseline | 0.000 (—) | 0.000 (—) | 0.048 (—) |
| no-rerank | 0.188 (+0.188 [0.062, 0.344]) | 0.156 (+0.156 [0.031, 0.281]) | 0.209 (+0.161 [0.056, 0.285]) |
| dense-only | 0.000 (+0.000 [0.000, 0.000]) | 0.000 (+0.000 [0.000, 0.000]) | 0.035 (-0.013 [-0.027, -0.003]) |

> Faithfulness, citation, latency & $/query deltas are real-mode only (non-representative in stub). See per-arm results.json.
