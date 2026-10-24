# Price Intelligence — fair band + sweet-spot `_relate`

![Price](../../screenshots/13-price.png)

*Per-SKU price stats over `product_states` (mean ± 1.5σ, outlier
flag, observation count), a demand curve from `_estimate units_sold`,
and `_relate` over discount band ↔ category, which on today's data
finds no category discounted more than another (see the ADR 0016
amendment).*

## Overview

Two questions a price manager asks daily:

1. *Is this SKU's list price reasonable* compared to how we've
   actually sold it?
2. *Which categories respond to discounts*, and which sell
   equally well at list?

Aito answers both from the `product_states` table (ADR 0032) — one
row per product per month on sale, with the observed price and
discount, and the rest of the product's state that month (on offer,
stars, new, a rival's launch, a price rise). The fair-band
half is pure aggregation; the sweet-spot half uses three parallel
`_relate` calls over discount bands.

## How it works

### Fair-band — Python aggregation over `_search`

```python
# src/price_service.py — get_prices()
prices = _fetch_prices(client)   # paged _search over product_states
by_sku = group_by("product_sku")(prices)

for sku, rows in by_sku.items():
    prices_eur = [r["price_eur"] for r in rows]
    mean = sum(prices_eur) / len(prices_eur)
    std  = math.sqrt(sum((p - mean) ** 2 for p in prices_eur) / len(prices_eur))
    list_price = products[sku]["price_eur"]
    outlier = list_price < mean - 1.5*std or list_price > mean + 1.5*std
```

Aito retrieves the rows; the stats are aggregated locally. For
15,157 rows that's cheap.

### Sweet-spot — three parallel `_relate` calls

```python
bands = [
    ("list",  {"discount_pct": {"$lte": 5.0}}),
    ("mild",  {"discount_pct": {"$and": [{"$gt": 5.0}, {"$lte": 15.0}]}}),
    ("promo", {"discount_pct": {"$gt": 15.0}}),
]

def fetch(band, where):
    return client.relate(
        table="product_states",
        where=where,
        relate_field="product_sku.category",
        limit=8,
    )
```

The `relate` field traverses one hop: `product_sku.category`
fetches the linked product's category, which lives on `products`,
not on `product_states`.

Each band returns categories that over-index there. Pseudo-output:

```
list   (≤ 5 % off)  → cat=dry-food   lift 1.23×  (staples sell at list)
mild   (5-15 % off) → cat=treats     lift 1.41×
promo  (> 15 % off) → cat=toys       lift 2.15×  (promo-sensitive)
promo  (> 15 % off) → cat=dry-food   lift 0.72×  (rarely deep-discounted)
```

### The continuous-feature banding pattern

`_relate` over a Decimal column like `discount_pct` would emit
one row per unique value — useless. The three-band trick (split
the column with `$where` filters, run parallel calls, merge
results) transfers to any continuous feature.

## Key features

### 1. Outlier flagging surfaces actionable rows first

Sort by `outlier ↓ then observation_count ↓`. The user lands on
"these N SKUs' list prices are out of band — review pricing".
Without the outlier flag the table would be a 700-SKU stats dump.

### 2. Sweet-spot lifts in both directions

*On today's data no lift passes the filter, so the page leaves this card out (ADR 0016 amendment, 2026-10-11).*

Lifts > 1.15 (red chip ↑) = "this band over-indexes for this
category — discount-sensitive". Lifts < 0.85 (green chip ↓) =
"this band under-indexes — list-price-loyal customers". Both are
useful.

### 3. Cross-table `_relate` via link traversal

`relate: "product_sku.category"` is one hop from `product_states`
through `product_sku` to `products.category`. Aito does the
traversal natively; the alternative would be denormalising
category onto `product_states`.

## Data schema

