# Product — one product: the offer decision, its levers, its history, its buyers

*Pick a product and a month. The view says whether to put the product on
offer and at what discount, with its estimated effect on sales and
margin. Then it shows the two levers (discount and price), the product's
record month by month, and which households buy it. All of it is live.*

## Overview

A product manager asks about one product: "What will it do, why, and
what if I change its discount or price? For whom?" The view answers
in that order (ADR 0041):

1. **The decision.** For example: "Put it on offer at 10–15 % off".
   Aito estimates a shopper shown it buys it 41.9 % of the time at
   that band, against 26.6 % at list price. The margin per 100
   showings goes from €36.94 to €43.56. To break even the offer must
   sell 1.34× as often, and Aito expects 1.58×. These numbers are
   for the default product, PetNord Grain Free Daily Dental Treats 120g,
   on env `observable`.
2. **What if.** The price curve and the units waterfall at a chosen
   price, beside the discount bands.
3. **History.** Units per month, with offers, the price rise, a rival's
   launch, star changes and reviews marked; the funnel; the surfaces.
4. **For whom.** The declared households that buy it more than others,
   and a link to see the Shop as the shopper who fits them.

The URL holds the product, the month, the tab and the what-if price
(`/product/?sku=SKU-PT-0192&month=2026-04&tab=history`). The Shop's
product drawer links here with the same product and month.

## How it works

### The decision — `_predict purchased` per discount band

```python
# src/discount_what_if.py — predict_body()
{"from": "impressions",
 "where": {"product_sku": "SKU-PT-0192", "product_state.discount_band": "10-15"},
 "predict": "purchased", "select": ["$p", "feature", "$why"]}
```

The impression's `product_state` link makes the band evidence, so a
band the product never had is a what-if. `src/product_decision.py`
prices each band at its typical discount and compares what a showing
earns: `100 × $p × (price − unit cost)`. The band that earns the most
is the advice. This assumes one unit per purchase and as many showings
as now, and the page says so.

The band's lift in `$why` is shop-wide: Aito learned it from every
product's impressions. The page says that next to the number.

### The price — `_estimate units_sold` with the regression model

```python
# src/price_what_if.py — the what-if's body
{"from": "monthly_sales",
 "where": {"product_sku": "SKU-PT-0192", "units_last_month": 21, "pet_type": "dog",
           "category": "dental-treats", "brand": "PetNord", "season": "spring", "price_eur": 2.43},
 "estimate": "units_sold", "model": "regression", "select": ["estimate", "why"]}
```

The decision asks this at today's price and at the advised band's
price, for the month after the data ends. The What-if tab adds the
seven-point curve (`src/price_curve.py`) and a slider. The regression
learns one price effect from all products' months. So the curve's slope
is the same number of units per € for every product, not this product's
own price sensitivity. The page states this next to the curve. It is why
the price model shows the offer's lower price costing profit: the model
doesn't see the offer label, which is what lifts conversion.

### History — one `_batch`

```python
# src/product_history.py — history_queries()
{"from": "impressions", "where": {"product_sku": sku, "purchased": True}, "limit": 0}
{"from": "product_states", "where": {"product_sku": sku}, "limit": 500}
```

Twelve counts (the funnel, each surface's impressions and purchases)
and three row reads (reviews, product states, monthly sales) in one
round-trip. Checks that fail loudly rather than draw a wrong chart:
- the surfaces must cover every impression;
- every table must come back whole (`total` equals the rows returned);
- a sale in a month with no product state is refused.

A month on sale with no `monthly_sales` row sold 0 units.

### For whom — `_relate` over the product's order lines

```python
# src/product_buyers.py — buyers_relate_body()
{"from": "order_lines", "where": {"product_sku": sku}, "relate": "order_id.customer_id.pets"}
```

One call per declared field, fired in parallel: `pets`, `dog_size`,
`diet` and `region`, two links from the order line. Each lift has no
interval, so its counts are on screen. A lift on fewer than 10 lines,
or within 0.15 of 1, is grey. The Shop shopper whose declared profile
matches the clear lifts gets a "See it as …" link.

## Data schema

| Section | Table | Columns |
|---|---|---|
| Decision, discount what-if | `impressions` → `product_states` | `product_sku`, `product_state.discount_band`, `purchased` |
| Price what-if, curve | `monthly_sales`, `inventory` | `units_sold`, `units_last_month`, `price_eur`, profile fields; `unit_cost_eur` |
| History | `impressions`, `reviews`, `product_states`, `monthly_sales` | counts; `created_at`, `rating`, `sentiment`; the state columns; `units_sold` |
| For whom | `order_lines` → `orders` → `customers` | `order_id.customer_id.pets`, `.dog_size`, `.diet`, `.region` |

## Tradeoffs and gotchas

- **Two models, two answers.** The discount estimate says an offer
  sells more often. The price model says a lower price costs profit.
  Both are true of what each model sees. The advice comes from the
  discount estimate's margin per showing; the price model's units and
  profit sit beside it, labelled as the price's cost alone.
- **The months are the data's.** The what-ifs forecast the month after
  the data ends. The month picker chooses which month's state counts
  as "now".
- **No accuracy here.** How well the estimates hold up is in Evidence
  (the page's "How well? →").

## Try it live

```bash
./do dev
# → http://localhost:8500/product/
```
