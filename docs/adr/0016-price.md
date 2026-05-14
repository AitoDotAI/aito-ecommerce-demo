# ADR 0016: Price Intelligence — fair-band + sweet-spot `_relate`

**Status:** Accepted
**Date:** 2026-05-13
**Deciders:** Antti

## Context

Pricing decisions on a 700-SKU catalog are a mix of "is our
sticker price reasonable" (fair band) and "what discount level
drives volume in which category" (sweet spot). Most shops do
both manually — finance reviews margin tables, marketing tests
promo levels. Aito's `_search` aggregation + `_relate` give a
single-page answer to both.

The Operate section's third view; companion to Demand and
Inventory. Less viscerally compelling than Inventory's "cash at
risk", but a clean Aito-skills demo for `_relate` over a
synthesised observation panel.

## Aito usage

### Fair-band: bulk `_search` + Python aggregation, with one
### `_aggregate` for per-SKU drilldown

Catalog-wide outlier scan needs stats for every SKU. Two paths:

1. **Page-fetch all rows once, aggregate in Python** — one
   `_search` call (paged), ~11k rows. Cheap, no rate-limit risk.
2. **N parallel `_aggregate` calls** (one per SKU) — Aito-side
   stats, but 658 parallel calls trip Aito's rate limiter at
   429 Too Many Requests.

We chose (1) for the bulk scan and added a single targeted
`_aggregate` call for the top-displayed SKU's drilldown — that's
the body surfaced in the Aito side panel, so the endpoint is
still visible in the demo. See `docs/aito-cheatsheet.md`
§`_aggregate` for the per-SKU shape.

```json
{
  "from": "price_history",
  "where": {"product_sku": "SKU-PT-0042"},
  "aggregate": [
    "price_eur.$mean",
    "price_eur.$min",
    "price_eur.$max"
  ]
}
```

Note: `price_eur.$mean` automatically returns
`mean.standardDeviation` and `mean.variance` in the same
response — there's no separate `$standardDeviation` keyword.

### Sweet-spot: three parallel `_relate` calls

```json
{
  "from": "price_history",
  "where": { "discount_pct": { "$gt": 15.0 } },
  "relate": "product_sku.category"
}
```

Plus the matching queries for `discount_pct ≤ 5` (list price) and
`5 < discount_pct ≤ 15` (mild discount). The relate over the
linked column (`product_sku.category`) leverages Aito's
single-hop link traversal — `category` lives on `products`, not
on `price_history`.

Each band returns which categories over-index there. Reading
example: "promo-priced (> 15 % off) toys lift 2.1× over baseline
— customers respond to deep discounts on toys more than on
food".

### Price ↔ demand scatter chart

Mirrors `aito-demo`'s `PricingPage` scatter — historical
`(price, units)` pairs as light blue dots, Aito's `_estimate
units_sold` at +/-15 % adjusted prices as the orange curve,
current list price as a star.

`/api/price/detail?sku=…` returns:
- **historical** — per-month `(price, units, revenue, profit)`
  from `monthly_sales` (joined with `inventory.unit_cost_eur` for
  the profit calc)
- **curve** — 7 parallel `_estimate units_sold` calls at
  adjustments `[-15, -10, -5, 0, +5, +10, +15] %`. The 0 % call
  also pulls the `why` neighbor tree for the popover (future
  follow-up).

The Y-axis toggles between **Demand** (units) and **Profit** (€).
Max-profit point on the curve gets a yellow ring in profit mode
— typically NOT at the lowest price; the unit-cost floor moves
the optimum.

For the demand-curve to be Aito-driven, `monthly_sales` carries
a `price_eur` column (realised revenue / units per row). Without
it `_estimate units_sold` couldn't condition on price.

## Decision

### New `price_history` table

Per-SKU per-month price observation. Same row count as
`monthly_sales` (~11,100 rows) because we only emit a price
observation for months where the SKU had sales.

| Column | Type | Notes |
|---|---|---|
| `price_observation_id` | String, PK | `<sku>-<month>` |
| `product_sku` | String, link → products.sku | |
| `month` | String | YYYY-MM |
| `price_eur` | Decimal | Observed price this month |
| `list_price_eur` | Decimal | The SKU's current retail price (constant per SKU) |
| `discount_pct` | Decimal | `(list - price) / list × 100`, can be negative |

Engineered distribution of discount_pct:

| Band | Probability | Range |
|---|---|---|
| Near list | ~70 % | `-5 % … +5 %` |
| Mild discount | ~15 % | `5 % … 15 %` |
| Promo | ~15 % | `15 % … 30 %` |

The mild + promo bands together share roughly the same volume.
Categories with promo-sensitive customers (toys, treats) lift in
the promo `_relate`; staple categories (food, litter) tend to
sit at list.

### Fair-band view

Table sorted by `outlier ↓` then `observation_count ↓`. Outliers
surface first because they're the actionable rows ("this list
price is too high relative to history").

### Sweet-spot view

Top 12-15 `(discount_band, category)` pairs sorted by
`|lift - 1|`. Both directions matter — promo-sensitive AND
list-loyal categories are useful insights.

## Acceptance criteria

- [x] A user can open `/price` and see four KPI cards: SKUs
      tracked, total observations, outlier SKUs, promo share %.
- [x] Fair-band table shows ≥ 1 outlier SKU (engineered to land
      a small number).
- [x] Sweet-spot section shows 8-15 chip rows with lifts > 1.15
      or < 0.85 across the three discount bands.

## Demo impact

The third Operate-section view. Doesn't add a *new* Aito moment
on its own — the `_relate` pattern was already in Bought
Together / Pattern Explorer / Churn — but it applies the pattern
to a continuous-but-banded feature (discount_pct), which is a
useful worked example for any "what price drives volume" question
viewers ask.

## Out of scope

- **Price elasticity modelling**. We don't surface
  ∂units/∂price; we just relate band ↔ category. Real elasticity
  needs careful counter-factual reasoning Aito doesn't natively
  support.
- **Competitor prices**. No external feed of "what other shops
  charge for the same SKU". Fair-band is anchored on this shop's
  own history.
- **Predictive pricing** ("what's the optimal price for this
  SKU"). `_predict revenue_eur from {sku, price}` is plausible
  but adds noise to the demo's narrative.

## Consequences

**Good:**
- Adds a clean worked example of `_relate` over a *banded*
  continuous feature via `$where {discount_pct: {$gt: ...}}` —
  the pattern transfers to any continuous-column analysis.
- The sweet-spot output is genuinely actionable for the
  merchandising audience (unlike, say, Pattern Explorer which
  is more analyst-facing).

**Bad:**
- The fair-band math (mean ± 1.5σ over observed prices) is
  Python-side aggregation; Aito does the row retrieval, not the
  stats. A real product would pre-aggregate in the warehouse.
- Synthetic price data — promo cadence is uniform random rather
  than tied to seasons / inventory state. Real promo data shows
  pre-Christmas, end-of-season clearance, etc.

## Notes

The three-band `_relate` shape is a useful generic pattern:
when you want `_relate` over a continuous column, slice it into
~3-5 bands with `$where` and run parallel calls. The merged
results give you "lift per band" without trying to make Aito
quantise on its own.
