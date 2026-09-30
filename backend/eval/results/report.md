# SAGE evaluation report

Eval set: 50 questions over 6 sources (10 unanswerable).

## Retrieval ablation (all-MiniLM-L6-v2)

| Configuration | Context recall | Recall@k | MRR |
|---|---|---|---|
| Dense only | 91% | 91% | 0.69 |
| + BM25 hybrid rerank | 91% | 91% | 0.77 |
| + Query rewriting | 91% | 91% | 0.75 |
| Full (+ overview/position) | 94% | 91% | 0.75 |

34 retrieval-scored questions.

## Embedding models (full pipeline)

| Model | Context recall | Recall@k | MRR | ms/query |
|---|---|---|---|---|
| all-MiniLM-L6-v2 | 94% | 91% | 0.75 | 435 |
| BAAI/bge-small-en-v1.5 | 91% | 91% | 0.70 | 389 |
| intfloat/multilingual-e5-small | 88% | 88% | 0.71 | 414 |
## Answers — full system (all-minilm-l6-v2)

- Answer accuracy (answerable): **90%** of 40
- Refusal recall (unanswerable refused): **100%** of 10
- Refusal precision: **77%** (3 false refusals)
- Median answer latency: 2.38s

| Category | Accuracy | n |
|---|---|---|
| factual | 76% | 17 |
| hindi | 100% | 5 |
| multi | 100% | 2 |
| paraphrase | 100% | 4 |
| position | 100% | 1 |
| summary | 100% | 2 |
| typo | 100% | 5 |
| unanswerable | 100% | 10 |
| vague | 100% | 4 |

### Confidence calibration (answerable questions)

| Confidence | n | Accuracy |
|---|---|---|
| 0.00-0.40 | 0 | – |
| 0.40-0.60 | 5 | 100% |
| 0.60-0.75 | 19 | 84% |
| 0.75-1.00 | 16 | 94% |

