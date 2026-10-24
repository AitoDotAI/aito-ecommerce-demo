# ADR 0045: One source for showings and sales

**Status:** Accepted (2026-10-24, Antti: "Could we fix the data, instead of hiding the view?
… make it consistent, so that the CTR and demand data agrees … basing both on the same
source data & generation")
**Date:** 2026-10-24
**Deciders:** Antti

## Context

The generator draws two things independently:
- **orders,** from baskets, staples and promotions, which `monthly_sales` sums;
- **impressions,** a funnel of showings, clicks and purchases.

So they disagree:
- An offer lifts the chance a showing ends in a purchase (×1.2–2.5 by shopper, ADR
  0032/0038), but the units sold don't follow it the same way.
- The PetNord agent found a purchased showing in a month with 0 units sold
  (SKU-PT-0626, July 2024).
- Product's units-by-price curve is nearly flat (about 0.1 units per €):
  - `_estimate units_sold` sees only price in euros, across all products;
  - the price effects that do exist live in a different process from the one that
    makes the units.
- Supply's markdown estimate couldn't count an offer's lift. The CRO's correction of
  2026-10-24 made that line say "by price alone".
- A discount has a double effect: a higher chance per showing, and a higher place in the
  shop, which brings more showings. Today neither reaches the units.

## Decision

### Every sale is a purchase in a session

- The generator simulates every customer's sessions, consenting or not:
  - what was shown, in which order;
  - clicks, carts, purchases.
- **A purchased showing becomes an order line;** a session's purchases are its order.
  `monthly_sales` is the sum of order lines per product and month.
- **Consent (ADR 0044) decides what is recorded, not what happens.** Non-consenting
  customers' sessions produce orders but no `contexts` or `impressions` rows.
- **Orders outside the shop's lists** (reorders from an order history, a direct link) are
  sessions on the surface `direct`. They're recorded like the others, so every order line
  has a session.
- **Tests:**
  - `monthly_sales.units_sold` equals the sum of that month's purchased order lines, for
    every product and month;
  - every purchased impression has its order line.

### Price acts in one place

Each showing's purchase odds carry every price effect, and nothing else adds units:
- **offer band:** P1/P6, by the shopper's discount sensitivity;
- **list-price change:** the planted elasticity ε (−2 … −1) of ADR 0032's P3, now applied
  to the odds;
- **stars and the rest:** as their ADRs plant them.

### The double effect: placement

- **The shop's own ranker:** shown lists are ordered by a merchandising score that
  includes the product's offer band, so an offered product is placed higher.
- **Position bias:** the chance a showing is clicked falls with its position (×0.9 per
  slot, a planted effect), and a list shows 6–14 slots.
- **Result:** an offer raises a product's purchases twice: more and better-placed
  showings, and a higher chance per showing. Both are recorded in the data a shop has.

### What the units model can see

`monthly_sales` gains:
- `price_index`: price ÷ the product's list price, that month;
- `discount_band`: as `product_states`, copied because `_estimate` can't read linked
  fields (probed 2026-10-24);
- `showings`: the product's recorded impressions that month (consenting shoppers only, so
  it's an observable proxy).

### Pre-registered checks (data release 2's prereg, before the change)

| # | Check |
|---|---|
| O1 | Consistency: units = Σ purchased lines, exactly (test) |
| O2 | The offer lift on units: at a 20 %+ offer, units ÷ the null generation's ≥ 1.8 (the per-showing lift × the placement lift) |
| O3 | Placement: an offered product's showings ÷ the null's ≥ 1.2; click rate by position falls monotonically |
| O4 | Elasticity recovered: `_estimate units_sold` with `price_index` gives a within-product slope whose implied ε lies in [−2.5, −0.5] on a held-out month (live, on the release env) |
| O5 | The older checks (P, R, F, C, K, D, S) re-run, with dated amendments for moved ranges |

## Views (after the release is loaded)

- **Product:** the units-by-price curve unfolds. Units at an offer band and its
  placement come from the same data as the per-showing chance, so the two agree.
- **Supply:** the markdown estimate counts both effects ("clears in N weeks at 15 % off"),
  with no "by price alone" caveat.
- **The Shop's sandbox lever** stays a re-score (ADR 0043); its placement effect now has a
  measured counterpart.

## Consequences

**Good:**
- Clicks, purchases and sales are one story. A partner can check one against the other.
- Price and offers have an effect a merchant can plan with.

**Bad:**
- The largest generator change since ADR 0030. Orders change, so every order-side check
  re-runs.
- The demo's Monday data (release 1) keeps the folded curve until release 2 is live.
