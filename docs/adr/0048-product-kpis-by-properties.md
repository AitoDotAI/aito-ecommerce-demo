# ADR 0048: Product KPIs by properties — clicks and purchases, explained, and editable

**Status:** Accepted (2026-10-26, Antti: "on the right side the view to the KPIs with tab like behavior… one KPI
view could be the CTR, another purchases and third the view it currently has. It should explain the KPI by the
product properties", and which properties can be edited so the KPIs update in real time)
**Date:** 2026-10-26
**Deciders:** Antti

## Context

The Product view (ADR 0041) has the product's properties on the left and, on the right, the offer decision:
purchases at each discount band, margin, break-even. Its estimates stand on the *product's own history* (the
SKU is in the `where`), which is right for a product with a record but says nothing about *which of its
properties* the numbers come from, and gives no way to ask "what if it had a label, or more stars?".

## Decision

The right side gets three tabs: **Clicks**, **Purchases**, and **Offer & margin** (the view that was there).
Clicks and Purchases show the chance that a shopper shown a product with these properties clicks it, or buys it,
and a bar per property: its lift, ordered by size, from Aito's `$why`. The left side's properties are the
inputs: the offer (as before), stars and the shop label can be changed, and the numbers on the right are asked
again, beside the numbers without the change. Nothing is saved: a change is a preview.

The query has the product's **properties, not its SKU**, so a property it never had (an offer it has not run,
a star band it has not reached) still gets an answer. For an existing product the SKU form (ADR 0032) is the
better forecast; this one says what the properties are worth. Both numbers are on the page: the estimate, and
what the product has actually done.

## Aito usage

One `_batch` per request, in `src/product_kpi.py`: `_predict clicked` and `_predict purchased` on `impressions`,

```json
{"from": "impressions",
 "where": {"product_sku.brand": "PetNord", "product_sku.category": "treats", "product_sku.pet_type": "dog",
           "product_state.discount_band": "15-20", "product_state.rating_band": "4", "product_state.label": "none",
           "product_state.age": "established", "product_state.stock": "in_stock", "product_state.rival_launched": false},
 "predict": "clicked", "select": ["$p", "feature", "$why"]}
```

plus counts of showings and clicks/purchases for the properties and for the SKU. `$why` for `true` is the base
rate, the normalisers, and one `relatedPropositionLift` per property or, when Aito judges properties correlated,
one for a `$group` of them. `kpi_estimate` raises when the chain doesn't multiply out to `$p`.

What the data supports (probed 2026-10-26 on master; clicks and purchases per showing): the offer
(0.275 → 0.462 clicks from none to 20 %+), stars (0.258 → 0.365), and the shop label (0.306 → 0.386 popular).
Stock and a rival's launch move little (+7 %, −10 %); they stay in the query as evidence, but they are not
editable.

## Acceptance criteria

- A user can open Clicks and Purchases on the Product view and read, per KPI, the chance and a bar per property.
- When a user changes the offer, the stars or the shop label on the left, the right shows the before and the
  after, and marks the properties changed.
- The page shows the product's own record beside the estimate (shown, clicked, bought).
- A request that changes a property that is not editable is refused, not ignored.

## Demo impact

`docs/demo-script.md`: on the Product view, after the offer decision, click Clicks and Purchases, then raise the
stars or the offer and watch the lifts move.

## Out of scope

- A blend of the product's own record with its properties (the two answers disagree for a product with a strong
  record of its own; the page shows both rather than mixing them).
- Editing the catalogue (ADR 0046) and saving a change; the sandbox levers (ADR 0043) remain the way to write.
- These are associations in the shop's showings, not proven causes.
