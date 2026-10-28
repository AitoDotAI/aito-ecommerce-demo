# Funnel calibration against April 2026, as counted

**Date:** 2026-10-28 · **Env:** master (release 3a), Aito 2.11.9 · **Code:** `330b23b`
**Probe:** `funnel_calibration_probe.py` (read-only; 70 products drawn with seed 11 from April 2026's `monthly_sales`)
**Data:** generated (planted effects). This describes the engine on this data, not a real shop.

Question: how far are the Funnel's chained estimates (ADR 0050) from what was counted, and is `_estimate`
closer? Antti's hypothesis was bias from multiplying many evidence lifts; this report measures, it does not
establish the cause.

## Result

| Quantity (sum over 70 products) | Estimate | Counted | Ratio |
|---|---|---|---|
| Impressions | 740.4 | 853 | 0.87 |
| Clicks | 303.9 | 357 | 0.85 |
| Purchases | 196.2 | 223 | 0.88 |
| Units | 339.3 | 471 | 0.72 |

Units, mean absolute error per product (products with an `_estimate units_index` answer):
`_estimate units_index` × the product's mean 4.03 · the product's mean of earlier months 4.72 · the funnel's chain 5.01.
So the direct `_estimate` was closest, and the four-stage chain was further off than the plain mean.

`_predict` calibration on the ranked impressions (expected = Σ p × the product's ranked showings):

| | Expected | Observed | Ratio | Lowest-p decile (expected / observed, products) |
|---|---|---|---|---|
| clicked | 1136.2 | 1220 | 0.93 | 11.3 / 26 (6) |
| purchased | 466.9 | 537 | 0.87 | 148.5 / 235 (46) |

The aggregate is close; the under-estimate sits in the low-probability tail (purchased: 0.63 in the lowest
decile, 46 of the 70 products). Higher deciles are near 1 or over (0.3 decile: 360.7 expected, 316 observed).

## What this does not show

- The cause. A product of correlated lifts treated as independent would push the tails outward, and four chained
  stages compound each stage's error; both fit, neither was isolated. A fail-first booktest on a table with known
  true rates and correlated features would.
- The earlier figures in the session notes (per-product error 3.66 / 4.29 / 5.35, aggregate ratios 0.82–1.06,
  tail about 40 % under) came from an earlier run on the `release3a` env with a probe that was not committed.
  They do not reproduce exactly (above: 4.03 / 4.72 / 5.01, units ratio 0.72); the ordering and the tail's
  direction do. This report replaces them.
- One sample of 70 products and one month. No interval is claimed.
