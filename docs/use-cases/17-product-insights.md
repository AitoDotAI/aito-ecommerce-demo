# Product Insights — one product, its funnel and its buyers

*Pick a product and see how it converts, on which surface, which customer
profiles buy it more than average, how many units it sells per month, and
what its reviews say. One `_batch` of counts and one `_relate` per customer
column, all live.*

## Overview

The other analytics views look at the whole store or at categories. A
merchandiser's everyday question is about one product: is it converting,
where is it found, and who is it actually for? This view answers that for
any SKU, and the URL (`/product-insights/?sku=SKU-PT-0177`) opens the same
product for anyone you send it to.

## How it works

### Who buys it — `_relate` over the product's order lines

```python
# src/product_insights_service.py — _buyer_rows()
client.relate(
    table="order_lines",
    where={"product_sku": sku},
    relate_field="customer_segment",
    limit=10,
)
```

One call per customer column that is denormalised onto `order_lines`
(segment, pet size, lifestyle, health focus, treat affinity, brand
loyalty), fired in parallel. With the product as the condition, each
hit's `lift` is how much more common that profile is among this
product's order lines than among all order lines. Its `fs` carries the
counts: `fOnCondition` is the product's lines with that profile, and
`fCondition` is all of the product's lines.

For Puppy Cheese Treats (SKU-PT-0177) on master:

```
segment = dog_owner    1.42×   99 of 117 lines
segment = multi_pet    0.97×   17 of 117 lines
segment = cat_owner    0.52×    1 of 117 lines
```

The cat-owner row shows why the counts are on screen. One line out of 117
would be a near-zero lift, but Aito smooths small counts toward 1, so it
reads 0.52×. The page shows "1 of 117 lines" next to it, so nobody mistakes
it for a finding. Lifts within ±0.15 of 1 are drawn in the neutral colour.

### Funnel, surfaces and reviews — one `_batch` of counts

```python
# src/product_insights_service.py — _count_queries()
{"from": "impressions", "where": {"product_sku": sku, "purchased": True}, "limit": 0}
```

The view needs about 20 counts:
- the funnel's 4 steps;
- impressions and purchases for each of the 4 surfaces;
- the 5 ratings and the 3 sentiments.

They are independent, so they go in one `_batch`: one round-trip
instead of twenty. Two consistency checks fail loudly instead of drawing
a wrong chart:
- the surfaces must cover every impression;
- the reviews counted by rating must equal the reviews counted by
  sentiment.

### Units per month

`monthly_sales` has a row only for months with sales. The view fills the
months in between with 0, and the chart's caption says so.

## Data schema

| Panel | Table | Columns |
|---|---|---|
| Funnel, surfaces | `impressions` | `product_sku`, `surface`, `clicked`, `added_to_cart`, `purchased` |
| Who buys it | `order_lines` | `product_sku`, `customer_*` (denormalised profile) |
| Units per month | `monthly_sales` | `product_sku`, `month`, `units_sold` |
| Reviews | `reviews` | `product_sku`, `rating`, `sentiment` |

## Tradeoffs and gotchas

- **The funnel's rates are each of the step before**: "80% of added to
  cart" means 90 of 112 carts became purchases. There is no "CTR" tile,
  because the number usually given that name (purchases per impression)
  isn't one.
- **No search-terms panel.** On this data every search query is a single
  category word ("treats", "food"), so relating `search_query` says
  nothing about the product.
- **"Bought with it" links out.** A link-traversal `_relate` doesn't
  condition per anchor (see the cheatsheet). The category-level answer is
  Bought Together, which the page links to when the product's category is
  one of its anchors.

## Try it live

```bash
./do dev
# → http://localhost:8500/product-insights/
```
