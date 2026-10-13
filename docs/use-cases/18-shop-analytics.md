# Shop analytics — the patterns behind the shop

*What goes with a click and a purchase, who buys what and when, which
categories share a basket, and which search words convert. Every number
is a `_relate` lift with its counts, and a lift is shown only when it
clears a bar that accounts for clustered rows and for many tests at
once.*

## Overview

The shopper-facing views (For You, Smart Search) use these patterns
without showing them. A shop owner wants to see them: do low-rated
products sell less, is anyone offered what they just bought, what does
summer change, which search words end in a sale. This view (ADR 0031)
answers each with `_relate`.

The KPI and the "who/when" choice are in the URL
(`/shop-analytics/?kpi=clicked&who=grain-free`), so a link opens the
same state. Each section has its own endpoint
(`/api/shop-analytics/funnel`, `/who`, `/baskets`, `/search-words`), so
switching the KPI re-asks only its section.

## When is a lift shown?

`src/lift_rows.py` applies three rules to every `_relate` hit.

**1. Rows of one customer are not independent.** A search shows 6–14
products under one query, and a customer who buys often buys from many
sessions. Treating 53 purchases as 53 independent draws makes the
interval too narrow. Each section therefore measures how clustered its
condition is by customer, and divides every count by the design effect
before computing the interval (`src/design_effect.py`):

```
deff ≈ 1 + (m − 1) · ρ_condition · ρ_value        (Kish)
```

- m is the size-weighted mean rows per customer.
- ρ_condition is the intra-customer correlation of the condition (e.g.
  "purchased"), estimated from the data.
- ρ_value is bounded by 1, so the design effect is an upper bound.
  Intervals come out wider than they need to be, never narrower.

ρ_condition needs every customer's rows and their rows meeting the
condition. Two field-form `_relate`s on the customer column give both:

```python
# everyone: where = every month of the window (so every row), relate the customer
{"from": "impressions", "where": {"month": {"$or": [...24 months]}},
 "relate": "customer_id", "limit": 10000}
# the condition
{"from": "impressions", "where": {"purchased": True}, "relate": "customer_id", "limit": 10000}
```

Measured on `shoppers` (2026-10-13):

| section | ρ | rows per customer | design effect |
|:--|:--|:--|:--|
| purchases | 0.021 | 48.5 | 2.0 |
| clicks | 0.006 | 48.5 | 1.3 |
| summer order lines | 0.24 | 20.4 | 5.6 |
| a segment or diet rule | 1 (constant per customer) | 20.4 | 20.4 |
| baskets, per anchor | 0–0.6 | 6.5 | 1.0–6.5 |
| search purchases | 0.036 | 22.8 | 1.8 |

**2. Support counts independent rows.** A lift is tested only if its
`fOnCondition` divided by the design effect is 30 or more.

**3. Many tests at once.** A section tests 15–48 lifts. Each interval is
at the Bonferroni level for the number tested (z = 2.9–3.3), so the
chance that *any* shown row in a section is really a lift of 1 is at most
5 %, if the design effect is right. This doesn't make each lift's size
exact, and a lift that isn't shown may still be real. The page says so
under each section.

The interval is the log relative risk on the effective counts
(`lift_interval` in `src/price_bands.py`). It is rounded outward to two
decimals, and a row whose rounded interval touches 1 is left out. A field
with no row left is listed as "no clear effect": either nothing cleared
the bar, or nothing had enough independent rows.

## The four sections

### 1. What goes with a click and a purchase

```python
{"from": "impressions", "where": {"purchased": True},
 "relate": "product_sku.rating_band", "limit": 50}
```

One call per field:
- the product's rating band and category, both through the
  `product_sku` link;
- the shopper's segment, lifestyle and diet rule;
- `just_bought`, a Boolean: was the product in their last order;
- the surface.

The toggle swaps `purchased` for `clicked`. Among purchases:

```
rating = 1–2 stars   0.79×   923 of 12,135   0.68–0.92
category = dental    1.77×   663 of 12,135   1.47–2.13
```

"In their last order" (0.48×) is planted, but it rests on 40 purchases,
about 20 independent ones, so it has no clear effect among purchases.
Among clicks it shows: 0.46× (109 of 24,950, 0.32–0.66). The 1–2 star
band has no clear effect on clicks: ADR 0030 plants poor quality at the
cart and purchase steps, not the click.

### 2. Who buys what, and when

