# ADR 0031: An interactive shop, and the owner's view of its patterns

**Status:** Accepted (2026-10-13)
**Date:** 2026-10-13
**Deciders:** Antti

## Context

ADR 0030 gives the data stories: diet rules, a guided pet kit, routine
staples, seasons, ratings that matter, basket complements and recency
(what was just bought). Antti asked (2026-10-13) to make them visible
from both sides of a shop:

- **The shopper**, interactively, like aito-demo's grocery store: a
  cart that changes the recommendations, a product page with "often in
  the same basket" and "in your baskets", autofill for a routine buyer,
  a context to choose, and not being offered what you just bought.
- **The owner**: which features go with clicks and purchases, which
  products go with which buyers and contexts, basket analytics, and the
  search words that convert.

A survey of aito-demo (2026-10-13) found that it loads "previous basket"
data but never queries it, and that its cart only *excludes* cart items
from recommendations rather than conditioning on them. With ADR 0030's
columns this demo can do both.

## Decision

Two new views, each built on queries probed on the test env first.

### Shop (`/shop/`): the shopper side

- **Who and when.** Pick a shopper (the existing personas plus ADR
  0030's story personas, each with one line of narration and their
  rule) and a month (seasons). Both live in the URL.
- **The cart.** Add products from the grid; the cart lives in the URL
  (shareable). Every change re-ranks the grid.
- **"For you, with this cart."** One `_recommend` on `impressions`,
  goal `purchased`, with the shopper's profile, rule, the month, the
  cart (`basket_skus` / `basket_categories`) and their last order
  (`last_order_skus`) as context. A cage in the cart lifts the hideout
  and the water bottle; a bag bought last order drops away.
- **Product page.** A drawer with the product's `$why`, "often in the
  same basket" (`_relate` over `orders.skus`), "in your baskets" (the
  same, from this shopper's own orders), and the buyers it suits.
- **Fill my usual basket.** For a routine buyer, the staples Aito
  predicts they're due for, each with its probability, in one click.
- **What's next for your pet.** For a new owner, the next kit items
  given what they own (`orders.owned_before`).

### Shop analytics (`/shop-analytics/`): the owner side

- **What goes with a click and a purchase.** `_relate` over impressions
  with `clicked` / `purchased`, across product, shopper, basket, season
  and recency fields; each lift with its counts and 95 % interval, and
  the ones whose interval includes 1 left out (as in Price and Demand).
- **Who buys what, and when.** Products against segments, diet rules and
  months.
- **Baskets.** The pairs bought together most above chance, from
  `orders.skus`.
- **Search words.** Which query words convert, and which don't.

## Aito usage

In the cheatsheet: `_recommend` with a goal and context, field
`_relate`, `_predict`, Text `$match`, `_batch`.

New, each probed on the test env and written into the cheatsheet before
its view uses it:

1. **A shopper's own history as the population**: a nested `from`
   (`{"from": {"from": "orders", "where": {"customer_id": …}}}`). The
   grocery demo notes an empty population answers 400; the view must
   say "no history yet" rather than fail.
2. **One prediction per staple**: a non-exclusive `_predict` on
   `orders.skus` (aito-demo's `predict: "skus.$feature"`), from the
   shopper's own orders.
3. **`$match` on a Text column of SKUs** as `_relate` / `_recommend`
   context on the v2 engine.

### Findings from the probes (2026-10-13, test env `shoppers`)

These change the design above; details in
`docs/verification/shoppers-data-prereg.md`.

- **A hard rule is a filter, not a prediction.** Grain-free households
  bought only grain-free food, but 14 purchases is too few for
  `_recommend` to learn the rule (check A1 failed). The Shop filters
  the candidates by the shopper's rule (`product_sku.name` matching its
  words) and lets Aito rank within it, and says so on screen.
- **"In your baskets" is history, not inference.** `_relate` with a
  nested `from` answers 501 on 2.11.4 ("not supported with relate
  yet"), so it is a `_search` of the shopper's own orders, labelled as
  their history.
- **Same-basket pairs are thin per product** (3–8 shared orders), so
  the drawer shows the counts, and the owner's basket section works at
  category level (`orders.line_categories`) as Basket Rules does.
- **Autofill** is `_predict` with `predict: "skus.$feature"` from the
  shopper's own orders (nested `from`): one probability per product.
- **"What's next for your pet"** is `_predict product_sku` on
  `order_lines` with `order_id.owned_before` matching each owned item
  (check A2: the exercise wheel comes top after cage, bottle, hideout).

## Acceptance criteria

- A user can pick "new hamster owner", add a cage to the cart, and see
  the hideout or water bottle rise in the grid, with why.
- A product just bought by the shopper ranks lower than before buying it.
- A grain-free household's grid holds no rule-breaking food, and the page says the rule is applied as a filter.
- "Fill my usual basket" proposes a routine buyer's staples, each with a
  probability, and nothing for a shopper with no history (said plainly).
- The product drawer shows "often in the same basket" and "in your
  baskets", each from a query that was sent and is shown.
- Shop analytics shows at least one planted pattern per section, each
  with counts and an interval, and no lift whose interval includes 1.
- Both views open from a shared link in the same state.

## Demo impact

`docs/demo-script.md` gains a shopper beat ("I just got a hamster": cart
→ grid → next kit item) and an owner beat (the patterns behind it).
Existing beats stay.

## Out of scope

- A real checkout, accounts, or a server-side cart.
- Weekday context: the data has no weekday effect to show.
- Writing the shopper's choices back to Aito (a stretch, later).

## Consequences

**Good:** the demo shows Aito answering a shopper and an owner from the
same data, with the patterns visible on both sides.

**Bad:** two more views to keep honest; three new query patterns to
verify first; both views need ADR 0030's data on master.
