# Search evaluation

60 judged queries x 3 arms. Relevance is graded exhaustively from product attributes (see src/search_eval/relevance.py), never by a search system.

| arm | nDCG@10 | P@5 | R@20 | MRR | zero-result | p50 ms | p95 ms |
|:--|--:|--:|--:|--:|--:|--:|--:|
| current_match | 0.293 | 0.297 | 0.208 | 0.300 | 0.700 | 64 | 173 |
| bm25 | 0.599 | 0.713 | 0.345 | 0.613 | 0.000 | 62 | 238 |
| random (control) | 0.091 | 0.167 | 0.027 | 0.141 | 0.000 | 0 | 0 |

## nDCG@10 by stratum

| stratum | current_match | bm25 | random (control) |
|:--|--:|--:|--:|
| brand | 0.700 | 0.833 | 0.085 |
| exact | 1.000 | 1.000 | 0.057 |
| misspelling | 0.000 | 0.525 | 0.110 |
| nordic | 0.000 | 0.233 | 0.131 |
| paraphrase | 0.000 | 0.521 | 0.068 |
| synonym | 0.056 | 0.482 | 0.093 |

## Paired difference vs current_match (nDCG@10, 95% bootstrap CI)

- **bm25**: +0.306 [+0.212, +0.409] — better
- **random (control)**: -0.202 [-0.331, -0.085] — worse

## Controls

- chance level (random arm): 0.091 nDCG@10
- best arm (`bm25`) against SHUFFLED labels: 0.098 — must fall to within 0.05 of chance
- best arm against the real labels must clear chance by ≥ 0.2
