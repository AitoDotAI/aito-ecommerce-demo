# Shop — be a shopper, and watch Aito re-rank

*Pick a shopper and a month, fill a cart, and the Shop follows. It shows
one view per intent: "Buy again" (the routine), "Next for their kit"
(growing a pet's kit) and "Picked for you" (everything else, ranked for
their pets, the month and the cart), each card saying why. Search ranks
the same way, and a product opens to show its alternatives and what
goes with it.*

## Overview

The other views each show one Aito query. The Shop puts them in front of
a shopper, the way a store would use them. Its six shoppers are real
customers in the data, and each card's story is checked against their
history (`tests/test_shop_personas.py`): Päivi got a guinea pig in
February (a cage and a bottle so far), Janne's household only buys
grain-free food, Helena buys the same cat food every few weeks.

Aito sees only what a shop observes (ADR 0033): a customer id, what the
household declared (pets, a dog's size, a diet), and the visit (month,
cart). Nothing the data generator uses to *produce* behaviour (a
shopper's lifestyle or tastes) is in any table.

Shopper, month, cart and the open product are all in the URL, so a link
opens the same shop. The month is "now": every panel uses only the
shopper's orders before it (`src/shop_history.py`), so picking an earlier
month shows the shop as it was then.

## How it works

### One view per intent (ADR 0033, amendment of 2026-10-21)

A visit is usually mostly one thing: a routine restock, or growing a
kit. One `_recommend` carrying everything at once (identity, month,
cart, owned kit) did worse than each piece alone: Aito multiplies lifts,
and the cart's SKUs next to the owned kit erased the kit's lift. So each
intent gets its own well-conditioned query.

### Buy again — one probability per product, from their own orders

`src/shop_suggestions.py`. `_predict` with `predict: "skus.$feature"`
from a nested `from` holding only this shopper's orders before the month:

```json
{ "from": { "from": "orders", "where": { "order_id": { "$or": ["ORD-04450"] } } },
  "predict": "skus.$feature", "limit": 14 }
```

`$feature` makes it one probability per SKU rather than one per whole
past basket. Kit items (a cage) are left out: they're bought once.
"Fill my usual basket" adds those at 15 % or more.

### Next for their kit — what households that owned the same bought next

`_predict product_sku` on `order_lines` whose order already owned what
this shopper owns, for that pet's accessories and toys. For Päivi in
April 2026 (owns a cage and a water bottle):

```json
{ "from": "order_lines",
  "where": { "order_id.owned_before": { "$and": [{ "$match": "small_animal_cage" },
                                                 { "$match": "small_animal_water_bottle" }] },
             "product_sku.pet_type": "small_animal",
             "product_sku.category": { "$or": ["accessories", "toys"] } },
  "predict": "product_sku", "limit": 12 }
```

What they already own is dropped from the answer, and so is anything
under 5 %. For Päivi the hideout comes first (the kit's next step);
`tests/test_aito_check.py` checks it live.

### Picked for you — `_recommend` with declared pets, the month and the cart

`src/shop_grid.py`, `src/shop_context.py`, `src/shop_ranking.py`. For
Päivi in April 2026 with a cage in the cart:

```json
{ "from": "impressions",
  "where": { "context.customer.pets": { "$and": [{ "$match": "small_animal" }] },
             "context.month": "2026-04",
             "context.basket_categories": { "$and": [{ "$match": "small_animal_accessories" },
                                                     { "$match": "small_animal_cage" }] },
             "just_bought": false,
             "product_sku": { "$not": { "$or": ["SKU-PT-0555"] } },
             "product_sku.pet_type": { "$or": ["small_animal"] } },
  "recommend": "product_sku", "goal": { "purchased": true },
  "select": ["sku", "name", "brand", "pet_type", "category", "price_eur", "avg_rating", "$p", "$why"],
  "limit": 20 }
```

- **Declared pets, not identity.** `context.customer.pets` reaches the
  customer's declared pets through two links (`impressions → contexts →
  customers`). The customer id itself is left out: added on top, it
  didn't rank better on held-out sessions and made `$p` worse calibrated
  (`docs/verification/observable-data-prereg.md`, R1/R2 decision).
- **The cart as words.** The cart goes in as the `basket_categories`
  tokens the contexts table records for a basket: one per pet and
  category, one per kit item. An exact cart SKU next to other context
  could veto a candidate on near-zero evidence
  (td-20261020210945109481); the cart's SKUs only keep its own items out
  of the candidates.
- **Their pets as a filter.** `product_sku.pet_type` limits the
  candidates to the household's declared pets. Aito saw dog treats shown
  to cat households too rarely to learn that they never buy them; a
  store would filter anyway. Search and a product's alternatives don't
  filter this way (a cat owner may look for a dog gift).

**A household's rule is a filter, not a prediction.** For Janne (declared
diet `grain-free`) the `where` also holds

```json
"$or": [ { "product_sku.category": { "$not": { "$or": ["dry-food", "wet-food"] } } },
         { "product_sku.pet_type": { "$not": { "$or": ["dog", "cat"] } } },
         { "product_sku.name": { "$match": "Grain" } } ]
```

Grain-free households bought grain-free food only 14 times in the data,
too few for `_recommend` to learn the rule (ADR 0030, check A1). A store
would filter anyway; Aito ranks within it.

**What was just bought falls.** Anything from the shopper's last order is
re-asked in one `_batch`, as `_predict purchased` with
`"product_sku": SKU, "just_bought": true` added to the same context.
Aito learned that a shopper rarely re-buys what they just bought (ADR
0030, check A8); the card shows the drop.

### Why each product — the lifts in its `$why`

`src/shop_reasons.py`. Each card shows up to three reasons, read from the
grid's own `_recommend` hit: under the product's own lift in `$why`, Aito
nests how much each part of the context lifts *this* product.

```json
{ "type": "hitPropositionLift", "proposition": { "product_sku": { "$has": "SKU-PT-0553" } },
  "factors": [ { "type": "relatedPropositionLift", "proposition": { "context.month": "2026-04" }, "value": 1.32 },
               "…" ] }
```

(The nesting was probed on 2026-10-17, before ADR 0033 renamed the
fields to `context.*`; the value is from that probe.)

They read as chips: "Fits your pets" (`context.customer.pets`), "Sells in
April" (`context.month`), "Goes with your cart"
(`context.basket_categories`). A lift under ×1.15 isn't shown, and nor
is a `$group` (Aito's joint estimate of several conditions, which can
rest on no rows, td-20261020210945585150). They explain the probability
on the same card.

Beside them, in grey, are **facts**: an offer this month
(`product_states`, at least 10 % off), the star rating, "keeps their
rule". They aren't reasons, because the grid recommends `product_sku`,
which has no month in it: an offer can't be one of its features.

### Search — the grid's ranking over the products the words name

`src/shop_search.py`. A query keeps the shopper's pets, month, cart and
rule (not the pets filter):

1. `_search products` by `$similarity` on the name: which products the
   words name, each with its text lift (`$score > 1`).
2. `_recommend` as the grid, restricted to them (`product_sku: {"$or": …}`),
   selecting `$p` only.
3. Ranked by `$p` × text lift (Smart Search's blend); the top 12 are asked
   once more for their reasons, facts and the just-bought re-ask.

Smart Search's one-query blend (`_search impressions get product_sku`)
isn't used here: its `where` conditions `$p` but doesn't filter on
`product_sku.*`, so a grain-free household would see grain food.

### The product drawer — details, alternatives, same basket, your orders

`src/shop_product.py`.

- **Details:** brand, price, this month's offer, stars, diet and tags.
- **Instead, this shopper might buy:** the grid's ranking over the same
  category for the same pet, with reasons. A kit item's category
  ("accessories") holds cages and bottles alike, so a kit item's name
  must also hold its type: a bottle's alternatives are bottles.

- **Often in the same basket:** `_relate` on `orders` where
  `skus: {"$match": SKU}`, related to `skus`. Product pairs are thin (a
  few orders each), so a pair is shown only with at least 5 orders
  together and a 95 % interval above 1, with its counts.
- **In this shopper's orders:** a `_search` of their own orders that held
  it. This is their history, not a prediction: `_relate` over one
  shopper's orders (a nested `from`) answers 501 on Aito 2.11.4.

## Data schema

| Panel | Table | Columns |
|---|---|---|
| Picked for you, search, alternatives | `impressions` → `contexts` → `customers` | `context.customer.pets`, `context.month`, `context.basket_categories`, `just_bought`, `purchased`, `product_sku` |
| Search words | `products` | `name` |
| Offers | `product_states` | `month`, `product_sku`, `on_offer`, `discount_pct` |
| Pets and rule filters | `products` (link) | `pet_type`, `category`, `name` |
| Household rule | `customers` | `diet`, `pets` (declared) |
| Same basket | `orders` | `skus` |
| Your orders | `orders` | `customer_id`, `skus`, `month` |
| Buy again | `orders` | `order_id`, `skus` |
| Next for their kit | `order_lines` → `orders` | `owned_before`, `product_sku` |

## Tradeoffs and gotchas

- **Other pets' products are filtered out of "Picked for you", not
  learned away.** Aito saw them shown to the wrong households too rarely
  to learn they don't sell there (dog treats to cat households: 7
  impressions). Search doesn't filter, so it can still show them.
- **Blending the three views into one list** (Aito predicting each
  intent's weight from history) is a later experiment.
- **Same-basket pairs are often empty** for a product: few products share
  enough orders to say "often".
- **Months matter:** December lifts treats and toys, summer grooming and
  health care (ADR 0030, S4).

## Try it live

```bash
./do dev
# → http://localhost:8500/shop/?shopper=paivi&cart=SKU-PT-0555
# → http://localhost:8500/shop/?shopper=janne&q=food   (only grain-free food)
```
