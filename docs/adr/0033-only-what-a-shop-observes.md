# ADR 0033: Only what a shop can observe — impressions, contexts and customers

**Status:** Accepted (2026-10-19)
**Date:** 2026-10-19
**Deciders:** Antti

## Context

The Shop's grid sends Aito this (ADR 0031):

```json
{ "from": "impressions",
  "where": { "customer_segment": "cat_owner", "customer_lifestyle": "premium",
             "customer_health_focus": "high", "customer_treat_affinity": "low",
             "customer_brand_loyalty": "loyal", "month": "2026-04", "just_bought": false },
  "recommend": "product_sku", "goal": { "purchased": true } }
```

Antti pointed out (2026-10-19) that no shop knows a customer's "health
focus" or "treat affinity". These are the generator's **hidden traits**:
the variables that *produce* behaviour in the synthetic data. ADR 0006 and
ADR 0017 copied them onto `order_lines` and `impressions` to get around a
one-hop link limit, and later views put them in `where`. Aito then ranks
by being told the answer, and a developer evaluating Aito can't reproduce
that with their own data.

What a shop does have: a customer id, what the customer told it (pets, a
dog's size, a diet), where they live, how long they've been a customer,
and their history. And per visit: the basket, the last order, the date,
the surface, a search query.

Two Aito reference apps already store data that way (survey, 2026-10-19):

- **The grocery demo** (`aito-demo`): `impressions {context → contexts,
  product → products, purchase}`; `contexts {user → users, day, week,
  month, weekday, basket, prevBasket, query, type}`; `users {id, tags}`
  with observable tags only (club-member, female, young). The hidden
  preferences lived only in its generator. It personalises with the user
  as the population: `from: {from: impressions, where: {"context.user":
  id}}`, falling back to all impressions for a new visitor. It never uses
  the basket as evidence.
- **The Shopify app** (`aito-shopify`): the same impressions → contexts →
  users shape; its users are synthetic too, and its plan for a real store
  expects only a hashed customer id plus source, device and page.

## Decision

### The tables

| Table | Holds | Links |
|---|---|---|
| `customers` | What the customer declared or the shop records: `region`, `joined_month`, declared `pets` (e.g. "dog cat"), `dog_size`, declared `diet` (a household's rule, when they told us) | — |
| `contexts` | One row per moment products were shown: `month`, `weekday`, `surface`, `basket` (SKUs), `basket_categories`, `prev_basket` (the last order's SKUs), `owned` (the household's kit items so far, from its orders, e.g. `small_animal_cage small_animal_water_bottle`), `search_query` | `customer → customers` |
| `impressions` | The outcome: `clicked`, `added_to_cart`, `purchased`, `position`, `just_bought` | `context → contexts`, `product_sku → products` (the recommend target while state candidates overconfide, td-20261018112625647694), `product_state → product_states` (ADR 0032) |
| `orders`, `order_lines` | As now, minus the copied traits | `customer → customers`, `product_state → product_states` |

`just_bought` stays on the impression: it is a fact about this product in
this context (the product was in the last order).

The hidden traits (`lifestyle`, `health_focus`, `treat_affinity`,
`brand_loyalty`) and `segment` stay **in the generator only**. They still
drive behaviour, so Aito has something to discover, but no table holds
them. `segment` becomes the declared `pets`.

### Personalisation

Aito learns a customer from their own rows. Two forms, both probed before
a view uses either (CLAUDE.md):

1. **Customer as evidence**: `where {"context.customer": id, ...}` (two
   links from `impressions`).
2. **Customer as population**: `from: {from: impressions, where:
   {"context.customer": id}}`, falling back to all impressions when the
   customer has none (the grocery demo's form).

The context (basket, previous basket, what the household owns, month,
surface) goes in `where` as evidence in both, as Aito core's grocery tests
do (`"context.basket": {"$has": id}`, or the whole basket as an array,
with `$highlight` naming the basket items that lifted a hit). The grocery
demo itself only *excludes* the basket and never queries `prevBasket`;
this demo uses both.

### The kit, in the grid (planted effect K1)

Antti's favourite story is the new hamster owner, and its one gap is that
the grid itself doesn't lead with the kit's next item: only the separate
"What's next" panel (from orders) does. The cause is in the data: an
impression of an add-on converts ×3 when the starter kit is in the
*current* basket, every add-on alike and in no order; the kit's own
partner (the water bottle with the cage) gets nothing; and what the
household already owns plays no part. So Aito has no evidence that "owns
a cage and a bottle → the hideout is next".

Planted instead, from the generator's kit order (`STARTER_KITS`, then
`ADD_ONS` in sequence), with the kit read from the basket **and** what
the household owns:

| Shown product | Odds (click, cart, purchase) |
|---|---|
| A kit item the household already owns | ×0.1 (nobody needs a second cage) |
| The kit's **next** missing item: the starter kit's partner, then the add-ons in order | ×5 |
| Another add-on not yet owned | ×1.5 |

Judged against its null generation as ADR 0032's effects are: the next
item's purchase rate over other add-ons' ≥ 2.0, and owned kit items'
over unowned ≤ 0.3, on every seed.

### Analytics

Views that relate behaviour to customer traits move to what a shop has:
declared fields (`customers.pets`, `dog_size`, `diet`, `region`), tenure,
and features **derived visibly from history**, such as a spend band or
"bought premium brands before". Each derived feature is computed in one
place, as of the context's month, and named as derived.

| View | Uses today | Uses instead |
|---|---|---|
| Shop grid, search, alternatives (`shop_context`, `shop_reasons`) | segment, four traits, diet_rule | customer link, declared fields, context |
| Shop analytics (`shop_analytics_service`) | segment, lifestyle, diet_rule | declared fields, derived spend band, product state |
| Product Insights "who buys it" | segment, pet_size, four traits | declared fields, region, tenure, derived bands |
| Win-back (`winback_service`) | lifestyle, health_focus, segment | derived history features, declared fields |
| Churn drivers (`churn_drivers`) | traits | tenure, region, derived history |
| Smart Search, For You (`search_service`, `recommend_service`, `arms`) | segment, pet_size | customer link, declared pets |
| Evaluation (`eval_service`) | segment | declared pets |

## Aito usage, and what to probe first

| # | Shape | Question |
|---|---|---|
| R1 | `_recommend` with `where {"context.customer": id}` | Does a customer's ~40 impressions personalise, or overconfide as sparse candidates did (td-20261018112625647694)? Hit@10 on held-out impressions against the segment-as-context ranking we use now. |
| R2 | The same with the customer as a nested `from` and the fallback | Same measure; which to use. |
| R3 | `$why` under R1 | Do the context's and the customer's lifts nest under the product's own lift, as the Shop's reasons need? |
| R4 | `_relate` over `context.customer.dog_size` (two links) | Works as `product_state.product_sku.*` did on 2026-10-18? |
| R5 | The Shop's grid for a new guinea-pig owner | With a cage in the basket and nothing owned: the water bottle in the top 3. Owning cage and bottle, empty basket: the hideout in the top 3, and no cage in the top 12. |

R1–R3 need Aito with #1673 (`_recommend` counts the goal as its own
evidence on v2 tables, td-20261018115755850452).

## Acceptance criteria

- No table Aito sees holds lifestyle, health focus, treat affinity or
  brand loyalty; a test checks the schema for them.
- The Shop's query holds only a customer id and context; for a premium,
  health-focused cat owner, the grid still leans to premium wellness cat
  food, learned from their history (checked against the generator's
  traits, which Aito never sees).
- Every analytics view says which fields are declared and which derived.
- A user can be Päivi (owns a cage and a bottle) and see the hideout
  among the first three products in the grid, with "you own a cage" or
  the basket among its reasons; adding the hideout brings the wheel up.

## Demo impact

The Aito panel shows a query a developer could send with their own data.
The demo's story gains a beat: "Aito never sees that Saara is premium and
brand-loyal; it learned it from what she bought."

## Out of scope

- Anonymous visitors without a customer id (the context alone; later).
- Channel and device, which the data has no effect for.

## Consequences

**Good:** the demo stops claiming knowledge a shop doesn't have, and
matches Aito's other reference apps.

**Bad:** most views change; a full reload, folded into ADR 0032's
(not yet promoted); personalisation may be weaker than with the traits
handed over, and the probes decide whether it is good enough.

## Plan

1. This ADR, for Antti's review.
2. Generator: write `contexts`, the new `customers` columns, and drop the
   traits from every table; data checks as ADR 0032's (the planted
   effects judged against nulls).
