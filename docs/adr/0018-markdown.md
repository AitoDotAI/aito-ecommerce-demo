# ADR 0018 — Markdown decision view

**Status:** Accepted

## Context

The Inventory view surfaces overstock SKUs and their tied capital
in €, but stops at "you have €14k stuck in slow-moving stock". The
merchandiser's next question — *what discount clears this, and
what does it cost in margin?* — was unanswered. The Price view has
the demand-curve `_estimate` shape that answers exactly that, but
only for one SKU at a time via the interactive chart.

Markdown ties the two together as a one-call answer: *for every
overstock SKU, here's the proposed discount, the weeks to clear,
the recoverable revenue, the margin you're giving up.* Replaces a
weekly meeting between merchandising and finance with a single
view.

## Decision

A new "Markdown" view in the Operate section, between Inventory
and Price. For each overstock SKU (current_stock > 5 × reorder_point,
the same band Inventory uses), call Aito's `_estimate units_sold`
at **five markdown levels (0, 5, 10, 15, 20 %)**. Compute the
curve point that maximises *recoverable revenue =
(price − unit_cost) × cleared_units* subject to the soft
constraint *clear excess within 3 months*. If no markdown ≤ 20 %
clears the excess in horizon, fall back to the deepest probe and
flag the row "won't clear in horizon" — honest signal that this
SKU needs liquidation or a deeper cut than the curve covers.

### Aito usage

```json
POST /api/v1/_estimate
{
  "from":  "monthly_sales",
  "where": {
    "product_sku": "SKU-PT-0042",
    "month":       "2026-05",
    "category":    "dry-food",
    "brand":       "Royal Canin",
    "season":      "spring",
    "price_eur":   72.20
  },
  "estimate": "units_sold"
}
```

Same body shape as the Price view's demand-curve probe. The
`price_eur` field is what shifts the K-NN's neighborhood —
without it Aito returns the SKU's unconditional expected demand,
which doesn't model the markdown response we need here.

### Concurrency + rate limits

5 markdown probes × 15 SKUs would be 75 calls if run with maximum
parallelism. Aito's `inFlightWeight` capacity is 48; the markdown
probes alone could pace fine, but stacking with other warmups
caused 429s in early tests. The shape we settled on:

- **Sequential within a SKU** (5 probes in series), and
- **Parallel across SKUs** (4 SKUs at a time)

= ~4 in-flight Aito calls at peak. Wall-clock ~18 s for the full
15-SKU sweep on a cold cache, cached for 30 minutes after.

### `_estimate` returning null

Aito's K-NN occasionally returns `null` for the deeper discounts
because the SKU never sold below that price in the training data.
Fallback: substitute the SKU's mean monthly units from
`monthly_sales`. Keeps the curve continuous and lets the picker
still consider that row instead of skipping it. The row's "won't
clear in horizon" flag tells the merchandiser when this happens.

## Acceptance criteria

- A user can open `/markdown` and see ~15 overstock SKUs ranked by
  recoverable revenue with the proposed discount per row.
- KPI strip rolls up tied capital, capital freed (cost basis of
  cleared units), and margin earned at the proposed markdowns.
- Clicking a row reveals the full 5-point curve with the chosen
  discount highlighted.
- SKUs that won't clear in horizon are visibly flagged.

## Demo impact

- **Inventory** stays the "what's stuck" view.
- **Markdown** becomes the "what to do about it" view.
- **Price** stays the per-SKU explorer.

The Markdown view answers a CFO-language question directly: "If
we discount our overstock as proposed, we recover €X of capital
and earn €Y of margin while clearing 318 excess units." Inventory
+ Price already have the data; this view composes them.

## Out of scope

- **Time-decaying markdown ladders** (start at 10 %, deepen if
  it doesn't clear in 2 weeks). Real merchandising uses these but
  they'd take a second `_estimate` shape per row and complicate
  the view's read.
- **Cross-SKU bundling** ("buy 2 get 1 free" math). Different
  query shape entirely.
- **Discount-band sweet spot** vs the per-SKU optimum — Price's
  `_relate` already covers the category-level "which bands move
  which categories" story.

## References

- Inventory view's overstock detection — ADR 0015.
- Price view's `_estimate` demand-curve shape — ADR 0016.
- The realistic margin + elasticity work that made the Markdown
  view's curve interpretable — ADR 0017 §"Price-curve realism".