```python
{"from": "order_lines",
 "where": {"order_id.month": {"$or": ["2025-08", "2025-07", ...]}},
 "relate": "product_sku.category", "limit": 50}
```

The same condition also relates `product_sku.dietary`, because a diet
rule shows in the dietary line, not the category. The selector offers the
four seasons (`season_months` from `src/demand_service.py`), the five
segments and the four diet rules.

```
summer      → health 3.99× (375 of 6,489 lines, 2.52–6.31)
grain-free  → dietary = grain-free 3.08× (1,171 of 2,003 lines, 2.54–3.73)
```

Summer grooming (3.89×, 157 lines) is planted but doesn't show: with a
design effect of 5.6 it rests on 28 independent lines. For a segment or
a diet rule every line of a customer shares the condition, so the design
effect is the full 20 lines per customer and only strong effects show.

### 3. Baskets

The order-level co-occurrence query Basket Rules mines (ADR 0022), one
per anchor category, plus one `_relate` on `customer_id` per anchor for
its design effect:

```python
{"from": "orders", "where": {"line_categories": {"$match": "dog_dryfood"}},
 "relate": "line_categories", "limit": 100}
```

The anchor's own token is skipped, and A + B and B + A count as one test.
Dog dry-food + dental-treats: 2.79× (2,699 of 4,100 orders, 2.44–3.19).
Product pairs (`orders.skus`) are left out: each pair shares only 3–8
orders. The page shows the strongest 8 pairs above 1 and 4 below 1, says
how many more there are, and links to Basket Rules.

### 4. Search words

`search_query` is a whitespace Text column, so a `_relate` on it returns
one hit per word, in `$has` form. The obvious query has the wrong
baseline: `_relate` divides by the word's share of *all* impressions,
and only search impressions carry a query, so every word came out about
2.5×. The view sends the query with and without `purchased` and divides
the counts (`src/search_words.py`):

```
lift = (purchases with the word / search purchases)
     / (impressions with the word / search impressions)
```

Words with identical counts are checked with a `_search`:

```python
{"$and": [{"surface": "search"},
          {"search_query": {"$match": "algae"}}, {"search_query": {"$match": "wafers"}}]}
```

If the searches holding all the words are as many as those holding each,
the words become one phrase ("algae wafers"), in the order of one such
search. That turned 99 words into 86 words and phrases.

Of those 86:
- 30 have enough independent purchases to test;
- 5 clear the bar, all above the 11.7 % average ("cheese" 26.1 %, 2.24×);
- none below the average does: "whitefish" (0.62×) is the closest.

A word never bought from search has no hit among purchases. These words
are listed with their impressions and the purchases the average would
expect, e.g. "nail clipper": 67 impressions, about 7.8 expected. Zero
purchases can't carry a lift interval of this kind.

## Latency

A section takes 1.5–3 s alone. The customer-column `_relate`s return
2,500–3,000 hits each and are the slowest part. With all four sections
asked at once, a section takes 4–9 s. That is over the ~3 s bar, so the
endpoints cache each section for 30 minutes (`cache.get_or_compute`), as
Product Insights does.

## Data schema

| Section | Table | Columns |
|---|---|---|
| Clicks and purchases | `impressions` | `clicked`, `purchased`, `month`, `customer_id`, `product_sku` → `products.rating_band`, `category`; `customer_segment`, `customer_lifestyle`, `customer_diet_rule`, `just_bought`, `surface` |
| Who and when | `order_lines` | `order_id` → `orders.month`, `customer_id`; `customer_segment`, `customer_diet_rule`; `product_sku` → `products.category`, `dietary` |
| Baskets | `orders` | `line_categories` (Text), `month`, `customer_id` |
| Search words | `impressions` | `surface`, `purchased`, `customer_id`, `search_query` (Text) |

## Tradeoffs and gotchas

- **The design effect is an upper bound.** Bounding ρ_value by 1 is safe,
  but for a customer-level condition (segment, diet rule) it is harsh:
  small-animal owners' 3.4× on treats doesn't show.
- **`product_category` is not related.** It is the denormalised copy of
  `product_sku.category`, and both return identical hits.
- **Needs ADR 0030's data.** The rating band, diet rule, `just_bought`
  and multi-word search queries exist only in the test env `shoppers`
  until master is reloaded.

## Try it live

```bash
AITO_ENV=shoppers ./do dev
# → http://localhost:8500/shop-analytics/
```
