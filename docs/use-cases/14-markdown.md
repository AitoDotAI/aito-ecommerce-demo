# Markdown Decision — Inventory + Demand + Price, one workflow

![Markdown](../../screenshots/inspect/14-markdown-default.png)

*Overstock SKUs surfaced from `inventory` × Aito's `_estimate
units_sold` at five markdown levels (0/5/10/15/20 %) per SKU =
proposed discount + recoverable margin + weeks-to-clear. The
merchandiser's "what should I discount and by how much" view.*

## Overview

The Inventory view answers *what's stuck*. The Markdown view
answers *what to do about it*. For each overstock SKU
(`current_stock > 5 × reorder_point`), Aito's `_estimate units_sold`
runs at five price points to walk the demand curve, then the
service picks the markdown that maximises recoverable revenue
while clearing the excess within 3 months. If no markdown ≤ 20 %
clears in horizon, the row is flagged "won't clear in horizon" —
honest signal that deeper cuts or liquidation are needed.

Three blocks per page load:

1. **KPI strip** — overstock SKUs targeted / tied capital € /
   margin recoverable €
2. **Proposal table** — 15 SKUs sorted by recoverable revenue,
   each row showing list price → markdown, weeks to clear, € recovered
3. **Per-row curve** — click a row to expand the 5-point
   `_estimate` sweep with the chosen discount highlighted

## How it works

### Overstock detection

```python
def _is_overstock(current: int, reorder_point: int) -> bool:
    return current > reorder_point * 5
```

Same band Inventory uses. Excess units = `current_stock − 2 ×
reorder_point` (we want to drain back to 2× headroom, not all the
way to zero).

### Demand curve via `_estimate`

```python
res = client.estimate(
    "monthly_sales",
    where={
        "product_sku": sku,
        "month":       "2026-05",
        "price_eur":   adjusted,          # ← the markdown price
        "pet_type":    recent.pet_type,
        "category":    recent.category,
        "brand":       recent.brand,
        "season":      _season_for(month),
    },
    estimate_field="units_sold",
)
```

Same body as the Price view's interactive chart. The `price_eur`
field is what shifts the K-NN's neighborhood — without it Aito
returns the SKU's unconditional expected demand.

### Picker

```python
target_weeks = CLEAR_HORIZON_MONTHS * 4         # 13 weeks
candidates = [c for c in curve if c.weeks_to_clear <= target_weeks]
if candidates:
    return max(candidates, key=lambda c: c.recoverable_revenue_eur)
# Fallback: nothing clears in horizon → return the deepest probe
return min(curve, key=lambda c: c.weeks_to_clear)
```

Recoverable revenue = `(price − unit_cost) × cleared_units`,
where cleared_units is capped at the excess. The picker prefers
the smallest discount that hits the clearance constraint — keeps
the view from over-recommending deep cuts when a light promo
would do the job.

### Concurrency

5 markdown probes × 15 SKUs would be 75 in-flight calls if fully
parallel. Aito's `inFlightWeight` ceiling is 48; we settled on
**sequential within a SKU, 4 SKUs at a time** = ~4 in-flight
calls at peak. Wall-clock ~18 s cold, cached 30 minutes after.

## Key features

### 1. Honest "won't clear in horizon" flag

When even -20 % can't clear the excess in 3 months, the row stays
in the table but flagged in red. The merchandiser sees "20 % off,
will take 18 weeks" and decides on their own whether to discount
further or liquidate. No silent dropping.

### 2. Some SKUs need no discount

The top result is often `0 % off` — high-margin SKUs where the
existing demand at list price clears the excess inside 3 months.
Demonstrates the view's value: it's not a "discount everything"
button; it's "discount exactly what needs discounting".

### 3. `_estimate` returning null gracefully handled

Aito's K-NN occasionally returns `null` for the deeper discounts
(no neighbor at that price). Fallback substitutes the SKU's mean
monthly units from `monthly_sales` so the curve stays continuous;
the row's clear-horizon flag tells the user when this happens.

## Data schema

Uses three existing tables — no schema additions.

```json
{
  "inventory":    "current_stock + reorder_point + unit_cost_eur",
  "products":     "list price + pet_type / category / brand for the _estimate where",
  "monthly_sales":"price_eur per row drives the K-NN's price ↔ demand correlation"
}
```

## Tradeoffs and gotchas

- **No time-decaying markdown ladders.** Real merchandising uses
  these ("start at 10 %, deepen if it doesn't clear in 2 weeks").
  Adding this would mean two more `_estimate` shapes per row.
- **Popularity proxy via price desc, not unit count.** The
  `products` table has no `total_units_sold` column; production
  code would join `monthly_sales` for real popularity.
- **Top result is sometimes 0 % off.** Demonstrates honest signal
  but reads "boring" on first glance — pair with the expanded
  curve to show why the picker landed there.

## What this demo abstracts away

- **A real pricing engine** with elasticity / cross-elasticity
- **Promotional calendar awareness** (Black Friday, end-of-season)
- **Margin floor enforcement** (price ≥ cost × markup)
- **Multi-step markdown sequences** ("price ladder" merchandising)
- **Cross-SKU bundling** ("buy 2 get 1 free" pricing math)

## Try it live

[**Open Markdown**](http://localhost:8500/markdown/). Cold load
~18 s (5 `_estimate` probes × 15 SKUs sequential per SKU,
parallel across); cached for 30 minutes. Click any row to see
the full markdown curve — the chosen discount is highlighted in
the curve so you see why it won the picker.
