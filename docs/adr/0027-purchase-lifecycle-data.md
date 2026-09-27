# ADR 0027: Purchase data with a lifecycle — restocking, and a starter kit that grows

**Status:** Accepted (the approach). Measured implementation to follow.
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

## Out of scope

- **Seasonality** (e.g. more treats before Christmas). It would help
  Demand's seasonality panel, but it's a separate signal; a follow-up
  if this lands well.
- **Customer churn behaviour.** The churn engineering stays as is.
- **New products or categories.**
