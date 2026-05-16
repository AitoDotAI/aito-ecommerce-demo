# ADR 0015: Inventory Intelligence — the killer Operate view

**Status:** Accepted
**Date:** 2026-05-13
**Deciders:** Antti

## Context

Inventory is the merchandiser's daily pain — too much stock and
cash is tied up, too little and the next purchase is a stockout.
Most e-commerce shops manage this with a calendar-style rule:
"reorder when days-of-supply < lead time + safety". That rule
doesn't predict; it reacts. The interesting question is "given
this month's sales and Aito's forecast, which SKUs need a
reorder *now* — and what's the cash exposure if we don't?".

The **killer feature** of the Operate section: predict who's
about to stock out, rank by revenue at risk, show the suggested
reorder quantity, surface the per-row `$why` for the demand
forecast that drove the recommendation.

## Aito usage

For each critical SKU (stock < reorder_point), one `_estimate`
— same shape as Demand's per-SKU forecast (ADR 0014). We use
`_estimate` (not `_predict`) because we want the *expected*
units, not the most-probable specific integer; otherwise the
revenue-at-risk calculation reads as "10 % chance we'll sell 3
units" rather than "we expect 3-4 units on average".

```json
{
  "from": "monthly_sales",
  "where": {
    "product_sku": "SKU-PT-0042",
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

Plus a single `_search inventory limit=0` per band for the KPI
strip (total / critical / overstock counts) and one
`_search monthly_sales` paged to compute daily-demand per SKU.

## Decision

### New `inventory` table

One row per SKU, snapshot at the frozen demo today (2026-04).

| Column | Type | Notes |
|---|---|---|
| `sku` | String, link → products.sku | PK |
| `current_stock` | Int | Synthesised — engineered band distribution (see below) |
| `unit_cost_eur` | Decimal | ≈ 60 % of retail price |
| `lead_time_days` | Int | 7-28 by category |
| `reorder_point` | Int | `lead-time × daily-demand + safety_stock` |
| `safety_stock` | Int | `daily-demand × 7` |
| `supplier` | String | `S-01` … `S-12` |
| `last_received_month` | String | Most recent restock month |

`current_stock` is engineered into four bands so the demo's
"reorder workflow" surface always has meaningful traffic:

| Band | Share | Range |
|---|---|---|
| critical | ~10 % | `stock < reorder_point` |
| low | ~25 % | `reorder_point ≤ stock < 1.4 × reorder_point` |
| ok | ~50 % | `1.5 × reorder_point ≤ stock < 5 × reorder_point` |
| overstock | ~15 % | `stock > 5 × reorder_point` |

### KPI strip + reorder queue + overstock list

Three blocks, all served by one cached request:

1. **KPI strip** (5 cards): total SKUs, critical count, overstock
   count, tied capital €, revenue at risk €. Tied capital sums
   `max(0, stock - 2 × reorder_point) × unit_cost` over the
   overstock band. Revenue at risk = sum of `(forecast - stock)`
   shortfalls × retail price across critical SKUs.

2. **Reorder queue** (left, 60 %): the critical SKUs scored by
   `_predict units_sold` next month, sorted by revenue at risk
   descending. Each row has stock + forecast + suggested reorder
   qty + supplier + lead time + the **?** popover.

3. **Overstock list** (right): top 20 by tied capital with
   months-of-supply and €/unit cost.

### Suggested reorder quantity

```python
suggested = max(
    0,
    forecast_units + safety_stock - current_stock
)
```

— meet next month's forecast and rebuild the safety buffer.
Simple arithmetic; the *prediction* lives in `forecast_units`.

## Acceptance criteria

- [x] A user can open `/inventory` and see the 5-card KPI strip
      with tied capital and revenue at risk both > €0.
- [x] The reorder queue shows up to 25 critical SKUs sorted by
      revenue at risk, with each row carrying its own ? popover
      decomposing the `units_sold` forecast.
- [x] The overstock list shows up to 20 SKUs with months-of-supply
      ≥ 5.
- [x] Forecast accuracy is shown via the Demand view's
      `_evaluate` (separate page, same data).

## Demo impact

Adds the **seventh demo moment**: "Aito ranks 25 at-risk SKUs by
revenue at risk in 3 seconds, with per-row `$why` explaining
each forecast". The strongest "cash impact" view in the demo —
the reorder queue's revenue-at-risk column is the merchandiser's
day-one metric.

## Out of scope

- **A real reorder workflow** (PO generation, supplier
  notification). The view shows the suggestion; clicking
  "Reorder now" doesn't actually persist a PO. ERP demo's
  `submission_store` would be the right starting point if we
  ever wire it.
- **Multi-warehouse stock**. Single stock value per SKU.
  Production wants per-location.
- **Backorder modelling**. Stockouts are binary here ("can serve
  next month's demand or can't"). Real systems carry a
  partial-fulfilment / backorder graph.
- **Demand-driven safety stock**. Safety stock is a simple
  `7 × daily-demand` heuristic. Stochastic methods (newsvendor,
  service-level target × demand σ) are out of scope.

## Consequences

**Good:**
- Demonstrates Aito as the *predictive* layer behind a
  rules-style arithmetic UI — the days-of-supply / reorder-point
  math is dumb, but the forecast that feeds it isn't.
- Reuses Demand's `_predict units_sold` body verbatim — the
  Aito panel shows the same query shape on both pages.
- The €€€ figures (tied capital, revenue at risk) are the
  merchandising audience's daily KPIs — speaks their language.

**Bad:**
- 25 parallel `_predict` calls per page load (~3 s warm).
  Mitigated by 30-min cache.
- The synthesised stock values aren't grounded in real warehouse
  data; the bands are engineered for demo visibility. A real
  installation would feed live WMS data instead.

## Notes

The 25-SKU cap on the reorder predict fan-out is a trade-off:
larger N would surface more critical SKUs but cost proportional
Aito calls. 25 covers ~30 % of the critical band on the engineered
fixture (~75 SKUs total). Production would predict for all
critical SKUs offline and cache nightly.
