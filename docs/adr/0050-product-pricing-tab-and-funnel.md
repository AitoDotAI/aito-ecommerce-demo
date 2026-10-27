# ADR 0050: Product pricing tab with an editable list price, and the funnel

**Status:** Proposed (2026-10-27; weekly table and the ranker's loop chosen the same day. Antti: "add a pricing view in the product page as a tab and make the list price
editable", and "estimate impressions … have a funnel page, which shows the impressions -> clicks -> purchases ->
profit funnel, that react whenever you change any of the dynamic properties")
**Date:** 2026-10-27
**Deciders:** Antti
**Builds on:** ADR 0048 (KPIs by properties), ADR 0049 (data release 3: the price and the listing as state)

## Context

The Product view lets an owner change a product's offer, stars and label and see the chance of a click and of a
purchase move (ADR 0048). Two things the owner asks next cannot be answered honestly from release 2.

**A list price the data can learn.** A product's list price is one value, with a rise in 60 products. Across
products it follows the category, so as evidence it says "dog food" and not "dearer". The price that *varies*
inside a product, `price_index` (price ÷ the product's list price), lives in `monthly_sales`, not in
`product_states`, which is what an impression links to. So a click or a purchase estimate cannot be asked
at a price, and the units regression is additive (ADR 0049, finding 1). Editing the list price today would
change a number on screen and nothing the data knows.

**Impressions are not a number anywhere on the page.** `impressions` holds the showings that happened; a
month's count sits in `monthly_sales.showings`. The funnel starts with how often the product will be shown,
which the owner moves with price, offer and advertising (placement, ADR 0045) and which the ranker moves with
click-through. Nothing estimates it.

## Decision

### Data (added to release 3, ADR 0049)

- `product_states.price_index`: the month's price ÷ the product's reference list price, 3 decimals. Impressions
  link it, so `_predict clicked` and `_predict purchased` can take `product_state.price_index` as evidence. If the
  probe shows Aito wants bins for a linked decimal, it becomes `price_index_band` (below 0.85, 0.85–0.95,
  0.95–1.05, above 1.05), as the discount is a band today.
- **`product_weeks`**, a new table: one row per product-week (`SKU-PT-0182-2026-W14`, the week belonging to the
  month of its Monday) with `showings`, `clicks`, `purchases`, `revenue_eur`, the `product_state` in force (the
  month's), and two relative columns: `showings_index` (showings ÷ the product's mean weekly showings before
  that week, the multiplicative target, as `units_index` is for units) and `ctr_prev_week_index` (last week's
  click-through ÷ the product's mean before it; unset in a product's first weeks). `impressions` gain `week`.
  About 65 000 rows. A day would be too thin: the median product-month has 4 showings and 8 % have none, and a
  zero breaks a multiplicative regression (ADR 0049, finding 1). `monthly_sales` still gains `units_index`.
- The generator plants the price in one place, as today: the odds of each showing (ADR 0045); showings,
  clicks, purchases and units are all counted from them, so the funnel is one process, not three models.

### The Pricing tab

A tab beside *What if / History / For whom* on the Product view:

- **List price field**, prefilled with the product's list price, editable. It sets the *price index* the
  estimates are asked at (`new price ÷ reference list price`); an offer band applies on top, as it does today.
- **Curve**: units and profit by list price, from `_estimate units_index` at eight prices, scaled by the product's
  recent mean units, with the product's own months as dots. The profit-maximising price among those is marked.
- **Outside what the product has tried** (price index beyond its months' range, ±5 %) the page says "no data
  here" and greys the estimate. It does not extrapolate quietly.
- The editor's list price sets the same preview as the offer does (nothing is saved); in a sandbox (ADR 0043) it
  writes next month's `product_states` row.

### The funnel

The Product view's right side gains a **Funnel** tab (beside Clicks, Purchases, Offer & margin), so it uses the
editor on the left and reacts to every property in it: offer, list price, stars, label, and release 3's images,
description and advertising.

| Step | Estimate | Aito |
|---|---|---|
| Impressions | recent mean weekly showings × `showings_index` at the state and last week's click-through, weeks 1–4 | `_estimate showings_index` on `product_weeks` |
| Clicks | impressions × P(click \| shown) | `_predict clicked` on `impressions` |
| Purchases | impressions × P(purchase \| shown) | `_predict purchased` on `impressions` |
| Profit | purchases × (price − unit cost) − the month's ad spend | arithmetic |

Each step shows its change against the state as it is now, the last three months' actual funnel beside the
estimate, and the `$why` of the click and the purchase (as ADR 0048 does). Purchases come from the showing, not
from clicks × a conversion, so the three steps cannot disagree with the data's own counting.

**Cross-check, shown on the page:** units from the funnel (impressions × P(purchase \| shown)) against units from
`_estimate units_index` × recent mean. Two routes to one number; a gap larger than 25 % is shown as a warning,
not hidden.

**Ad spend** is a declared cost per `ad_level`, constants in the code and named as assumptions on the page: none
€0, search €60, banner €180 per month. Without it, advertising would always win the profit line.

### Impressions and click-through: the ranker's loop

Showings move with the state through *placement* (ADR 0045: ×1.2–1.6 by offer band, ×1.0/1.4/1.8 by ad level).
The ranker also shows more of what gets clicked, so last week's click-through lifts this week's showings. The
generator plants that: `showings = base × placement(state) × ctr_prev_week_index^γ`, γ = 0.5, with the index
clamped to [0.5, 2] so a lucky week cannot run away. Showings are drawn first and clicks from them, so the loop
does not make clicks and showings the same number.

The question "if CTR rose 50 %, how much more is shown?" is then a query, not an assumption:
`_estimate showings_index` where `ctr_prev_week_index` = 1.5 against 1.0. The funnel runs it forward: week 1 is
the state's own effect, and weeks 2–4 add the loop, so a price cut or a picture shows its total effect on
showings after four weeks, not only its first. The pre-registered γ is a plant; the page shows what Aito
estimates, and Q12 says how close that must be.

## Aito usage

- `_estimate showings_index` on `product_weeks` and `_estimate units_index` on `monthly_sales`, `model: regression`
- `_predict clicked`, `_predict purchased` on `impressions`, with `product_state.price_index` and the listing
  columns, `select ["$p", "$why"]`
- No new query shapes beyond ADR 0049's; each is probed on a throwaway release-3 branch and added to
  `docs/aito-cheatsheet.md` before a view uses it.

## Pre-registered checks (added to release 3's prereg)

| # | Check |
|---|---|
| Q8 | `price_index` in `product_states` equals the `price_index` of the same product-month in `monthly_sales`, for every row |
| Q9 | Funnel consistency on held-out months: the funnel's units and `_estimate units_index` × mean agree within 25 % for the median product |
| Q10 | A 10 % list-price cut raises purchases more than clicks, and showings by the placement factor only, for the median product |
| Q11 | The profit-maximising price is inside the product's tried range for at least 90 % of products with 8+ index values |
| Q12 | Loop recovered: the log-log slope of `_estimate showings_index` on `ctr_prev_week_index` between 0.8 and 1.25 is in [0.2, 0.8] on held-out weeks (γ = 0.5 planted; the index is built from a few clicks a week, so it is noisy and the slope is expected to read low) |
| Q13 | `product_weeks` sums to `monthly_sales` (showings, purchases, revenue) for every product-month, and to `impressions` (ADR 0045's O1 extended to the week) |
| Q14 | Without the loop, no slope: on a copy of the data generated with γ = 0, the Q12 slope is in [−0.1, 0.1], so the estimate is not the offer's placement counted twice |

## Acceptance criteria

- A user can type a new list price for a product and see its units, profit and the profit-maximising price move,
  with the product's own months as dots and the data it came from named.
- A user typing a price outside what the product has tried sees "no data here", not a number.
- A user can see, for a click-through gain, how many more showings follow after one and after four weeks, and that this is estimated from the data.
- A user can change the offer, list price, stars, label, pictures, description or advertising and see all four
  funnel steps move; advertising moves impressions and clicks but not the purchase chance per showing.
- The funnel's units and the units curve agree within 25 %, or the page says they do not.
- Ad spend and its assumed levels are visible next to the profit line.

## Demo impact

`docs/demo-script.md`: a pricing step on the Product view ("what is the best price, and where does the data stop")
and a funnel step ("pictures and ads, and what each does to profit"). Written after release 3, with its numbers.

## Out of scope

- A loop from clicks to anything but showings (reviews, stars, price).
- A daily table.
- A shop-wide funnel (all products summed); the per-product funnel is the first step.
- Saving a list price outside the sandbox, competitors' prices, a price optimiser across products.
- Building any of this before release 3 is loaded: the tab and funnel need its columns.

## Consequences

**Good:** the owner's two decisions, price and listing, are answered from one process, with the funnel as the
single readout, and the limits of the data are on the page.

**Bad:** it waits for release 3, now larger: a new table, a loop in the generator and `week` on every impression, a reload of `product_states`, `monthly_sales` and `impressions`, and every order-side check re-run. The ad costs are our
assumption until the shop declares its own.
