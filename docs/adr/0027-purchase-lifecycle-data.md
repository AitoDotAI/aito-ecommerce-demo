# ADR 0027: Purchase data with a lifecycle — restocking, and a starter kit that grows

**Status:** Accepted (the lifecycle approach). The price and win-back extensions below are proposed, awaiting the maintainer's yes.
**Date:** 2026-09-28
**Deciders:** Antti

## Context

Every personalised feature in this demo learns from the synthetic
purchase history in `data/generate_fixtures.py`. That history has no
memory. Each order line is an independent draw: a pet type by segment
weight, a category by segment bias, then a brand and diet by the
customer's traits. Order months are drawn at random from the customer's
tenure window.

Real pet-store purchases are the opposite of independent. Measured on
the current fixtures (658 products, 12,215 orders, 38,013 lines):

| Pattern a pet owner shows | In the current data |
|:--|:--|
| **Restocking**: the same food, again and again | 6.7 % of food lines re-buy a food the customer bought before |
| **A starter kit, then add-ons**: cage, bottle and food first; wheel, hideout, tunnel later | small-animal first orders and later orders have the same category mix (treats 36/35 %, food 33/34 %, accessories 17/19 %) |
| **Durables bought once** | 18 of 106 small-animal cage buyers bought two or more cages, up to three |
| **Time order** | 25 % of a customer's orders share a month with another of theirs |

A predictive database can only find patterns the data contains. When a
customer's history doesn't predict their next basket, personalised
features can at best beat segment averages. That makes the demo read as
"Aito isn't that useful" when the real cause is the data. It is part of
why "Recommended for you" feels generic, and why Demand's seasonality
panel finds no drivers.

## Decision

Generate each customer's purchases as a life with their pet, not as
independent draws. The engineered signals the demo already relies on
stay (segment preferences, brand loyalty, the dog-food → dental-treats
lift, the personas' distinct baskets); the changes add structure on top.

1. **Orders in time order.** A customer's orders are a sequence of
   months from their first purchase, with gaps drawn from their
   restocking rhythm, instead of random months.
2. **Restocking.** Each customer settles on one or two **staple
   consumables** per pet (a food, and litter for cats). They reorder
   them on a personal cadence (roughly every 4-6 weeks, jittered) with
   high probability each time, and switch occasionally (a brand or
   life-stage change: puppy → adult → senior).
3. **A starter kit, then add-ons.** A new owner's first order is the
   basics for their pet type: for a hamster, a cage, a water bottle and
   food. Later orders add the related items the kit implies: wheel,
   hideout, tunnel, chews. Which add-on comes next depends on what the
   customer already owns.
4. **Durables bought once.** Cages, tanks and similar are not rebought,
   except as a rare replacement.
5. Everything else (treats, toys, occasional extras) keeps today's
   segment- and trait-driven draws, so baskets are not purely
   mechanical.

The product catalogue doesn't change. Which categories count as
consumable, starter or durable is a table in the generator, per pet
type.

## Aito usage

No new query patterns. The existing ones get data worth learning from:

- `_recommend` / `_predict` over `order_lines` and `impressions`
  (For You, Bought Together, Cart Completion) can learn "what this
  customer buys next" from their own history.
- The time-split `_evaluate` from ADR 0014 gets real month-to-month
  rhythm to learn.

The measurement below uses `_predict` of the next order's products from
the previous one, already in the cheatsheet.

## How we know it worked

**A next-basket evaluation**, run on both the old and the new data
before anything merges:

- For each customer's last order, predict its products from their
  earlier orders (`_predict` / `_recommend`, time-split: earlier orders
  train, the last order tests).
- Score hit rate @10 against a **popularity baseline** (the most-bought
  products for the segment).
- **Fail-proof:** the same evaluation with each customer's history
  shuffled across customers must fall to the popularity baseline. If
  it doesn't, the gain isn't coming from the customer's own history.

Acceptance: on the new data, the model beats popularity by a clear
margin, with a paired CI above zero. On the old data it shouldn't.
That's the measurement that says the data now carries the pattern.

## Acceptance criteria

- [ ] Food lines that re-buy a previous food: from 6.7 % to a
      majority, with switching still present.
- [ ] Small-animal first orders are dominated by starter items; later
      orders by consumables and add-ons.
- [ ] No customer buys a second cage except as a rare replacement.
- [ ] Next-basket hit rate @10 beats the popularity baseline on the new
      data (CI above zero), and the shuffled-history control falls to
      it.
- [ ] The existing engineered-signal tests still pass: segment
      preferences, brand loyalty, dental-treats lift, persona baskets.
      Any range that has to move is changed with its reason in the diff.
- [ ] The Demand page's time-split accuracy is re-measured against the
      naive forecast, and reported whichever way it falls.

## Demo impact

A new moment becomes possible and honest: "this customer bought a cage
and a bottle last month. What will they need next?" and "this
customer's food runs out next week". Whether to add it to
`docs/demo-script.md` is decided after the data is measured, not
before.

## Cost

- Every fixture file regenerates. Shared needs a full reload
  (`reset-data`). The tables on master became v2 through an
  irreversible `_migrate` after creation (ADR 0025), and the loader
  PUTs schemas with no engine. A reload must be checked to land on the
  v2 engine, for example by building an env, migrating it and promoting
  it as in ADR 0025, before it goes near master.
- Precompute snapshots, cached predictions and screenshots all refresh.
- Tests that pin today's engineered signals may need their ranges
  revisited.

## Extension (proposed 2026-09-29): prices and win-back

Five views are hidden until the data can support them. Diagnosing them
(read-only, on live data) showed the purchase lifecycle alone is not
enough: two more generators produce data with no cause and effect.

### Prices as exogenous promotions

Today `gen_price_history` sets each month's price **from** that month's
demand (a busy month gets the low price). So a cheap month is a busy
month, not the other way round:

- the within-SKU correlation between price and units is −0.83 on all
  638 SKUs, and the estimated price sensitivity comes out at about −3.7;
- every list price sits inside its realised band (list/mean 0.95–1.04),
  so there's no price outlier to find;
- discounts don't differ by category (every band × category lift
  interval includes 1), so there's no sweet spot to find.

