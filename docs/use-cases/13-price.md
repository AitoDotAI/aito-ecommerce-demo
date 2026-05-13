# Price Intelligence — fair band + sweet-spot `_relate`

![Price](../../screenshots/13-price.png)

*Per-SKU price stats over `price_history` (mean ± 1.5σ, outlier
flag, observation count) + Aito `_relate` over discount band ↔
category surfacing "promo-priced toys sell 2.4× more units than
list-priced toys" patterns.*

## Overview

Two questions a price manager asks daily:

1. *Is this SKU's list price reasonable* compared to how we've
   actually sold it?
2. *Which categories respond to discounts*, and which sell
   equally well at list?

Aito answers both from the `price_history` panel — one row per
SKU per month with the observed price + discount. The fair-band
half is pure aggregation; the sweet-spot half uses three parallel
`_relate` calls over discount bands.

## How it works

### Fair-band — Python aggregation over `_search`

```python
# src/price_service.py — get_prices()
prices = _fetch_prices(client)   # paged _search over price_history
by_sku = group_by("product_sku")(prices)

for sku, rows in by_sku.items():
    prices_eur = [r["price_eur"] for r in rows]
    mean = sum(prices_eur) / len(prices_eur)
    std  = math.sqrt(sum((p - mean) ** 2 for p in prices_eur) / len(prices_eur))
    list_price = products[sku]["price_eur"]
    outlier = list_price < mean - 1.5*std or list_price > mean + 1.5*std
```

Aito retrieves the rows; the stats are aggregated locally. For
11,100 rows that's cheap.

### Sweet-spot — three parallel `_relate` calls

```python
bands = [
    ("list",  {"discount_pct": {"$lte": 5.0}}),
    ("mild",  {"discount_pct": {"$and": [{"$gt": 5.0}, {"$lte": 15.0}]}}),
    ("promo", {"discount_pct": {"$gt": 15.0}}),
]

def fetch(band, where):
    return client.relate(
        table="price_history",
        where=where,
        relate_field="product_sku.category",
        limit=8,
    )
```

The `relate` field traverses one hop: `product_sku.category`
fetches the linked product's category, which lives on `products`,
not on `price_history`.

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

Lifts > 1.15 (red chip ↑) = "this band over-indexes for this
category — discount-sensitive". Lifts < 0.85 (green chip ↓) =
"this band under-indexes — list-price-loyal customers". Both are
useful.

### 3. Cross-table `_relate` via link traversal

`relate: "product_sku.category"` is one hop from `price_history`
through `product_sku` to `products.category`. Aito does the
traversal natively; the alternative would be denormalising
category onto `price_history` (extra ~11k denormalised values).

## Data schema

```json
{
  "price_history": {
    "type": "table",
    "columns": {
      "price_observation_id": { "type": "String" },
      "product_sku":          { "type": "String", "link": "products.sku" },
      "month":                { "type": "String" },
      "price_eur":            { "type": "Decimal" },
      "list_price_eur":       { "type": "Decimal" },
      "discount_pct":         { "type": "Decimal" }
    }
  }
}
```

~11,100 rows. Engineered discount distribution: 70 % near list
(±5 %), 15 % mild discount (5-15 % off), 15 % promo (15-30 % off).

## Tradeoffs and gotchas

- **No competitor prices**. The fair band reflects *this* shop's
  pricing history, not the market's. A real product would layer
  external feeds.
- **No elasticity model**. We surface "promo bands over-index for
  toys" but not ∂units/∂price. Real elasticity needs careful
  counter-factual reasoning Aito doesn't natively offer.
- **`_relate` over linked column slows by ~30 %** vs a non-linked
  column — Aito does the join row-by-row. For our 11k rows it's
  fine; on millions of rows you'd denormalise.
- **`band_lower_eur` can go negative** if a SKU has wildly
  varying observed prices; we floor at 0.0 for display.

## What this demo abstracts away

- **A real pricing engine** with elasticity / cross-elasticity
- **Promotional calendar awareness** (Black Friday, holidays)
- **Margin floor enforcement** (price ≥ cost × markup)
- **Competitor scraping / price-match rules**

## Try it live

[**Open Price**](http://localhost:8500/price/). Cold load ~1 s
(one big `_search` + three parallel `_relate`); cached for 30
minutes. Try the sweet-spot section — the chip with the highest
lift surfaces a category-discount pair that's the shop's
strongest promo response.
