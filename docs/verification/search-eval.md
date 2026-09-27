# Search evaluation

60 judged queries x 28 arms. Relevance is graded exhaustively from product attributes (see src/search_eval/relevance.py), never by a search system.

| arm | nDCG@10 | P@5 | R@20 | MRR | zero-result | p50 ms | p95 ms |
|:--|--:|--:|--:|--:|--:|--:|--:|
| before: $match | 0.293 | 0.297 | 0.208 | 0.300 | 0.700 | 53 | 402 |
| before: predictive[maija] | 0.293 | 0.297 | 0.208 | 0.300 | 0.700 | 109 | 182 |
| before: predictive[olli] | 0.293 | 0.297 | 0.208 | 0.300 | 0.700 | 122 | 184 |
| before: predictive[saara] | 0.293 | 0.297 | 0.208 | 0.300 | 0.700 | 141 | 253 |
| left: bm25 | 0.518 | 0.613 | 0.331 | 0.528 | 0.300 | 53 | 72 |
| right θ0.33[maija] | 0.313 | 0.367 | 0.128 | 0.335 | 0.000 | 102 | 125 |
| right θ0.33[olli] | 0.312 | 0.357 | 0.152 | 0.361 | 0.000 | 114 | 156 |
| right θ0.33[saara] | 0.321 | 0.357 | 0.168 | 0.399 | 0.000 | 132 | 602 |
| right θ1.0[maija] | 0.497 | 0.573 | 0.269 | 0.548 | 0.000 | 100 | 134 |
| right θ1.0[olli] | 0.483 | 0.550 | 0.295 | 0.553 | 0.000 | 113 | 144 |
| right θ1.0[saara] | 0.534 | 0.577 | 0.353 | 0.584 | 0.000 | 141 | 735 |
| right θ2.0[maija] | 0.543 | 0.643 | 0.299 | 0.599 | 0.000 | 102 | 296 |
| right θ2.0[olli] | 0.541 | 0.630 | 0.347 | 0.579 | 0.000 | 119 | 358 |
| right θ2.0[saara] | 0.581 | 0.660 | 0.366 | 0.610 | 0.000 | 126 | 184 |
| right θ3.0[maija] | 0.587 | 0.687 | 0.326 | 0.603 | 0.000 | 104 | 239 |
| right θ3.0[olli] | 0.565 | 0.660 | 0.355 | 0.596 | 0.000 | 113 | 211 |
| right θ3.0[saara] | 0.586 | 0.663 | 0.367 | 0.621 | 0.000 | 128 | 239 |
| right θ4.0[maija] | 0.592 | 0.687 | 0.331 | 0.602 | 0.000 | 101 | 138 |
| right θ4.0[olli] | 0.571 | 0.673 | 0.355 | 0.595 | 0.000 | 115 | 244 |
| right θ4.0[saara] | 0.589 | 0.673 | 0.364 | 0.624 | 0.000 | 125 | 158 |
| right θ6.0[maija] | 0.589 | 0.683 | 0.336 | 0.601 | 0.000 | 103 | 232 |
| right θ6.0[olli] | 0.573 | 0.670 | 0.354 | 0.593 | 0.000 | 113 | 130 |
| right θ6.0[saara] | 0.586 | 0.670 | 0.360 | 0.633 | 0.000 | 125 | 182 |
| right θ10.0[maija] | 0.591 | 0.680 | 0.337 | 0.601 | 0.000 | 113 | 320 |
| right θ10.0[olli] | 0.573 | 0.670 | 0.352 | 0.593 | 0.000 | 116 | 214 |
| right θ10.0[saara] | 0.583 | 0.670 | 0.360 | 0.619 | 0.000 | 129 | 303 |
| random (control) | 0.091 | 0.167 | 0.027 | 0.141 | 0.000 | 0 | 0 |
| table order (control) | 0.196 | 0.317 | 0.042 | 0.185 | 0.000 | 0 | 0 |

## nDCG@10 by stratum (shipped arms; right column at θ4.0)

| stratum | before: $match | left: bm25 | right θ4.0[maija] | right θ4.0[olli] | right θ4.0[saara] | random (control) |
|:--|--:|--:|--:|--:|--:|--:|
| brand | 0.700 | 0.833 | 0.866 | 0.846 | 0.846 | 0.085 |
| exact | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.057 |
| misspelling | 0.000 | 0.373 | 0.461 | 0.372 | 0.403 | 0.110 |
| nordic | 0.000 | 0.000 | 0.184 | 0.221 | 0.212 | 0.131 |
| paraphrase | 0.000 | 0.521 | 0.468 | 0.491 | 0.524 | 0.068 |
| synonym | 0.056 | 0.382 | 0.574 | 0.497 | 0.547 | 0.093 |

## Did each column improve? (nDCG@10 difference, paired 95% bootstrap CI)

- **left: bm25 vs before: $match**: +0.225 [+0.141, +0.318] — better
- **right[maija] vs before: predictive[maija]**: +0.299 [+0.204, +0.395] — better
- **right[olli] vs before: predictive[olli]**: +0.278 [+0.199, +0.364] — better
- **right[saara] vs before: predictive[saara]**: +0.296 [+0.205, +0.392] — better

Is the right column at least as good as the left? (ADR 0026 acceptance)

- **right[maija] vs left: bm25**: +0.074 [+0.012, +0.150] — better
- **right[olli] vs left: bm25**: +0.053 [+0.014, +0.102] — better
- **right[saara] vs left: bm25**: +0.071 [+0.025, +0.125] — better

## Reading the numbers

The old right column tied `$match` because its `product_sku.name $match` filter decided which products could appear; reordering a set whose members are all relevant cannot change an attribute-graded score.

Rows that match no query word are dropped from the left column. Left in, they arrive in table order, and the table starts with dog dry food, so every unmatched dog query would score as if answered perfectly. The table-order control shows how much credit that ordering gives for free.

θ4.0 was chosen from 0.33, 1.0, 2.0, 3.0, 4.0, 6.0, 10.0 on this same query set, so the right-vs-left gain above is in-sample and may be optimistic. The next section repeats the choice out of sample.

These labels ignore the persona, so this report cannot see personalisation. Measuring that needs labels from purchases, which waits on purchase data with real repeat and progression patterns.

## θ chosen out of sample

Chosen on half the queries, scored on the other half, over 500 stratified splits (see src/search_eval/theta_selection.py).

- θ chosen on the tuning half: θ0.33 0/500, θ1.0 0/500, θ2.0 0/500, θ3.0 13/500, θ4.0 311/500, θ6.0 40/500, θ10.0 136/500
- held-out right-vs-left gain for each θ (median over splits): θ0.33 -0.202, θ1.0 -0.012, θ2.0 +0.038, θ3.0 +0.062, θ4.0 +0.067, θ6.0 +0.066, θ10.0 +0.065
- held-out right-vs-left gain of the θ chosen per split: median +0.065, 90 % of splits in [+0.036, +0.093], positive in 100% of splits
- one split (seed 0, θ4.0), per persona on its 30 held-out queries:
  - maija: +0.052 [-0.022, +0.148]
  - olli: +0.052 [-0.012, +0.123]
  - saara: +0.081 [+0.004, +0.176]

## Controls

- chance level (random arm): 0.091 nDCG@10
- best arm (`right θ4.0[maija]`) against SHUFFLED labels: 0.104 — must fall to within 0.05 of chance
- best arm against the real labels must clear chance by ≥ 0.2