3. Probes R1–R4 on a test env once #1673 is on shared.
4. Views, one PR each, in the table's order.

## Amendment (2026-10-21): one view per intent in the Shop

**Context.** The grid asked one `_recommend` to carry everything at once:
the customer's identity, the month, the cart, the owned kit and what it
lacks. Each piece works alone; together they degrade:
- the cart's SKU next to the owned kit erases the kit's lift;
- identity plus rich context calibrates worse than either alone, on 150
  held-out sessions (`observable-data-prereg.md`, R1/R2 sweep);
- Antti saw the same in the grocery demo, where the basket went unused.

His reading: shopping intent is a mixture (this visit is mostly a routine
restock, or mostly growing the kit), while Aito multiplies lifts. The core
side is filed as a theme with the CPO.

**Decision (Antti, option 2 of three).** The Shop shows one view per intent,
each one well-conditioned query:

| View | Intent | Query |
|---|---|---|
| Buy again | routine | `_predict "skus.$feature"` over the shopper's own orders (the "usual basket", ADR 0031) |
| Next for their kit | kit | `_predict product_sku` on order lines whose order owned what they own (ADR 0031) |
| Picked for you | everything else | `_recommend` on impressions with `context.customer.pets` (declared), `context.month` and the cart as words; the diet rule as a filter; the just-bought re-ask |

The grid drops the identity and the kit conditions: the kit has its own
view, and identity worsened calibration. Search and a product's
alternatives use the same simplified query. Blending the views into one
list, with Aito predicting the intent weights from history, is a later
experiment.

