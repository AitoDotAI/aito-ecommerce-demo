# Shop — be a shopper, and watch Aito re-rank

*Pick a shopper and a month, fill a cart, and the grid follows: who they
are, the season, what's in the cart and what they bought last time all
change what Aito suggests. A product opens to show what goes with it; a
routine buyer can fill their usual basket in one click; a new pet owner
sees what's next for the kit.*

## Overview

The other views each show one Aito query. The Shop puts them in front of
a shopper, the way a store would use them. Its six shoppers are real
customers in the data, and each card's story is checked against their
history (`tests/test_shop_personas.py`): Sofia just got a guinea pig,
Janne's household only buys grain-free food, Helena buys the same cat
food every few weeks.

Shopper, month, cart and the open product are all in the URL, so a link
opens the same shop.

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

### The product drawer — same basket, and your orders

`src/shop_product.py`.

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
  (`order_id.owned_before` matching each item). For Sofia, with a cage,
  bottle and hideout, the exercise wheel comes first.

## Data schema

| Panel | Table | Columns |
|---|---|---|
| Grid | `impressions` | `customer_*`, `month`, `basket_categories`, `basket_skus`, `just_bought`, `purchased` |
| Rule filter | `products` (link) | `category`, `name` |
| Same basket | `orders` | `skus` |
| Your orders | `orders` | `customer_id`, `skus`, `month` |
| Usual basket | `orders` | `customer_id`, `skus` |
| What's next | `order_lines` → `orders` | `owned_before`, `product_sku` |

## Tradeoffs and gotchas

- **The model still offers some other pets' items** to a single-pet
  shopper (a dog chew at 34 % for Sofia). That is its honest estimate
  from the impressions; the Shop doesn't hide it.
- **Same-basket pairs are often empty** for a product: few products share
  enough orders to say "often".
- **Months matter:** December lifts treats and toys, summer grooming and
  health care (ADR 0030, S4).

## Try it live

```bash
./do dev
# → http://localhost:8500/shop/?shopper=sofia
```
