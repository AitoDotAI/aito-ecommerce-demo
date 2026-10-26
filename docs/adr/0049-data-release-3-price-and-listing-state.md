# ADR 0049: Data release 3 — price that the data can learn, and the listing as product state

**Status:** Proposed (2026-10-26, Antti: "we could now have a setup with data, which contains informative product
states with different prices, so that the price sensitivity will properly be stored to the data … all the data in
sync", "more actionable details to product state … number of images, advertising details", and "demand should
react stronger than CTR as CTR will drive impressions in this kind of system")
**Date:** 2026-10-26
**Deciders:** Antti

## Context

ADR 0045 made showings and sales one process: a purchased impression is an order line, and `monthly_sales` is
their sum. Price acts in one place, the odds of each showing. That is live (data release 2). Two things are
still missing.

**1. The price curve cannot be learned per product.** Probed on master, 2026-10-26, `_estimate units_sold`
(regression) with `price_index` and the product's forecast evidence, at index 0.8 / 0.9 / 1.0 / 1.1:

| product | units |
|---|---|
| SKU-PT-0563 | 2.6 · 1.9 · 1.3 · 0.6 |
| SKU-PT-0100 | 28.1 · 27.4 · 26.8 · 26.1 |
| SKU-PT-0042 | 4.5 · 3.9 · 3.2 · 2.6 |

Every product loses about 0.65 units per 0.1 of index. A regression on `units_sold` is additive, so one slope
serves a 1-unit and a 27-unit product alike: a 10 % cut would raise the first by 50 % and the second by 2.4 %.
The generator plants a *multiplicative* elasticity (ε between −2 and −1), so the data is right and the target is
the wrong shape. This is why the units-by-price curve is still folded in the Product view.

**2. The offer's effect is the same on a click as on a purchase.** P6 (ADR 0038) lifts click, cart and purchase by
the same factor, `1 + k · discount_pct / 10`. In a shop where the ranker shows what gets clicked, that is the
wrong balance: a click is cheap and also feeds the ranker, so what the shop sees is click-through *and* more
showings. Demand is the stronger, slower response: it must react more than the click does.

A third gap is in what the owner can act on. The state holds price, offer, stars, label and stock. A merchant also
controls how a product is *listed*: how many pictures it has, how well it is described, and whether it is
advertised.

## Decision

### A relative demand target

`monthly_sales` gains `units_index`: units ÷ the product's mean monthly units over the months before it (1.0 for
an average month; unset for a product's first month). A regression on `units_index` is multiplicative across
products. The Product view's price what-if asks `_estimate units_index` at `price_index`, and shows units as
`units_index × the product's recent mean`. The existing `price_index`, `discount_band` and `showings` stay.

### More price points, informative ones

A product has a price state each month. Today it takes one of four discount bands (none, 10–15, 15–20, 20+), and
60 products have one list-price rise. The release adds:
- **a price index drawn per product and month**, not only per band: a band is a range (a 12 % and a 14 % offer
  are both "10–15"), so `price_index` takes the actual value;
- **a pricing policy per product** (hold, promote often, dynamic): products differ in how much their price
  moves, so each has a spread of index values to learn from;
- **at least eight distinct index values in at least 70 % of products**, so a per-product curve has dots.

### Click lifts less than purchase

P6 splits: the click's offer factor is `1 + 0.4 · k · discount_pct / 10`, cart and purchase keep
`1 + k · discount_pct / 10`. The list-price elasticity (R6) acts on cart and purchase at ε, and on the click at
ε/3. Placement (ADR 0045, ×1.2–1.6 showings per offer band) is unchanged. The result an owner can check: an
offer's gain in *units* is larger than its gain in *click-through*, and the click rate per showing rises less
than purchases per showing do. Position bias and placement stay as they are.

### The listing as product state

`product_states` gains three columns, each set by the shop (so the owner can change them):

| Column | Values | Planted effect (per showing) |
|---|---|---|
| `image_count` | `0-1`, `2-3`, `4+` | click ×0.85 / 1.0 / 1.15; purchase ×0.9 / 1.0 / 1.15; stronger for a shopper with no orders yet (×1.5 the gap) |
| `description_quality` | `thin`, `ok`, `rich` | purchase given a click ×0.85 / 1.0 / 1.2; no effect on the click |
| `ad_level` | `none`, `search`, `banner` | placement: showings ×1.0 / 1.4 / 1.8; click ×1.1 / 1.2 on the showing it buys; **no** lift on purchase given a click |

Ads buy visibility, not conviction. A product advertised more shows up more and is clicked a bit more, and sells
more only through those extra showings. An owner who raises `ad_level` on a product nobody wants gets clicks and
no sales: Aito should find that from the data.

Each column is a state column in the initial schema (ADR 0030: columns added in place come back typed
`Unknown`), and is copied to `monthly_sales` where `_estimate` needs it (it cannot read linked fields, probed
2026-10-24). The Product editor gains selects for the three, as previews first (as stars and label are today,
ADR 0048), and a sandbox lever (ADR 0043) for them once their effects are verified.

### Aito usage

- `_estimate units_index` on `monthly_sales`, `where {product_sku, price_index, ...}`, `model: regression`
- `_predict purchased` and `_predict clicked` on `impressions`, `where {product_sku, product_state.image_count,
  product_state.ad_level, ...}`, `select ["$p", "$why"]`
- `_relate` on `impressions`, by `product_state.description_quality`, for the "For whom" view
- All new patterns are probed on a throwaway release-3 branch and added to `docs/aito-cheatsheet.md` before any
  view uses them.

## Pre-registered checks (data release 3's prereg, before generation)

| # | Check |
|---|---|
| Q1 | Consistency holds: units = Σ purchased lines, every purchased showing has its line (ADR 0045's O1) |
| Q2 | Elasticity recovered per product: the median implied ε from `_estimate units_index` at `price_index` 0.83 vs 1.00 is in [−2.5, −0.5], on a held-out month, and the spread across products is below that of the additive model (the 0.65-units-per-0.1 rule above) |
| Q3 | Demand reacts more than click: at a 20 %+ offer, units ÷ null ≥ 1.8 and click-through ÷ null ≤ 1.3 |
| Q4 | `image_count`: 4+ against 0–1, purchase odds ratio in [1.2, 1.6] |
| Q5 | `description_quality`: rich against thin, purchase-given-click ratio in [1.2, 1.6]; click ratio in [0.9, 1.1] |
| Q6 | `ad_level`: banner against none, showings ratio ≥ 1.6, click-through ≤ 1.3, purchase given click in [0.9, 1.1] |
| Q7 | The older checks (P, R, F, C, K, D, S, O) re-run, with dated amendments for moved ranges |

The generator is byte-stable per seed (`tests/test_generation_is_byte_stable.py`); each new effect draws from its
own seeded stream, so earlier effects don't shift.

## Acceptance criteria

- A user can open a product's *Units by price* and see a curve whose slope is that product's own, with its
  months as dots, and the page says which data it came from.
- A user can change a product's pictures, description or advertising in the editor and see the clicks and
  purchases tabs move, each by its measured size: ads move showings and clicks but not purchases per click.
- When a product is put on offer, the Purchases tab shows a larger change than the Clicks tab.
- Q1–Q7 pass, or each miss is a dated amendment in the prereg.

## Demo impact

`docs/demo-script.md`: the Product view's price curve unfolds (it is folded today); a step for "advertising buys
visibility, not sales" is added to the owner's story. The partner numbers are re-run on release 3, so nothing in
the script is quoted before then.

## Out of scope

- Real pictures or ad platforms: the three columns are the shop's declared listing, not content.
- Competitor prices.
- Changing the sandbox's re-score rule (ADR 0043); it keeps multiplying Aito's lifts until the new effects are
  verified.
- A data release without Antti's go-ahead: loading it touches shared environments.

## Consequences

**Good:** the price curve is the product's own and testable; the click-versus-demand balance matches how a
ranked shop behaves; the owner gets levers (pictures, copy, ads) with a measured, different effect each.

**Bad:** another generator change, and every order-side check re-runs; `monthly_sales` gains four columns, so
release 3 is a reload, not an in-place change.
