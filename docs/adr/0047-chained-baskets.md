# ADR 0047: Chained baskets — each order points to the one before it

**Status:** Accepted, data side built (2026-10-25); the Shop's use waits for the migration and PR #99. (Proposed 2026-10-25, Antti: "shopping baskets could be chained so that each basket has
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
- [ ] The Shop's last-order option conditions on `context.last_order.basket_categories` and reads the
      words from the stored order, not recomputed in the app. (The first draft asked for the same result as
      the derived-words version, which put the words on `context.basket_categories`. That is the wrong test:
      see "Probed" below.)
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

## Built and probed (2026-10-25)

- **Data side:** `src/chained_baskets.py` derives the links at load time; `orders` gets `previous_order`
  and `basket_categories`, `contexts` gets `last_order` and loads after `orders` (`src/schema.py`).
  `tests/test_chained_baskets.py` holds the acceptance criteria that don't need Aito: one chain per
  customer, no fork or cycle, a link target loads before its source, no context links to an order of its
  own month or later. The fixtures already carry `contexts.prev_basket` (the last order's SKUs, 4,934
  contexts): the links agree with it exactly, set for set, on the same 4,934 contexts.
- **In place:** `scripts/add_chained_baskets.py` adds the three columns to an existing env (`PUT /schema` +
  `_backfill` + optimize) and reads every value back. Run on a throwaway branch of `release2`: all 7,834
  `previous_order`, 10,834 `basket_categories` and 4,934 `last_order` values read back equal the
  loader's, and a second run finds nothing to add. `release2` itself is untouched; the migration of a real
  env is Antti's call.
- **Probes** (`scripts/chained_baskets_probe.py`, throwaway branch of `release2`, Aito 2.11.8):
  - A one-hop path conditions `_recommend` (`context.last_order.basket_categories` with `$match` words),
    in 0.4 s; a two-hop path (`context.last_order.previous_order.basket_categories`) in 0.7 s.
  - `$why` reports each path as its own proposition with its own lift (for example `last_order.basket_categories
    cat_litter` ×0.77 overall and ×1.5 for the hit), so the popover can say "your last order".
  - The count of impressions whose last order holds a word (10,463 of 43,938 for `cat_litter`) is a path
    match over linked rows; contexts with no link don't match.
  - **The path is not the cart words.** The same words as `context.basket_categories` give a different
    top 3 (Salmon Dry Food in place of Whimzees on one session): the cart field learned "this session's cart
    holds X", the path learns "customers whose last order held X". The path is the right feature for a
    last order; the app-derived words put the last order in the cart's field. That is why the equivalence
    criterion above was dropped.
- **Not done:** the Shop reading the path (it waits on PR #99's options and an env with the columns), and
  the depth sweep (depth 0 to 3), to follow the last-basket sweep.