Decision:

1. **Promotions are decided first,** independent of demand. Each month a
   SKU is promoted with a probability that depends on its category
   (treats and toys twice as often as dry food). Promotion depth is
   10–25 %.
2. **Demand responds to price:** units × (price / list)^ε, with ε drawn
   per SKU from [−2, −1]. That's a price sensitivity a category manager
   would believe.
3. **Planted mispricings:** about 15 SKUs have a list price 15–25 %
   above their category's level and are promoted most months. Their
   realised prices sit well below list, with ≥ 12 observations each.

### Win-back with product-level response

Today each product is sent 1–3 times and response doesn't depend on the
product. So product evidence makes predictions **worse** than the base
rate: held-out log-loss 0.417 against a base of 0.401 (and 0.437 against
0.418 on a second seed). "Which product to send" has no support.

Decision: keep today's base response by lifestyle and recency (9–20 %).
Multiply it by **2.5** when the product is in a category the customer
bought at least three times (their staple), and by **0.5** for a category
they never bought. Every product gets enough sends to learn from
(≥ 10 each for the catalogue's top 200).

### Unhide criteria, per view

Each runs as a live `aito-check` in the PR that unhides the view. A view
comes back only when its check passes on the regenerated data.

| view | criterion |
|:--|:--|
| Demand | On the time split, the model beats the naive "same range as last month" forecast (paired CI above zero). |
| Price | ≥ 3 outliers with n ≥ 12; ≥ 1 band × category lift whose 95 % interval excludes 1; no outlier with n < 6. |
| Markdown | No proposal loses margin against holding stock at list; estimated units never fall as price falls; implied sensitivity at −20 % within [−3, −0.5] for ≥ 90 % of scored SKUs. |
| Win-back | `_evaluate predict responded` with the page's evidence beats the base rate in log-loss by ≥ 0.01, on two seeds; no displayed rate above 0.5. |
| Cart Completion | Held-out next item: hit rate at 3 beats popularity-within-pet (paired CI above zero); no suggestion priced above 2× the cart; any probability shown matches the held-out attach rate within ±0.1. |

### Also noted

- Churn's drivers are real but one reads backwards: a recent **negative**
  review lowers churn (lift 0.67). The likely reason is that any recent
  review marks an engaged customer. The regeneration should make review
  sentiment carry its own effect (negative raises churn), measured the
  same way.

## Out of scope

- **Seasonality** (e.g. more treats before Christmas). It would help
  Demand's seasonality panel, but it's a separate signal; a follow-up
  if this lands well.
- **Customer churn behaviour.** The churn engineering stays as is.
- **New products or categories.**
