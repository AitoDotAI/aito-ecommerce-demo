# Pre-registration: data release 3a (ADR 0049, with ADR 0050's `list_price_index`)

Written 2026-10-27, **before** the generator is changed. It builds on `actionable-states-prereg.md` (including the
ADR 0045 addendum); the older checks (P, R, F, C, K, D, S, O) still apply and are re-run (Q7). The new fixtures
go into a new env (`release3a`) on the shared instance only with Antti's go-ahead; nothing is loaded by writing
this. Release 3b (`product_weeks` and the ranker's loop, ADR 0050) has its own prereg.

The generator is **not** re-tuned against these checks after seeing them. If it has to change, this file is
amended first, dated, with the reason. Each effect has a switch in `data/planted_switches.py` and is judged against
a null generation of the same seed (`scripts/planted_effects.py`).

## What is planted

| # | Effect | How |
|:--|:--|:--|
| L1 | List price moves | Each product draws a policy from its own stream: `hold` 50 % (the 60 rises of P3, the mispriced and the demo anchors are always `hold`), `dynamic` 30 %, `promote` 20 %. A `dynamic` product's list price index (list ÷ its original list) each month stays with probability 0.4, otherwise is drawn from {0.85, 0.90, 0.95, 1.00, 1.05, 1.10}. A `promote` product holds its list price and has the offer probability ×2.5 (cap 0.6). |
| L2 | Price acts on the purchase, less on the click | The list price's elasticity ε (R6) acts on cart and purchase at ε and on the click at ε/3 (odds ×(list ÷ original)^ε, and ^(ε/3)). Orders' pick weights follow the same list price as P3 does. |
| L3 | An offer lifts the click less | P6 splits: the click's odds factor is `1 + 0.4 · k · discount_pct / 10`; cart and purchase keep `1 + k · discount_pct / 10`, k by the shopper's discount sensitivity (1.0 / 0.4 / 0.1). Placement (ADR 0045) is unchanged. |
| L4 | Pictures | `image_count` `0-1` / `2-3` / `4+`: click odds ×0.85 / 1.0 / 1.15; purchase-given-click ×0.9 / 1.0 / 1.15. Drawn per product (25 / 50 / 25 %); 25 % of products move up one level in one month of the window. |
| L5 | Description | `description_quality` `thin` / `ok` / `rich` (25 / 55 / 20 %; 20 % move up one level once): purchase-given-click ×0.85 / 1.0 / 1.2, no effect on the click. |
| L6 | Advertising | `ad_level` `none` / `search` / `banner`: 15 % of products run a campaign of 1–3 consecutive months (70 % search, 30 % banner), at most one at a time. Placement (showings) ×1.0 / 1.4 / 1.8, click odds ×1.0 / 1.1 / 1.2, **no** effect on purchase-given-click. |

Deferred (recorded, not planted): ADR 0049's "stronger for a shopper with no orders yet" on pictures. The
generator's shopper has no notion of their orders-so-far at a showing; it comes with 3b if wanted.

`product_states` gains `list_price_index` (list ÷ original list, 3 decimals), `image_count`,
`description_quality`, `ad_level`. `monthly_sales` gains `units_index` (units ÷ the product's mean units in the
months before it; unset in its first month), `list_price_index` and the three listing columns (copied: `_estimate`
cannot read a linked field). `monthly_sales.price_index` stays the effective price ÷ list. All are columns of the
initial schema (ADR 0030).

## Checks

### Data-level (offline: `tests/test_release3_data.py`)

| # | Check | Pass when |
|:--|:--|:--|
| Q1 | Consistency holds: a month's units = its purchased showings, every purchased showing has its order line (ADR 0045's O1), `monthly_sales` ↔ `product_states` one to one | 100 % |
| Q8a | `monthly_sales.price_index` = `list_price_index` × (1 − discount_pct/100) per row, to 0.002 | 100 % |
| Q8b | `list_price_index` takes 2 or more values in at least 40 % of products | ≥ 40 % |
| Q8c | The effective `price_index`, in 0.02 bins, takes at least 8 values in at least 70 % of products with 12 or more months | ≥ 70 % |
| Q9 | The listing columns: shares of `image_count`, `description_quality`, `ad_level` over product-months; a campaign is 1–3 months long | within ±5 points of the drawn shares |
| Q10 | A launched product has no row before its launch in any table, with the new tables and columns (P2a) | 0 |

### Effects (against nulls: `scripts/planted_effects.py`, seeds 42, 7, 99, pooled)

| # | Check | Pass when |
|:--|:--|:--|
| Q3 | At a 20 %+ offer against none, same products, list placement: purchases per showing ÷ click-through | ≥ 1.25 |
| Q3a | The same: click-through ratio | in [1.15, 1.6] |
| Q3b | Units of a month on a 20 %+ offer ÷ the product's units with none (units_index) | ≥ 1.8 |
| Q2 | List price: purchases per showing, `dynamic` products' months with list index ≤ 0.90 ÷ those ≥ 1.05, no offer | in [1.3, 3.0] (ε between −2 and −1 over a ratio of about 1.2) |
| Q2a | The same, click-through | between 1.05 and 1.5, and below the purchase ratio |
| Q4 | `image_count` 4+ ÷ 0–1: click-through ratio; purchases per click ratio | [1.2, 1.5]; [1.15, 1.45] |
| Q5 | `description_quality` rich ÷ thin: purchases per click; click-through | [1.25, 1.6]; [0.9, 1.1] |
| Q6 | `ad_level` banner ÷ none: showings per product-month; click-through; purchases per click | ≥ 1.6; ≤ 1.35; [0.9, 1.1] |

### Aito (once `release3a` is loaded; Antti's go-ahead)

| # | Check | Pass when |
|:--|:--|:--|
| A1 | `_estimate units_index` at `price_index` 0.83 vs 1.00, median product, implied ε on a held-out month | in [−2.5, −0.5], spread across products below the additive model's (ADR 0049's Q2) |
| A2 | `_predict clicked` and `purchased` with `product_state.list_price_index` or its band: probed on a throwaway branch first | answers; `$why` multiplies out |
| A3 | `_relate` on `impressions` by `product_state.ad_level`, `image_count`, `description_quality` | the lifts have the planted directions; ads: no lift on purchase given click |

### Amendments before generation (2026-10-27)

- **ADR 0049's Q3** said click-through at a 20 %+ offer ≤ 1.3. With k averaging 0.5 over shoppers, a click lifted
  by `1 + 0.4 · k · 2.2` is about ×1.4, so ≤ 1.3 could not hold; it is replaced by Q3/Q3a above, which say what
  the ADR meant (demand reacts more than the click does) as a ratio.
- **ADR 0049's Q4/Q5 columns** speak of "purchase odds"; here each effect is a per-step factor (click, then
  purchase given click), and the checks read those two ratios.
