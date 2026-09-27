# ADR 0014: Demand Forecast — `_predict units_sold` over monthly_sales

**Status:** Accepted
**Date:** 2026-05-13
**Deciders:** Antti

## Context

Merchandisers plan reorders, promotions, and ad spend based on
"how many of SKU X will we sell next month". Most shops do this
with last-month-times-seasonality-factor; we wire Aito's
`_predict units_sold` to the same problem from a panel of
historical sales.

The Operate section's first view; companion to Inventory (which
consumes Demand's forecast as input) and Price (which surfaces
sweet-spot patterns over the same panel).

## Aito usage

**`_estimate`** (not `_predict`) for the forecast — `units_sold`
is continuous-style Int data and what we want is the *expected
value*, not the most-probable specific integer. `_predict` on
`units_sold` returns ranked discrete values each with low `$p`
(top hit "1 unit at 17 %"); `_estimate` returns a single mean
(3.76 units) — the natural fit. See `docs/aito-cheatsheet.md`
§`_estimate vs _predict`.

```json
{
  "from": "monthly_sales",
  "where": {
    "product_sku": "SKU-PT-0001",
    "month": "2026-05",
    "pet_type": "dog",
    "category": "dry-food",
    "brand": "Royal Canin",
    "season": "spring"
  },
  "estimate": "units_sold",
  "select": ["estimate", "why"]
}
```

The `why` is a K-NN `weightedAverage` of `neighborContext`
nodes. `process_estimate_why` flattens **only the top-weighted
neighbor's subtree** — 20+ neighbors × per-feature regressions
would be too noisy for the popover.

Plus, in parallel:

- **Seasonality** — four `_relate` calls, one per season
  (spring/summer/autumn/winter), each relating `category` over
  `monthly_sales where {season: <name>}` to surface "treats peak
  in winter at 2.1× baseline", "aquarium products lift in
  summer".
- **Accuracy** — one `_evaluate` over a 300-row sample with the
  same feature set, reporting accuracy + baseline + gain pp.

## Decision

### New `monthly_sales` table

Panel data, one row per `(sku, month)` with at least one sale.
Volumes: ~11,100 rows (658 SKUs × ~17 months avg coverage).

| Column | Type | Notes |
|---|---|---|
| `monthly_sale_id` | String, PK | `<sku>-<month>` |
| `product_sku` | String, link → products.sku | |
| `month` | String | YYYY-MM |
| `units_sold` | Int | Sum of qty across all order_lines this month |
| `revenue_eur` | Decimal | units × price |
| `unique_customers` | Int | Distinct customer_ids |
| `pet_type` / `category` / `brand` | String | Denormalised (Aito single-hop) |
| `season` | String | spring / summer / autumn / winter |

Denormalised profile fields are deliberate — `_predict` on
`monthly_sales` conditions on the row's fields directly without
traversing to `products`.

### Top movers, not random SKUs

The page shows the top 25 SKUs ranked by **average monthly
units**. Picking by volume keeps the forecasts statistically
meaningful — long-tail SKUs with 1-2 historical observations
return low-confidence predictions that read as noise.

### Forecast month is fixed

Frozen demo today = `2026-04`. Forecast month = `2026-05`. Aito
predicts for a month not in the training data — the value of the
`month` feature is novel; Aito's prediction relies on the other
features (sku + denormalised profile + season).

## Acceptance criteria

- [x] A user can open `/demand` and see 25 top-mover SKUs with
      forecast / last-month / avg-monthly columns.
- [x] Each forecast row's **?** opens the WhyPopover with the
      $why factor chain.
- [x] Seasonality section surfaces 8-12 category-season pairs
      with lift > 1.15 or < 0.85.
- [x] Evaluation card shows held-out accuracy + baseline + gain
      pp; gain ≥ 0 (the model at least matches majority-class).

## Demo impact

Adds a third Aito-time-series pattern to the demo (alongside the
month-string ordering in Dashboard and the customer_months panel
in Churn). Powers Inventory's reorder workflow — without Demand,
Inventory has no way to know what to reorder.

## Out of scope

- **Confidence intervals on forecasts**. Aito's `_predict`
  returns `$p`, not a distribution. A real demand-planning tool
  needs P10/P50/P90; we show only the point estimate.
- **Multi-month horizons**. Forecast is for next month only.
  Three-month-ahead would need a separate model per horizon or
  a recursive approach.
