# ADR 0065: The Shop ranks a product's state, not only the product

**Status:** Proposed (2026-11-07; Antti: "we should seek to use product state here, I'd even claim as a priority")
**Date:** 2026-11-07
**Deciders:** Antti

## Context

The Shop's "Picked for you" asks `_recommend product_sku` over `impressions`
with the shopper's context in the `where` (`src/shop_ranking.py`). A product's
monthly state (price, offer, stars, a rival's launch, a price change; ADR 0032)
enters only as history: every impression links to the `product_states` row it
was shown with, so Aito learned from showings at many prices, but the ranking
cannot tell that this product costs 20 % less than last month. If the owner
prices dynamically, a ranking built on the product's history cannot follow.

What exists today:

- "Product state" in the Shop settings re-scores the top candidates after the
  query: `$p` × an offer lift × a star lift (`src/shop_rescore.py`, ADR 0043).
  The lifts are Aito's, read shop-wide; the multiplication is this app's.
  It is off by default and it only re-orders the 40 candidates the product
  query already chose.
- B5 (ADR 0032, `docs/verification/product-states-prereg.md`) measured
  `_recommend product_state` against `_recommend product_sku` on 1,400
  held-out sessions: hit@10 +0.011 [−0.005, +0.028], Brier +0.0105
  [+0.0079, +0.0131] (worse). The state ranks like the product; it does not
  yet calibrate as well.
- `basedOn: ["product_sku"]` on a state target, which lets a state borrow its
  product's evidence from other months, raises the top `$p` and on some
  sessions answers 500 ("lifts multiplied past the range of a double",
  td-20261020211932494271, aito-core). It cannot be the default until core
  fixes it.

## Decision

The Shop gets a ranking whose unit is the product's state for the month shown:

    {"from": "impressions",
     "where": {<the shopper's context>, "product_state.month": <month>,
               <pets, household rule, cart as filters on product_state.product_sku.*>},
     "recommend": "product_state", "goal": {"purchased": true},
     "select": ["product_state_id", "product_sku", "$p", "$why"], "limit": 40}

A candidate is this month's state, so its price, offer band and stars are part
of what is asked, not history. Cards are built from the state's product; the
card shows the state it was ranked on (price, offer, stars).

1. **Option, then default.** It ships as a third value of the Shop's "Product
   state" setting (`state=native`), beside `offer` and `change`, and is
   compared with the product ranking in the UI by the same side-by-side the
   other modes use. It becomes the default only when its numbers (below) are at
   least as good as the product ranking's.
2. **No `basedOn` at first.** The first version has none, because of the NaN.
   With `basedOn: ["product_sku"]` working it is the natural second step: the
   state keeps the product's identity as a prior. It is added behind the same
   option when core's fix lands, and measured as its own column.
3. **Thin states.** B5 found 26 of 48 small-animal states with `$p` ≤ 0.001 on
   0 purchases in 1–11 impressions. A state with fewer than a few showings
   falls back to its product's score (a second `_recommend product_sku` the
   Shop already makes), stated on the card. The cutoff is chosen on the
   evaluation set, not by hand.
4. **Speed.** One extra `_recommend` on a state population is already warmed by
   the Shop's precompute. The target is the product ranking's latency plus no
   more than 50 %, measured warm and cold on the test host.

### The state's data model (data release 6)

- **Versions.** A state row carries `begin_version` and `end_version` (numbers; the open end is a large sentinel, because
  a null cannot be compared with `$lt`). Whenever a product's state is updated, the version increases: the old row's end
  is closed and a new row opens. `product_state_id` is the SKU plus the version. "Latest" is the open row; an evaluation
  passes the version its context saw, as a literal: `product_state.begin_version: {"$lte": V}, product_state.end_version:
  {"$gt": V}`. (`$gte` and `$lt` through the link work on 2.12.0, checked locally.) Impressions keep linking to the exact
  version they were shown with. This also lets a price change inside a month have a state of its own.
- **Cold start.** A new version has no showings. A state target ranks only rows with impressions, so a price cut would
  make a product vanish from the ranking at the moment it matters. The prior therefore comes from the product.
- **The product's attributes on the state.** A `product_state` target's `basedOn` names only its own table's columns
  (`product_sku.tags` is a 400 on 2.12.0), so the state row also carries its product's tags, category, brand, pet type
  and name. `basedOn: ["product_sku", tags, category, brand, pet_type]`: the product supplies the prior; the state's own
  showings add information once it has been on display for weeks. A multi-hop `basedOn` (`product_sku.tags`) from core
  would remove the copy; it is a request, not a dependency.
- **Probabilities.** `basedOn` inflates the top `$p` (0.83–0.99 against a base rate of 0.14, on a local slice). The order
  may hold while the number cannot be shown as it is; the held-out Brier decides, and the card shows a probability only if
  it calibrates.

## Aito usage

`_recommend` with a `product_state` target and a `where` on the target's link
(`product_state.month`, `product_state.product_sku.pet_type`, …): the form
`scripts/product_state_sweep.py` already uses read-only. No new query shape.
`$why` for a state target is parsed into reasons the way the product's is
(`src/shop_reasons.py`); where its terms differ, the card says "the state's
price band", not the product's.

## Acceptance criteria

- A user can choose "Product state: ranked as this month's state" in the Shop
  and see a grid whose cards show the state (price, offer, stars) they were
  ranked on.
- When a product goes on offer in the month shown, it moves up in this mode and
  the card says why; in the default product ranking it does not.
- On the held-out sweep (1,400 sessions), hit@10 is not worse than the product
  ranking's by more than 0.01, and Brier no worse by more than 0.005, or the
  mode is not made the default (the result is reported either way).
- Warm latency is no more than 1.5 × the product ranking's.
- The held-out sweep is reported split by how long a state has been shown (showings per state): the state ranking is
  expected to match or beat the product ranking on well-shown states and to fall back to its prior on thin ones.
- A booktest holds the query shape and a fake-client test holds the mapping
  from state hits to cards.

## Demo impact

`docs/demo-script.md` §Shop: one beat, "put a product on offer and watch the
Shop follow it", in the sandbox month (ADR 0043).

## Out of scope

- Serving experiment variants (ADR 0064, remaining slice 3).
- Changing the sandbox's levers, or the data.
- Making `basedOn` work: core's.
