# ADR 0047: Chained baskets — each order points to the one before it

**Status:** Proposed (2026-10-25, Antti: "shopping baskets could be chained so that each basket has
reference to previously one. Then context could point out prev one, so that you can examine even longer
history if you want")
**Date:** 2026-10-25
**Deciders:** Antti

## Context

The Shop's cold start can use a customer's latest basket: it gives the pets, and where the shopper is (the
first items for a terrarium, or a new puppy's second week). The "Start from their last order" option
(PR #99) does it by rebuilding the last order's words in the app, as cart words, and the last-basket
sweep (`docs/verification/last-basket-prereg.md`) measures whether it helps.

That works, but the history lives in the app: the query holds words the app derived, one order deep. Two
limits follow:

- The database can't be asked how far back is worth looking. Depth is whatever the app builds.
- The words are a copy of data the database already holds in its orders, so a change to how a basket is
  tokenised changes the query and the stored data in two places.

Aito conditions on a path through links, to any depth (`context.customer.pets` is one hop). If an order
links to the previous one, and a session links to the last order before it, the history is reachable by
path and the depth becomes a choice in the query.

## Decision

Two links, derived by the loader from the orders it already has. No generator draw changes, so the seeded
fixtures stay byte-identical for every existing column.

1. **`orders.previous_order`**: nullable link to `orders.order_id`: the customer's order before this one.
   A customer's first order has none (the key is absent, as Aito leaves a null out).
2. **`contexts.last_order`**: nullable link to `orders.order_id`: the customer's latest order **before
   the session's month**. A visitor with no earlier order, or an unidentified one, has none.
3. **`orders.basket_categories`**: the order's words, in the vocabulary `contexts.basket_categories` uses
   (`small_animal_cage`, `small_animal_accessories`), so a path condition and a cart condition match the same
   tokens.

**Ordering.** Orders carry a month, not a date. The previous order is the customer's latest order in an
earlier month. Orders in the same month chain by `order_id` (the generator writes them in order), and a
session sees only orders of earlier months: a session never sees an order of its own month, so the link
can't leak the session's own purchase.

## Aito usage, to probe before use

| Query | Question |
|---|---|
| `where {"context.last_order.basket_categories": {"$match": "small_animal_cage"}}` | Does a one-hop path through a nullable link condition `_recommend` as a cart word does? |
| `where {"context.last_order.previous_order.basket_categories": …}` | Does a two-hop path work, and what does it cost? |
| The same with the link absent | A missing link must behave as no condition, and say so (td-20261025133912138605: a link id with no rows is silently no evidence). |
| `$why` of a path condition | Is its lift reported per path, so the popover can say "your last order" and "the order before"? |

## Evidence

A pre-registered sweep, the same protocol as the last-basket sweep: depth 0 (today), depth 1 (last order),
depth 2, depth 3, on the 3,880 eligible sessions, held out by throwaway branches. Predictions: a gain at
depth 1 for kit households; depth 2 and 3 add little, because a kit progresses one item at a time.
Reported with intervals. The depth the data supports becomes the Shop's default, not the deepest one.

## Acceptance criteria

- [ ] Every order has `previous_order` unless it is the customer's first; every context of an identified
      customer with an earlier order has `last_order`, and it names an order of an earlier month.
- [ ] A test asserts no context links to an order of its own month or later.
- [ ] The chain has no cycle and no two orders share a `previous_order` (each customer's orders form one chain).
- [ ] The Shop's last-order option reads the link by path, with no words derived in the app, and its
      result for the same sessions equals the derived-words version's (the equivalence test).
- [ ] The depth sweep reports hit@12 and Brier per depth, with intervals.

## Demo impact

The "Start from their last order" checkbox gains a depth ("last order", "and the one before"). The `?`
popover names the order a lift comes from. `docs/demo-script.md` is unchanged until a depth is chosen.

## Out of scope

- A customer's whole lifetime as one condition. A path reaches a fixed depth; "all earlier orders" is a
  different question.
- Chaining sessions (visits) rather than orders.
- Real order dates.

## Consequences

**Good:**
- The history lives in the database, so any depth is a query change, not an app change.
- The same links serve other questions: the time between orders for churn, the basket before a return.

**Bad:**
- A data release: two links and a column, and a loader change; existing environments need them added in
  place (`PUT /schema` + `_backfill`, never a drop and reload, which would land the table on the v1 engine).
- A path through a nullable link may behave unlike the cart words (the probes above).
