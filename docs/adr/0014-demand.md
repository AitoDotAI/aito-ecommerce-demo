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
