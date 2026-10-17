# Shop — be a shopper, and watch Aito re-rank

*Pick a shopper and a month, fill a cart, and the grid follows: who they
are, the season, what's in the cart and what they bought last time all
change what Aito suggests, and each card says why. Search ranks the same
way. A product opens to show its alternatives and what goes with it; a
routine buyer can fill their usual basket in one click; a new pet owner
sees what's next for the kit.*

## Overview

The other views each show one Aito query. The Shop puts them in front of
a shopper, the way a store would use them. Its six shoppers are real
customers in the data, and each card's story is checked against their
history (`tests/test_shop_personas.py`): Päivi just got a guinea pig (a cage and a bottle so far),
Janne's household only buys grain-free food, Helena buys the same cat
food every few weeks.

Shopper, month, cart and the open product are all in the URL, so a link
opens the same shop. The month is "now": every panel uses only the
shopper's orders before it (`src/shop_history.py`), so picking an earlier
month shows the shop as it was then.

## How it works

### The grid — `_recommend` with the shopper, the month and the cart as context

```json
{ "from": "impressions",
  "where": { "customer_segment": "small_animal_owner", "customer_lifestyle": "mid", "…": "…",
             "month": "2026-04",
             "basket_categories": { "$and": [{ "$match": "small_animal_accessories" },
                                              { "$match": "small_animal_cage" }] },
             "basket_skus": { "$and": [{ "$match": "SKU-PT-0555" }] },
             "product_sku": { "$not": { "$or": ["SKU-PT-0555"] } } },
  "recommend": "product_sku", "goal": { "purchased": true } }
```

`src/shop_grid.py`. The cart goes in as the words the impressions table
records for a basket (`src/shop_context.py`), so a cage in the cart lifts
what shoppers with a cage in their basket bought.

**A household's rule is a filter, not a prediction.** For Janne the
`where` also holds

```json
"$or": [ { "product_sku.category": { "$not": { "$or": ["dry-food", "wet-food"] } } },
         { "product_sku.name": { "$match": "Grain" } } ]
```

Grain-free households bought grain-free food only 14 times in the data,
too few for `_recommend` to learn the rule (ADR 0030, check A1). A store
would filter anyway; Aito ranks within it.

**What was just bought falls.** Anything from the shopper's last order is
re-asked in one `_batch`, as `_predict purchased` with `just_bought: true`
added to the same context. Aito learned that a shopper rarely re-buys what
they just bought (ADR 0030, check A8); the card shows the drop, e.g.
"Bought last order: 8 % → 2 %".

### Why each product — the lifts in its `$why`

`src/shop_reasons.py`. Each card shows up to three reasons, read from the
grid's own `_recommend` hit: under the product's own lift in `$why`, Aito
nests how much each part of the context lifts *this* product.

```json
{ "type": "hitPropositionLift", "proposition": { "product_sku": { "$has": "SKU-PT-0553" } },
  "factors": [ { "type": "relatedPropositionLift", "proposition": { "customer_treat_affinity": "high" }, "value": 1.49 },
               { "type": "relatedPropositionLift", "proposition": { "month": "2026-04" }, "value": 1.32 },
               { "type": "relatedPropositionLift", "proposition": { "$group": ["…basket_categories…"] }, "value": 2.38 } ] }
```

With a cage in a guinea-pig owner's cart, a fruit treat read "Goes with
your cart ×3.0 · Treat affinity: high ×1.5 · Sells in April ×1.3" on the
ADR 0030 data (2026-10-17). They explain the probability on the same card.

Beside them, in grey, are **facts**: an offer this month (`price_history`,
at least 10 % off), the star rating, "keeps their rule". They aren't
shown as reasons because the data can't weigh them yet: `impressions`
records no offer, and the rating's lift in `$why` is small and mixed.

### Search — the grid's ranking over the products the words name

`src/shop_search.py`. A query keeps the shopper, month, cart and rule:

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

### Suggestions — the usual basket, and what's next for the pet

`src/shop_suggestions.py`.

- **Fill my usual basket:** `_predict` with `predict: "skus.$feature"`
  from a nested `from` of the shopper's own orders: one probability per
  product. Kit items (a cage) are left out: they're bought once.
- **What's next for their pet:** `_predict product_sku` on `order_lines`
  whose order already owned what the shopper owns
  (`order_id.owned_before` matching each item). For Päivi, with a cage,
  bottle as of April 2026, the hideout comes first (the kit's next step); a
  shopper who owned a cage, bottle and hideout gets the exercise wheel.

## Data schema

| Panel | Table | Columns |
|---|---|---|
| Grid, search, alternatives | `impressions` | `customer_*`, `month`, `basket_categories`, `basket_skus`, `just_bought`, `purchased` |
| Search words | `products` | `name` |
| Offers | `price_history` | `month`, `discount_pct` |
| Rule filter | `products` (link) | `category`, `name` |
| Same basket | `orders` | `skus` |
| Your orders | `orders` | `customer_id`, `skus`, `month` |
| Usual basket | `orders` | `customer_id`, `skus` |
| What's next | `order_lines` → `orders` | `owned_before`, `product_sku` |

## Tradeoffs and gotchas

- **The model still offers some other pets' items** to a single-pet
  shopper (a dog chew at 34 % for a guinea-pig owner, on the ADR 0030
  data). That is its honest estimate
  from the impressions; the Shop doesn't hide it.
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
