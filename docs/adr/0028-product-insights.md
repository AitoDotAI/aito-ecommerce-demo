# ADR 0028: Product Insights — one product, its funnel and its buyers

**Status:** Accepted
**Date:** 2026-10-03
**Deciders:** Antti

## Context

Every analytics view in the demo is about the whole store or a category.
Purchase Analytics shows monthly totals and the top ten products; Bought
Together, Pattern Explorer and Basket Rules work on category pairs.
Nothing answers the merchandiser's everyday question about **one
product**: how well does it convert, where, and who buys it?

Aito's grocery demo (`aito-demo`) has a Product Analytics page for this,
and Antti asked for the same here. That page also has problems not to
copy:
- its "CTR" tile is purchases per impression;
- its query pane is a fixed example string, not the query sent;
- its numbers are in-sample with no counts behind them.

## Decision

A new view, **Product Insights** (`/product-insights/?sku=…`). It is
shareable by URL, using the same `useUrlState` as the other views. It
has five panels, all live against Aito:

1. **Funnel** — impressions → clicked → added to cart → purchased, as
   counts and step rates. Labelled as rates of the step before, never
   "CTR".
2. **By surface** — impressions and purchases per surface (search, For
   You, category page, Bought Together), with the purchase rate.
3. **Who buys it** — which customer profiles are over- or
   under-represented among this product's purchases, with the counts
   behind each lift.
4. **Monthly units** — `monthly_sales` for this product.
5. **Reviews** — the rating distribution and sentiment counts.

The page links to Bought Together for the product's category
(`/bought-together/?anchor=…`) rather than repeating it.

The product picker lists the local catalog grouped by category, so it
costs no query. The default product is SKU-PT-0177 (Puppy Cheese Treats),
chosen because it has enough data in every panel: 363 impressions, 117
order lines and 18 reviews on master.

## Aito usage

- **Counts** — `_search` with `limit: 0` (funnel, surfaces, reviews),
  sent as one `_batch`: about 20 independent reads that would otherwise
  be sequential round-trips. Both are already in the cheatsheet.
- **Who buys it** — `_relate` on `order_lines`, where the product is
  the condition:

  ```json
  { "from": "order_lines", "where": { "product_sku": "SKU-PT-0177" },
    "relate": "customer_segment" }
  ```

  It runs once per customer column (segment, pet size, lifestyle, health
  focus, treat affinity, brand loyalty), in parallel. Each hit's lift is
  how much more common the profile is among this product's order lines
  than among all order lines. `fs.fOnCondition` is the product's lines
  with that profile, and `fs.fCondition` is all of the product's lines.
  Probed live 2026-10-03: dog owners 1.42× (99 of 117 lines).
  - This is the field-form `_relate` already in the cheatsheet, with a
    one-product condition.
  - Thin rows are shown with their counts. Cat owners come out 0.52× on
    1 of 117 lines, because Aito smooths small counts toward 1.
- **Monthly units** — `_search` on `monthly_sales`.
  - On master the table has rows only for months with sales, so a month
    without a row is 0 units.
  - The chart fills those months with 0 and says so in its caption.
- **Query pane** — shows the `_relate` body actually sent, with the
  product filled in.

## Acceptance criteria

- A user can open `/product-insights/` and see the default product's
  five panels.
- A user can pick another product. The URL changes, and the copied URL
  reopens that product in a fresh browser (covered by
  `./do test-urls`).
- The funnel's counts never increase from one step to the next, and
  each rate is labelled with the step it divides by.
- Every lift in "Who buys it" shows its counts: the product's lines with
  that profile, and all of its lines.
- The query pane shows the body that was sent.
- `./do aito-check` asserts that the funnel is monotone and that the
  relate's `fCondition` equals the product's order-line count.

## Demo impact

This adds a view under Analyze, after Purchase Analytics.
`docs/demo-script.md` gets no new step: the existing walkthrough stays
the canonical path, and Product Insights is for questions about one
product.

## Out of scope

- **Search terms that convert.** On this data every search query is a
  single category word, "treats" or "food", so the panel would say
  nothing about the product. It comes back if the generator produces
  real queries.
- **Product-level "bought with it".** The cheatsheet notes that a
  link-traversal `_relate` doesn't condition per anchor. The
  category-level answer is Bought Together, which the page links to.
- **Lifecycle panels.** How often the product is re-bought, and what
  customers buy after a starter kit, wait for the purchase-lifecycle
  data (ADR 0027).
- **Forecasts.** Demand stays its own view.
