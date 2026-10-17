# ADR 0032: Product states — recommend a product as it is this month

**Status:** Proposed (2026-10-17)
**Date:** 2026-10-17
**Deciders:** Antti

## Context

The Shop recommends `product_sku`: a product with no time in it. What
makes a shown product sell this month — its price, an offer, its stars,
being new — can only enter a query as context for the whole query, never
as a feature of each candidate. So `$why` can't say "on offer ×1.4", and
the Shop shows offers and stars as facts beside Aito's reasons (ADR 0031,
amendment of 2026-10-17).

Antti proposed (2026-10-17) recommending a **product state** instead: the
product as it is in a month, linked to the product. The same rows would
serve Pricing and product analytics: *how did a price change, an offer or
a rival's launch drive this product's sales?*

A survey of the generator (2026-10-17) found that the data can't answer
that yet:

- An impression's purchase ignores price, offers, season and stars (only
  a hidden "poorly made" flag lowers it). Promotions lift *orders* only.
- No product is ever launched or changes its list price: all 658 exist,
  unchanged, in all 24 months.
- Customer properties steer orders strongly (lifestyle → brand tier ×2.6,
  health focus → wellness diets ×2.4, treat affinity → treats ×2.7), but
  nothing makes a dog's size matter to a pack size, and two affinity
  tables (`BRAND_AFFINITY_BY_SEGMENT`, `DIETARY_AFFINITY_BY_SEGMENT`) are
  defined and never used.

## Decision

### The table: `product_states`, one row per product and month it is on sale

It supersedes `price_history` (same id, `SKU-PT-0182-2026-04`, and the
same price columns), adding the state a shopper sees:

| Column | Type | Meaning |
|---|---|---|
| `product_sku` | link → `products` | the product |
| `month` | String | `2026-04` |
| `price_eur`, `list_price_eur`, `discount_pct` | Decimal | as `price_history` |
| `on_offer` | Boolean | at least 10 % below list |
| `discount_band` | String | `none`, `10-15`, `15-20`, `20+` (bands can't be related on v2) |
| `rating_band` | String | from the reviews written **before** the month |
| `age` | String | `new` (first 3 months on sale), `established` |
| `rival_launched` | Boolean | a product of the same pet and category launched in the last 3 months |
| `price_change` | String | `rise` (list price raised in the last 3 months), `none` |

`impressions`, `order_lines` and `monthly_sales` each gain a
`product_state` link to the row of their product and month. Every new
column is in the initial schema (ADR 0030: columns added in place come
back typed `Unknown`).

### Planted effects, each with a check (`docs/verification/product-states-prereg.md`)

| # | Effect | Planted as |
|---|---|---|
| P1 | Offers convert, most for budget shoppers | an impression of a product on offer converts at ×2.5 the odds for budget, ×1.8 mid, ×1.2 premium |
| P2 | Launches | 50 products are launched in a month between 2024-11 and 2026-01; nothing of theirs exists before. New, a flexible shopper converts on it at ×1.6 the odds, a loyal one at ×1.0; and it is picked at ×2.0 in orders, taking share from its category |
| P3 | Price rises | 60 products get one list-price rise of 8–15 % in a month; their orders follow the existing elasticity (ε in −2…−1) |
| P4 | Stars sell | an impression converts at the odds of its stars as of the month: 5 ×1.3, 4 ×1.15, 3 ×1, 1–2 ×0.8, unrated ×0.9 (on top of "poorly made") |
| P5 | Dog size → pack size | a large-dog household picks food of 7 kg or more at ×2.5, a small-dog household 2 kg or less at ×2.5 |

The unused affinity tables are deleted. Each new effect draws from its own
seeded RNG, as ADR 0030's do, but launches change which products exist,
so the older checks (D1–D8, S1–S8) are re-run and any range that moves is
changed in the diff with its reason.

### Views

- **Shop** recommends `product_state` with `product_state.month` as the
  candidate filter: each card is this month's product, and an offer, new
  stars or "new" can be Aito's reason.
- **Product story** (Product Insights): one product's 24 months with its
  state each month (offer, price rise, a rival's launch, its stars), and
  per month *what drove its sales*: the `_estimate` of its units on
  `monthly_sales`, with `$why` as a waterfall (as the price what-if, ADR
  0029). Beside it, who buys it on offer and who doesn't (`_relate` over
  its purchased impressions, `on_offer` true and false).
- **Pricing** gains a conversion-level what-if: `_predict purchased` for
  a shown product with `product_state.discount_band` set, per band.
- **Shop analytics** relates purchases to `product_state.*` (offer, age,
  stars, a rival's launch) beside the product and shopper fields.

## Aito usage, and what to probe first

New query shapes, each probed on a test env and its response inspected
before a view uses it (CLAUDE.md). **Two-link inference** is the risk:
`impressions → product_states → products`. Where it fails, the failure
is written up with a minimal reproduction for Aito core, as with
td-20261009071333317983, and the view waits or uses a one-link form.

| # | Shape | Question |
|---|---|---|
| Q1 | `_recommend product_state`, `where` `product_state.month` | Do candidates narrow to the month? How does ranking compare with `product_sku` on held-out impressions (hit@10, paired)? Each state has about 1/24 of a product's rows. |
| Q2 | `where` on `product_state.product_sku.category` (two links) | Does it filter candidates (the rule, alternatives)? |
| Q3 | `$why` of a state candidate | Do the state's own features (`on_offer`) and the product's (`product_sku.brand`, two links) appear as lifts? |
| Q4 | `_estimate units` on `monthly_sales` with `product_state.*` | Do the state's features enter the estimate and its `$why`? |
| Q5 | `_relate purchased` → `product_state.discount_band` on `impressions` | The one-link form (known to work for `product_sku.*`). |
| Q6 | `_relate` → `product_state.product_sku.category` (two links) | Does field-form relate through two links work? |

## Acceptance criteria

- On the test env, P1–P5 pass their pre-registered data checks, and Q1–Q6
  are answered with their responses recorded.
- A user can open the Shop for a budget shopper and see "On offer ×N" as
  one of Aito's reasons on a discounted card.
- A user can open a product launched mid-window and see its sales start
  at launch, and on an incumbent of its category, the months after the
  rival's launch marked and its estimate's `rival_launched` factor.
- A user can open a product with a price rise and see the month marked
  and the estimate's price factor after it.
- Shop analytics lists `product_state.on_offer` with an interval above 1
  among purchases.

## Demo impact

The Shop beat gains "On offer ×N" as a reason for a budget shopper. A new
optional beat, *a product's story*: "sales rose with each offer, fell
after the price rise, and the rival's launch took a fifth".

## Out of scope

- Stock-outs and their effect on sales (inventory stays one snapshot).
- Weekly or daily states.
- Changing a product's name, brand or category over time.

## Consequences

**Good:** offers, stars and novelty become reasons Aito learns and shows,
and the same rows answer the owner's "what drove this product's sales".

**Bad:** a full reload of every table; launches change which products
exist, so every older data check is re-run; and two-link inference may
fail or rank worse, which this ADR exposes but cannot fix.

## Plan

1. This ADR and `docs/verification/product-states-prereg.md`, thresholds
   fixed before the generator changes.
2. Generator and schema on a branch; offline data checks P1–P5 and the
   older D/S checks.
3. A test env `states` loaded with the new data (a shared write: Antti
   runs it, at night), then Q1–Q6 and the Aito checks.
4. Findings for Aito core written up; then the views, one PR each.
5. Promote to master only after the views pass on the test env.
