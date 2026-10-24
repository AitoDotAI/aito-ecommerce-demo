# Search evaluation

60 judged queries x 28 arms. Relevance is graded exhaustively from product attributes (see src/search_eval/relevance.py), never by a search system.

| arm | nDCG@10 | P@5 | R@20 | MRR | zero-result | p50 ms | p95 ms |
|:--|--:|--:|--:|--:|--:|--:|--:|
| before: $match | 0.293 | 0.297 | 0.208 | 0.300 | 0.700 | 3049 | 8861 |
| before: predictive[maija] | 0.293 | 0.297 | 0.208 | 0.300 | 0.700 | 4478 | 8063 |
| before: predictive[olli] | 0.293 | 0.297 | 0.208 | 0.300 | 0.700 | 3870 | 6219 |
| before: predictive[saara] | 0.293 | 0.297 | 0.208 | 0.300 | 0.700 | 3691 | 5311 |
| left: bm25 | 0.518 | 0.613 | 0.332 | 0.529 | 0.300 | 3744 | 6648 |
| right θ0.33[maija] | 0.345 | 0.430 | 0.173 | 0.442 | 0.000 | 3689 | 8275 |
| right θ0.33[olli] | 0.301 | 0.393 | 0.195 | 0.447 | 0.000 | 3825 | 7598 |
| right θ0.33[saara] | 0.333 | 0.437 | 0.204 | 0.449 | 0.000 | 3440 | 7745 |
| right θ1.0[maija] | 0.574 | 0.667 | 0.324 | 0.583 | 0.000 | 3488 | 6751 |
| right θ1.0[olli] | 0.558 | 0.640 | 0.334 | 0.631 | 0.000 | 3432 | 7612 |
| right θ1.0[saara] | 0.559 | 0.637 | 0.332 | 0.584 | 0.000 | 3438 | 7484 |
| right θ2.0[maija] | 0.588 | 0.683 | 0.342 | 0.612 | 0.000 | 3201 | 4609 |
| right θ2.0[olli] | 0.574 | 0.670 | 0.347 | 0.632 | 0.000 | 3251 | 4925 |
| right θ2.0[saara] | 0.589 | 0.683 | 0.349 | 0.608 | 0.000 | 3142 | 6370 |
| right θ3.0[maija] | 0.593 | 0.683 | 0.343 | 0.612 | 0.000 | 2956 | 6213 |
| right θ3.0[olli] | 0.573 | 0.670 | 0.353 | 0.615 | 0.000 | 2941 | 5217 |
| right θ3.0[saara] | 0.591 | 0.687 | 0.351 | 0.609 | 0.000 | 2940 | 5244 |
| right θ4.0[maija] | 0.589 | 0.680 | 0.343 | 0.604 | 0.000 | 3149 | 6761 |
| right θ4.0[olli] | 0.572 | 0.667 | 0.354 | 0.612 | 0.000 | 3143 | 5032 |
| right θ4.0[saara] | 0.590 | 0.687 | 0.352 | 0.611 | 0.000 | 3400 | 5754 |
| right θ6.0[maija] | 0.588 | 0.677 | 0.341 | 0.594 | 0.000 | 2406 | 6112 |
| right θ6.0[olli] | 0.574 | 0.667 | 0.352 | 0.618 | 0.000 | 3115 | 5246 |
| right θ6.0[saara] | 0.589 | 0.687 | 0.352 | 0.612 | 0.000 | 3154 | 7020 |
| right θ10.0[maija] | 0.592 | 0.673 | 0.338 | 0.600 | 0.000 | 3129 | 4799 |
| right θ10.0[olli] | 0.581 | 0.670 | 0.347 | 0.619 | 0.000 | 3195 | 4776 |
| right θ10.0[saara] | 0.589 | 0.687 | 0.346 | 0.611 | 0.000 | 3363 | 6234 |
| random (control) | 0.091 | 0.167 | 0.027 | 0.141 | 0.000 | 0 | 0 |
| table order (control) | 0.196 | 0.317 | 0.042 | 0.185 | 0.000 | 0 | 0 |

## nDCG@10 by stratum (shipped arms; right column at θ4.0)

| stratum | before: $match | left: bm25 | right θ4.0[maija] | right θ4.0[olli] | right θ4.0[saara] | random (control) |
|:--|--:|--:|--:|--:|--:|--:|
| brand | 0.700 | 0.833 | 0.846 | 0.848 | 0.841 | 0.085 |
| exact | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.057 |
| misspelling | 0.000 | 0.373 | 0.420 | 0.398 | 0.492 | 0.110 |
| nordic | 0.000 | 0.000 | 0.200 | 0.208 | 0.257 | 0.131 |
| paraphrase | 0.000 | 0.521 | 0.489 | 0.494 | 0.514 | 0.068 |
| synonym | 0.056 | 0.382 | 0.581 | 0.486 | 0.438 | 0.093 |

## Did each column improve? (nDCG@10 difference, paired 95% bootstrap CI)

- **left: bm25 vs before: $match**: +0.225 [+0.141, +0.318] — better
- **right[maija] vs before: predictive[maija]**: +0.296 [+0.201, +0.393] — better
- **right[olli] vs before: predictive[olli]**: +0.280 [+0.203, +0.365] — better
- **right[saara] vs before: predictive[saara]**: +0.298 [+0.209, +0.396] — better

Is the right column at least as good as the left? (ADR 0026 acceptance)

- **right[maija] vs left: bm25**: +0.071 [+0.007, +0.152] — better
- **right[olli] vs left: bm25**: +0.054 [+0.009, +0.102] — better
- **right[saara] vs left: bm25**: +0.072 [+0.012, +0.144] — better

## Reading the numbers

The old right column tied `$match` because its `product_sku.name $match` filter decided which products could appear; reordering a set whose members are all relevant cannot change an attribute-graded score.

Rows that match no query word are dropped from the left column. Left in, they arrive in table order, and the table starts with dog dry food, so every unmatched dog query would score as if answered perfectly. The table-order control shows how much credit that ordering gives for free.

θ4.0 was chosen from 0.33, 1.0, 2.0, 3.0, 4.0, 6.0, 10.0 on this same query set, so the right-vs-left gain above is in-sample and may be optimistic. The next section repeats the choice out of sample.

These labels ignore the persona, so this report cannot see personalisation. Measuring that needs labels from purchases, which waits on purchase data with real repeat and progression patterns.

## θ chosen out of sample

Chosen on half the queries, scored on the other half, over 500 stratified splits (see src/search_eval/theta_selection.py).

- θ chosen on the tuning half: θ0.33 0/500, θ1.0 0/500, θ2.0 79/500, θ3.0 100/500, θ4.0 25/500, θ6.0 6/500, θ10.0 290/500
- held-out right-vs-left gain for each θ (median over splits): θ0.33 -0.187, θ1.0 +0.046, θ2.0 +0.066, θ3.0 +0.068, θ4.0 +0.066, θ6.0 +0.066, θ10.0 +0.070
- held-out right-vs-left gain of the θ chosen per split: median +0.066, 90 % of splits in [+0.036, +0.099], positive in 100% of splits
- one split (seed 0, θ10.0), per persona on its 30 held-out queries:
  - maija: +0.051 [-0.026, +0.160]
  - olli: +0.059 [-0.003, +0.125]
  - saara: +0.038 [-0.020, +0.122]

## Controls

- chance level (random arm): 0.091 nDCG@10
- best arm (`right θ3.0[maija]`) against SHUFFLED labels: 0.110 — must fall to within 0.05 of chance
- best arm against the real labels must clear chance by ≥ 0.2
