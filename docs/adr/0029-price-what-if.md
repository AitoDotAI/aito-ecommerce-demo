# ADR 0029: Price what-if — set a price, see units, profit and why

**Status:** Proposed
**Date:** 2026-10-11
**Deciders:** Antti

## Context

The Price view (ADR 0016) draws a demand curve for one SKU: Aito's
`_estimate` of next month's units at seven prices around the list
price. It answers "what happens at these seven prices" but not the two
questions a merchandiser asks next:

- **What if I set it to €X?** One price they choose, with units,
  revenue and profit side by side.
- **Why that many units?** Which facts about the product and its recent
  sales push the estimate up or down, and by how much.

Aito's older grocery demo (demo.aito.ai/pricing) has a page that does
both: a price and cost input, a demand estimate, and a waterfall from
the mean through each factor ("Product −18.7 %", "sale_price −3.0 %",
"History-based adjustment +8.2 %") to the estimate. This ADR brings
that interaction to the ecommerce demo, on the data it has today.

Two things on that page are not copied:
- **Rows that change nothing** ("Category +0.0 %", "Weekend +0.0 %").
  They look like evidence and aren't.
- **Unlabelled rows.** "History-based adjustment" is most likely the
  k-NN neighbour residual of `_estimate`. Here it gets a label that
  says so, or it is not shown.

## Aito usage

One `_estimate` per price the user sets, on `monthly_sales`, with the
same evidence the demand curve already uses
(`src/demand_forecast.py`, `price_where`) and `why` selected:

```json
{
  "from": "monthly_sales",
  "where": {
    "product_sku": "SKU-PT-0133",
    "units_last_month": 23,
    "pet_type": "dog",
    "category": "wet-food",
    "brand": "Hill's Science Plan",
    "season": "spring",
    "price_eur": 4.68
  },
  "estimate": "units_sold",
  "select": ["estimate", "why"]
}
```

Both halves are already in use: the body is the demand curve's, and
`select: ["estimate", "why"]` feeds the Demand and Inventory `?`
popovers through `process_estimate_why` (`src/why_processor.py`).

**To verify live before building** (prime directive 3):
1. `price_eur` appears in the `why` tree as a factor. If it doesn't,
   the waterfall cannot explain a price change, and this ADR stops.
2. Whether the factors can be shown so that they add up to the
   estimate. Today's processor walks only the top-weighted neighbour,
   so its rows describe one comparable month, not the estimate. A
   waterfall must either add up (base × factors = estimate) or say
   plainly that it shows one neighbour.
3. The estimate moves the same way as the demand curve at the same
   price (same body, so it should be identical).

The result of each check goes into this ADR before code.

## Decision

A **what-if panel** under the demand curve on the Price view:

- **Price input.** A slider over the curve's price range, plus a
  number field. The curve's points are clickable and set it too.
- **Outputs.** Units next month, revenue (price × units) and profit
  ((price − cost) × units), using the cost the page already shows.
- **Waterfall.** From the base through each factor to the estimate,
  as percentages. Factors below 0.5 % are folded into one "other
  factors" row, so no row reads +0.0 %.
- **Query pane.** Shows the body actually sent, as every view does.
- **Shareable.** The SKU and price live in the URL (`useUrlState`).

Backend: one endpoint, `GET /api/price/what-if?sku=…&price=…`, in a
new `src/price_what_if.py`. It raises on a missing estimate and
answers 404 for an unknown SKU. It is not precomputed: it is one
`_estimate`, and the input is the user's.

## Acceptance criteria

- A user can set a price and see units, revenue and profit for next
  month.
- When the price equals one of the curve's seven points, the units
  match that point.
- Every waterfall row is labelled with a field and value, or with a
  plain-language name for Aito's terms (e.g. "similar past months").
  No row reads +0.0 %.
- The waterfall either adds up to the estimate, or says it shows one
  comparable month (per verification step 2).
- The copied URL reopens the same SKU and price.
- `./do aito-check` asserts that `price_eur` is a factor in the `why`
  and that the estimate is non-negative.

## Demo impact

Adds an optional step after the Price view in `docs/demo-script.md`:
drag the price and watch the waterfall shift. The current walkthrough
is unchanged.

## Out of scope

- **Placement, promotion, competitor price, day of week.** The data
  has none of them, and its grain is monthly. They come with the ADR
  0027 data amendment, and the what-if gains those levers then.
- **An optimal-price recommendation.** The curve already shows the
  peak; an automatic "best price" would hide the tradeoff.
- **Several SKUs at once.**

## Consequences

**Good:**
- The first view that answers "why this number" as a full chain, not
  a popover.
- No new query pattern; everything is in the cheatsheet.

**Bad:**
- On today's data `price_eur` may carry little weight. The waterfall
  will say so honestly, which is less impressive than the old page.

## Notes

The older demo's page also lets users set demand manually and toggle
fields on and off. Toggling fields is a useful way to show what each
fact contributes; it is left for after verification step 2, since it
needs a stable reading of the `why` tree.