```json
{
  "product_states": {
    "type": "table",
    "columns": {
      "product_state_id": { "type": "String" },
      "product_sku":      { "type": "String", "link": "products.sku" },
      "month":            { "type": "String" },
      "price_eur":        { "type": "Decimal" },
      "list_price_eur":   { "type": "Decimal" },
      "discount_pct":     { "type": "Decimal" },
      "on_offer":         { "type": "Boolean" },
      "discount_band":    { "type": "String" },
      "rating_band":      { "type": "String" },
      "age":              { "type": "String" },
      "rival_launched":   { "type": "Boolean" },
      "price_change":     { "type": "String" }
    }
  }
}
```

15,157 rows: every product in every month it is on sale (launched
products start mid-window). `impressions`, `order_lines` and
`monthly_sales` link to it through `product_state`. Most months sell
near list: about 82 % within ±5 % of list, 6 % mild discount (5-15 %
off) and 13 % promo (> 15 % off), from `gen_product_states` in
`data/catalogue_events.py`.

## Tradeoffs and gotchas

- **No competitor prices**. The fair band reflects *this* shop's
  pricing history, not the market's. A real product would layer
  external feeds.
- **No elasticity model**. We surface "promo bands over-index for
  toys" but not ∂units/∂price. Real elasticity needs careful
  counter-factual reasoning Aito doesn't natively offer.
- **`_relate` over linked column slows by ~30 %** vs a non-linked
  column — Aito does the join row-by-row. For our 15k rows it's
  fine; on millions of rows you'd denormalise.
- **`band_lower_eur` can go negative** if a SKU has wildly
  varying observed prices; we floor at 0.0 for display.

## What this demo abstracts away

- **A real pricing engine** with elasticity / cross-elasticity
- **Promotional calendar awareness** (Black Friday, holidays)
- **Margin floor enforcement** (price ≥ cost × markup)
- **Competitor scraping / price-match rules**

## Price ↔ Demand / Profit scatter

Click any row in the fair-band table to load that SKU's
interactive chart. Y-axis toggle switches between **Demand**
(units sold) and **Profit** (€ per month).

```
sku → _search monthly_sales where {product_sku: sku}    → historical
   → _search inventory where {sku}                        → unit_cost
   → _estimate units_sold × 7 parallel:
       price_eur = mean_price × [0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15]
                                                          → demand curve
```

The 7-point curve is Aito's `_estimate units_sold` over
`monthly_sales` with `price_eur` in the where — this is why
`monthly_sales` carries a `price_eur` column (= revenue / units
per row). Without it Aito couldn't condition on price.

Profit at each curve point = `(price - unit_cost) × units`.
The max-profit point (yellow ring in profit mode) is the
margin × demand sweet spot — usually NOT the cheapest price
because the unit-cost floor truncates the margin.

Mirrors `aito-demo`'s `PricingPage` scatter, adapted to our
two-table layout (monthly_sales + inventory).

## What if — one price, and why that many units

Below the curve, a what-if panel asks one `_estimate` at the price you
choose (a curve point, the slider, or `?price=` in the URL):

```json
{ "from": "monthly_sales",
  "where": { "product_sku": "SKU-PT-0133", "units_last_month": 23, "pet_type": "dog",
             "category": "wet-food", "brand": "Hill's Science Plan", "season": "spring",
             "price_eur": 4.68 },
  "estimate": "units_sold", "model": "regression", "select": ["estimate", "why"] }
```

With `model: "regression"` the `why` is `exp(mean + Σ factors)`, so the
panel shows a typical month (e^mean, 3.0 units here) times one factor
per field, and the rows multiply out to the estimate (5.8 units). Factors
under 0.5 % fold into "Other factors". The curve asks the same model, so
a point on it and the what-if at that price agree; `./do aito-check`
pins that.

## Try it live

[**Open Price**](http://localhost:8500/price/). Cold load ~1 s
(one big `_search` + three parallel `_relate`); cached for 30
minutes. Try the sweet-spot section — the chip with the highest
lift surfaces a category-discount pair that's the shop's
strongest promo response.
