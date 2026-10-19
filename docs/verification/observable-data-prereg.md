# Pre-registration: only what a shop can observe (ADR 0033)

Written 2026-10-19, **before** the generator changes for ADR 0033. It
builds on ADR 0032's data and checks (`product-states-prereg.md`), which
are re-run unchanged: the planted effects P1–P5 against their nulls, and
the absolute P2a and P6. Every threshold below is fixed now; any change
is an amendment here first, with its reason.

## What changes in the data

- **Removed from every table Aito sees:** `lifestyle`, `health_focus`,
  `treat_affinity`, `brand_loyalty`, `segment`, and every `customer_*`
  copy of them on `order_lines`, `impressions`, `winback_campaigns` and
  `customer_months`. They stay in the generator and still drive behaviour.
- **`customers`** holds what was declared or recorded: `region`,
  `tenure_months`, `pets` (the household's pet types, whitespace Text),
  `dog_size` (when a dog is among them), `diet` (the household's rule),
  and the history aggregates it has today (`total_orders`,
  `total_spent_eur`, `last_order_month`, `churned`).
- **`contexts`**, one per impression session: `customer` (link),
  `month`, `weekday`, `surface`, `basket`, `basket_categories`,
  `prev_basket`, `owned`, `search_query`.
- **`impressions`**: `context` (link), `product_sku` (link, the
  recommend target while `product_state` candidates overconfide,
  td-20261018112625647694), `product_state` (link), `position`,
  `just_bought`, `clicked`, `added_to_cart`, `purchased`.

## The planted effect

| # | Effect | Planted as |
|:--|:--|:--|
| K1 | The kit's next item | The household's kit is read from the session's basket **and** what it owns from earlier orders. An impression of a kit item it already owns converts at odds ×0.1; the kit's next missing item (the starter kit's partner, then `ADD_ONS` in order) ×5; another add-on not yet owned ×1.5. It replaces ADR 0030's S6 rule for kit add-ons (×3 when the starter kit is in the basket); S6's dental-with-dry-food rule stays. |

## 1. Data checks

| # | check | pass when |
|:--|:--|:--|
| O1 | no column named after a hidden trait, nor `segment`, in `src/schema.py` or in any fixture row | none |
| O2 | every impression's context exists and belongs to the impression's customer and month | 100 % |
| K1a | (null: K1 off, S6's kit rule kept) purchase rate of the kit's next item ÷ that of other not-yet-owned add-ons, on impressions where the household has a kit | planted ÷ null ≥ 2.0 on seeds 42, 7, 99 |
| K1b | (same null) purchase rate of an owned kit item ÷ the same item unowned | planted ÷ null ≤ 0.3 on every seed |
| D/S/P | ADR 0030's and 0032's checks | as registered; a range that moves is amended here first |

## 2. Aito checks (on a test env, after #1673 is on shared)

| # | check | pass when |
|:--|:--|:--|
| R1 | hit@10 on held-out impressions: `_recommend` with the customer as evidence (`context.customer`) and the context | reported against today's ranking (segment and traits handed over); the Shop uses it if the paired 95 % CI's lower bound is above −0.05 |
| R2 | the same with the customer as the population (nested `from`, fallback to all) | reported; the better of R1 and R2 is used |
| R3 | `$why` under R1 | the context's lifts nest under the product's own lift, as the Shop's reasons need |
| R4 | `_relate` over `context.customer.dog_size` (two links) | answers with counts that match a `_search` count |
| R5 | the grid for a guinea-pig owner | cage in the basket, nothing owned: water bottle in the top 3; owns cage and bottle, empty basket: hideout in the top 3 and no cage in the top 12 |
| R6 | a premium, health-focused cat owner (traits known to the generator only) | their grid's food is mostly premium and wellness: share ≥ 1.5× the catalogue's |

## Results

(none yet)