- **Promotional / external-event modelling**. The forecast
  doesn't know about upcoming sales events; production would
  layer an event calendar over the baseline.

## Consequences

**Good:**
- The first Aito predict in the demo on a *panel-data* shape with
  a denormalised time-index — pattern transfers directly to
  customer_months and any future SKU-month / customer-day style
  data.
- Reuses the existing `process_why` + `WhyPopover` infrastructure
  — every forecast carries its own `$why` decomposition.

**Bad:**
- 25 parallel `_predict` calls is the costliest piece of this
  page (~3 s warm). Mitigated by the standard 30-min cache.
- Forecasts for SKUs with sparse history (< 6 observations) are
  noisy; we cap at top 25 by volume to avoid surfacing those.

## Notes

The `season` column is denormalised at fixture-gen via
`_SEASON_BY_MONTH`. The `_relate season=<name> relate category`
queries leverage this directly — without it, the four parallel
seasonality `_relate` calls couldn't condition cleanly.

## Correction: a forecast must beat "same as last month" (2026-09-27)

The page reported a held-out accuracy *below* its baseline (21 % vs
25 %) and forecast 6-7 units for SKUs that sold 13-30 last month. Three
design faults, none of them tuning:

1. **No memory of recent sales.** The forecast conditioned on
   `month: "2026-05"`, a value no training row has, so it carried no
   evidence and the estimate fell back to the SKU's all-time average.
   The catalogue's volume grows ~17x over the 24 months, so the
   all-time average sits far below the current level.
2. **The wrong score.** `_evaluate predict units_sold` counts a hit only
   on the exact integer, against "always 1 unit". Nobody plans stock to
   the unit; the question is whether the forecast lands in the right
   range, and whether it beats the obvious rule.
3. **A random hold-out for a time series.** Test rows came from every
   month, so the model could learn from a SKU's *later* months when
   predicting an earlier one.

### Decision

- `monthly_sales` gains `units_last_month` (Int, 0 when the SKU sold
  nothing), and `units_bucket` / `units_last_month_bucket` (String):
  `0`, `1`, `2-3`, `4-7`, `8-15`, `16-31`, `32+`. Doubling-width ranges,
  because a forecast off by 2 units matters at 3 and not at 30.
- The forecast conditions on `units_last_month` instead of the unseen
  `month`.
- Accuracy is a **time split**: train on every month before the latest,
  test on the latest (`2026-04`), predicting `units_bucket`. `_evaluate`
  takes `train` / `test` propositions for this.
- The page shows three numbers side by side on the same test rows: the
  model, the **naive forecast** (next month lands in last month's
  range), and the majority range. The naive rule is the one to beat.
- Errors surface. The service no longer turns a failed Aito call into
  a forecast of 0 or an accuracy of 0 %; the endpoint returns 502.

### Aito usage

```json
{
  "train": {"month": {"$not": "2026-04"}},
  "test":  {"month": "2026-04"},
  "evaluate": {
    "from": "monthly_sales",
    "where": {"units_last_month_bucket": {"$get": "units_last_month_bucket"},
              "product_sku": {"$get": "product_sku"},
              "category": {"$get": "category"}, "brand": {"$get": "brand"},
              "pet_type": {"$get": "pet_type"}, "season": {"$get": "season"}},
    "predict": "units_bucket"
  },
  "select": ["accuracy", "baseAccuracy", "n"]
}
```

Verified on shared (read-only) that `train` is honoured: training on
the oldest month alone changes the accuracy on the same test rows.

This is an interim metric. The right score for a numeric forecast is
the error size (MAE) against the naive forecast. The engine documents
`_evaluate` over `estimate` (`select: [mae, rmse, r2]`) but v2.10.3
rejects it on both API versions ("missing 'evaluate.predict'"), and
computing it in the service would leak: `_estimate` has no train
filter, so a held-out row would inform its own forecast. When the
engine accepts it, the page moves to MAE against naive.

### Acceptance criteria

- The evaluation card shows model, naive and majority accuracy on the
  same held-out rows, and names the design (time split, ranges).
- When Aito fails, `/api/demand` returns 502 rather than zeros.
- A top mover that sold 20+ units last month is not forecast at the
  all-time average.

The original criterion "gain ≥ 0" is replaced: the gain that matters
is over the naive forecast, and the page reports it whichever way it
falls.
