# Shop analytics — the patterns behind the shop

*What goes with a click and a purchase, who buys what and when, which
categories share a basket, and which search words convert. Every number
is a `_relate` lift with its counts and a 95 % interval, about 21 queries
in parallel, all live.*

## Overview

The shopper-facing views (For You, Smart Search) use these patterns
without showing them. A shop owner wants to see them: do low-rated
products sell less, is anyone offered what they just bought, what does
summer change, which search words end in a sale. This view (ADR 0031)
answers each with `_relate` and shows only the lifts whose interval
stays clear of 1.

The KPI and the "who/when" choice are in the URL
(`/shop-analytics/?kpi=clicked&who=grain-free`), so a link opens the
same state.

## How it works

### Reading a lift as a row

Every hit of a field-form `_relate` carries a `lift` and the four counts
behind it in `fs`. `src/lift_rows.py` turns a hit into a row:

```
rating = 1–2 stars   0.79×   923 of 12,135 purchases   95 %: 0.73–0.85
```

The interval is `lift_interval` from `src/price_bands.py` (log relative
risk on the counts), and `is_real_lift` drops a lift whose interval
includes 1 or that rests on fewer than 30 rows, the rule Price and Demand
already use. The interval is rounded outward and checked again, so
nothing is shown as "0.93–1.00". A field that keeps no row is listed
under "Also checked, no effect".

### 1. What goes with a click and a purchase

```python
# src/shop_analytics_service.py — funnel_body()
{"from": "impressions", "where": {"purchased": True},
 "relate": "product_sku.rating_band", "limit": 50}
```

One call per field: the product's rating band and category (both through
the `product_sku` link), the shopper's segment, lifestyle and diet rule,
whether the product was in their last order (`just_bought`, a Boolean),
and the surface. The toggle swaps `purchased` for `clicked`.

On the test env `shoppers` (2026-10-13), purchases:

```
in their last order = yes   0.48×      40 of 12,135   0.35–0.67
rating = 1–2 stars          0.79×     923 of 12,135   0.73–0.85
category = dental treats    1.77×     663 of 12,135   1.63–1.92
```

With clicks, the 1–2 star band has no effect (1.01×): ADR 0030 plants
poor quality at the add-to-cart and purchase steps, not the click.

### 2. Who buys what, and when

```python
# who_body() for "summer": the season's months from Demand
{"from": "order_lines",
 "where": {"order_id.month": {"$or": ["2025-08", "2025-07", ...]}},
 "relate": "product_sku.category", "limit": 30}
```

The same query relates `product_sku.dietary` too, because a diet rule
shows in the dietary line rather than the category. The selector offers
the four seasons (`season_months` from `src/demand_service.py`), the five
segments and the four diet rules.

```
summer      → health 3.99× (375 of 6,489 lines), grooming 3.89×
grain-free  → dietary = grain-free 3.08× (1,171 of 2,003 lines)
```

### 3. Baskets

The order-level co-occurrence query Basket Rules mines (ADR 0022), one
per anchor category:

```python
{"from": "orders", "where": {"line_categories": {"$match": "dog_dryfood"}},
 "relate": "line_categories", "limit": 30}
```

The anchor's own token is skipped, and A + B and B + A are shown once.
Dog dry-food + dental-treats: 2.79× (2,699 of 4,100 orders). Product
pairs (`orders.skus`) are left out: each pair shares only 3–8 orders.
Rules with confidence and support are in Basket Rules, which the card
links to.

### 4. Search words

`search_query` is a whitespace Text column, so a `_relate` on it returns
one hit per word, in `$has` form. The obvious query has the wrong
baseline:

```python
{"from": "impressions", "where": {"surface": "search", "purchased": True},
 "relate": "search_query"}
```

`_relate` divides by the word's share of *all* impressions, and only
search impressions have a query, so every word comes out about 2.5×
("food" 2.76×, though it converts a little below the average search). A
nested `from` would restrict the population, but `_relate` answers 501 to
that on 2.11.4.

So the view sends the query twice, with and without `purchased`, and
divides the counts (`src/search_words.py`):

```
lift = (purchases with the word / search purchases)
     / (impressions with the word / search impressions)
```

That is the word's conversion over the average search's (11.7 %).
"veggie" converts at 26.8 % (2.30×); "whitefish" at 7.2 % (0.62×).

## Latency

About 0.7–1.1 s for the whole page from a cold start, because the 21
queries run eight at a time and each takes 5–60 ms on the engine. That is
under the ~3 s at which the heavier views are precomputed, so this one is
neither cached nor precomputed.

## Data schema

| Section | Table | Columns |
|---|---|---|
| Clicks and purchases | `impressions` | `clicked`, `purchased`, `product_sku` → `products.rating_band`, `category`; `customer_segment`, `customer_lifestyle`, `customer_diet_rule`, `just_bought`, `surface` |
| Who and when | `order_lines` | `order_id` → `orders.month`; `customer_segment`, `customer_diet_rule`; `product_sku` → `products.category`, `dietary` |
| Baskets | `orders` | `line_categories` (Text) |
| Search words | `impressions` | `surface`, `purchased`, `search_query` (Text) |

## Tradeoffs and gotchas

- **`product_category` is not related.** It is the denormalised copy of
  `product_sku.category`, and both return identical hits.
- **Thin strong effects are not shown.** A lift needs 30 rows. Small
  animal owners' 3 wet-food lines (0.03×) are a real absence, but the
  view can't tell it from chance at that count.
- **A Boolean has two rows.** `just_bought = no` sits at 1.01×, with an
  interval that touches 1 once rounded, so it is left out.
- **Needs ADR 0030's data.** The rating band, diet rule, `just_bought`
  and multi-word search queries exist only in the test env `shoppers`
  until master is reloaded.

## Try it live

```bash
AITO_ENV=shoppers ./do dev
# → http://localhost:8500/shop-analytics/
```
