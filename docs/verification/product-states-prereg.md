# Pre-registration: product states (ADR 0032)

Written 2026-10-17, **before** the generator was changed for ADR 0032. It
builds on ADR 0027's and ADR 0030's data (`lifecycle-data-prereg.md`,
`shoppers-data-prereg.md`), whose checks D1–D8 and S1–S8 still apply.
Every threshold below is fixed now. The new fixtures are loaded into a
non-master env (`states`) on the shared instance first; master is not
touched until these pass.

The generator is **not** re-tuned against the Aito checks after seeing
them. If it has to change, this file is amended first, with the reason.

## The planted effects

| # | Effect | How it is planted |
|:--|:--|:--|
| P1 | Offers convert, most for budget shoppers | An impression of a product on offer that month (≥ 10 % below list) converts (click, cart, purchase) at odds ×2.5 for budget, ×1.8 mid, ×1.2 premium shoppers. |
| P2 | Launches | 50 products (seeded, from food, treats, dental, toys and accessories) get a launch month uniform in 2024-11 … 2026-01. Before it they have no orders, lines, impressions, monthly sales or states. For their first 3 months on sale: picked at ×2.0 in orders, and an impression converts at odds ×1.6 for a flexible shopper, ×1.0 for a loyal one. |
| P3 | Price rises | 60 products not launched mid-window get one list-price rise of 8–15 % in a month uniform in 2024-11 … 2026-01. Orders follow it through the existing elasticity: pick weight × (price ÷ original list)^ε. |
| P4 | Stars sell | An impression converts at odds by the product's stars as of its month (reviews created before the month): 5 ×1.3, 4 ×1.15, 3 ×1.0, 1–2 ×0.8, unrated ×0.9. On top of "poorly made" ×0.35. |
| P5 | Dog size → pack size | A household whose dog is large picks dog food of 7 kg or more at ×2.5; small, 2 kg or less at ×2.5. Pack size is read from the product name. |

`product_states` replaces `price_history` (same id and price columns) and
adds `on_offer`, `discount_band`, `rating_band` (as of the month), `age`,
`rival_launched` and `price_change` (ADR 0032). `impressions`,
`order_lines` and `monthly_sales` gain a `product_state` link. All in the
initial schema. The unused `BRAND_AFFINITY_BY_SEGMENT` and
`DIETARY_AFFINITY_BY_SEGMENT` are deleted.

## 1. Data-level checks (offline, `tests/test_product_states_data.py`)

| # | check | pass when |
|:--|:--|:--|
| P1a | impression purchase rate on offer ÷ not on offer, budget shoppers | ≥ 1.7 |
| P1b | the same ratio, premium shoppers | ≤ 1.35, and budget's ratio ÷ premium's ≥ 1.4 |
| P2a | rows of a launched product dated before its launch, in every table | 0 |
| P2b | a launched product's share of its (pet, category)'s lines in its first 3 months ÷ its share by product count | ≥ 1.5 |
| P2c | incumbents' units in the 3 months after a rival's launch ÷ the 3 before, divided by the same ratio for (pet, category) slices with no launch then | ≤ 0.95 |
| P2d | impression purchase rate of new products, flexible ÷ loyal shoppers | ≥ 1.3 |
| P3a | raised products' units, 3 months after ÷ 3 before, divided by the same months' ratio for unraised products of their categories | ≤ 0.92 |
| P4a | impression purchase rate, 5 stars ÷ 3 stars as of the month, among products not poorly made | ≥ 1.15 |
| P5a | share of dog-food lines at 7 kg or more, large-dog ÷ small-dog households | ≥ 2.0 |
| P6 | every impression, order line and monthly-sales row links to the state of its product and month, and that state exists | 100 % |
| D/S | the existing D1–D8 and S1–S8 checks | still pass; any range that moves is changed in the diff with its reason |

## 2. Aito checks (on the test env, then `tests/test_aito_check.py`)

| # | check | pass when |
|:--|:--|:--|
| B1 | `_relate` on `impressions`, `purchased: true` → `product_state.on_offer` | `true`'s 95 % interval above 1 |
| B2 | the same among budget shoppers, and among premium | budget's lift above premium's, intervals not overlapping |
| B3 | `_estimate units` on `monthly_sales` for a raised product, the month after its rise | `$why` holds a factor for the state's price (or `price_change`) below 1 |
| B4 | the Shop's `_recommend product_state` for a budget shopper, top 12 | at least one card's reasons name the offer |
| B5 | hit@10 on held-out impressions, `_recommend product_state` vs `product_sku` (paired, 95 % CI) | reported either way; the Shop switches only if the CI's lower bound is above −0.02 |

## 3. Query patterns to probe before use (ADR 0032, Q1–Q6)

Each is run on the test env, its response inspected and recorded below,
and written into `docs/aito-cheatsheet.md` before a view uses it. A
two-link form (Q2, Q3, Q6) that fails or answers wrongly is written up
with a minimal reproduction for Aito core.

1. `_recommend product_state` with `where` `product_state.month`.
2. `where` on `product_state.product_sku.category` as a candidate filter.
3. `$why` of a state candidate: its own features and its product's.
4. `_estimate units` on `monthly_sales` with `product_state.*` in its `$why`.
5. `_relate purchased` → `product_state.discount_band`.
6. `_relate` → `product_state.product_sku.category`.

## Amendments after the first generation (2026-10-17, data checks only, before any Aito run)

The first generation passed P1a, P1b, P2a, P2c and P6, and failed five.
Each failure was diagnosed before anything changed:

| check | result | cause | change |
|:--|:--|:--|:--|
| P2b | 1.03 | Two causes. (1) The baseline, a fair share by product count, is wrong for food: households keep the food they settled on before a launch, so even an *established* launched food sits at 0.64–0.81 of "fair". In treats and toys, a new product's share was 1.6× fair against 0.7–1.1 once established. (2) The ×2.0 pull reached the basket draw but not the choice of a staple. | **Check:** a launched product's share of its slice in its first 3 months ÷ its own share in months 4–9, pooled over launches; ≥ 1.5. **Generator:** the pull also weights the choice of a staple (a new customer's, or a switcher's). |
| P2d | 1.17 | Confounded: loyal shoppers' purchase rate differs from flexible shoppers' on every product (favourite brands ×6), so the raw ratio isn't the planted effect. | **Check:** for launched products, (flexible ÷ loyal purchase rate while new) ÷ (the same ratio once established); ≥ 1.3. |
| P3a | 0.96 | A bug in the check: the comparison group (unraised products of the category) included launched products, whose units go from 0 to some. | **Check:** the comparison group leaves out launched products. Threshold unchanged. |
| P4a | 1.03 | Confounded across products: those with few early reviews have extreme bands (5 or 1–2) and are the less-bought ones. | **Check:** within product: for each product with impressions in months it showed 5 stars and months it showed 3, its purchase rate at 5 ÷ at 3, pooled (impressions-weighted); ≥ 1.15. If fewer than 15 products qualify, ≥ 4 stars vs ≤ 3 instead, ≥ 1.1. |
| P5a | 1.79 | The pack fit entered the customer score, which reaches the staple choice and 65 % of basket re-picks only. | **Generator:** the pack fit also weights the basket draw's first pick (the seasonal lines hold no food). Strength unchanged. |

## Amendment after the second generation (2026-10-17, decided by Antti, before any null run)

The second generation still failed P2b (1.22), P3a and P4a, and D1 fell
to 49.9 % (floor 50 %). Generating the same seed with one effect switched
off showed why fixed thresholds can't judge them: with the stars effect
off, P4a's within-product ratio read 1.16, and with it on 1.05 (changing
one impression's odds re-draws every later impression, so a check on 52
products swings by ±0.1); with the price rise off, raised products'
pooled sales ratio read 1.11, and with it on 0.83 (the randomly chosen
products drift up by themselves).

**The rule from here.** Each planted effect is judged against a **null
generation**: the same seed with that effect switched off, so that time
trends, selection and every confound show up in both. For seeds 42, 7
and 99, a check passes only if `metric(planted) ÷ metric(null)` clears
its margin on **every** seed. `scripts/planted_effects.py` runs it
(`./do planted-effects`) and writes `docs/verification/product-states-data.md`.

| # | null generation | metric | pass when planted ÷ null |
|:--|:--|:--|:--|
| P1a | `OFFER_ODDS` all 1 | budget: purchase rate on offer ÷ not | ≥ 1.5 |
| P1b | the same | premium: the same ratio; and budget's planted÷null over premium's | premium ≤ 1.3; budget ÷ premium ≥ 1.4 |
| P2b | `LAUNCH_PICK_FACTOR` 1, `NEW_ODDS` all 1 | launched products' slice share, first 3 months ÷ months 4–9, pooled | ≥ 1.3 |
| P2c | the same | incumbents' units 3 months after a launch ÷ 3 before, pooled | ≤ 0.95 |
| P2d | the same | on launched products, (flexible ÷ loyal purchase rate) new ÷ established | ≥ 1.25 |
| P3a | `RISE_RANGE` (1, 1) | raised products' units 6 months after ÷ 6 before, over the same for products neither raised nor launched | ≤ 0.92 |
| P4a | `STARS_ODDS` all 1 | purchase rate at 5 stars ÷ at 3, products not poorly made (across products: the null carries the confound) | ≥ 1.15 |
| P5a | `PACK_FIT` 1 | share of dog-food lines ≥ 7 kg, large-dog ÷ small-dog households | ≥ 1.8 |

P2a and P6 stay absolute (nothing before a launch; every row links to
its state) and stay in `tests/test_product_states_data.py`.

**D1** (food re-buy share, floor 50 %) read 49.9 %: launches give
switchers and new customers new products to settle on. Its floor becomes
48 %, with that reason. No other D or S range moved.

## Results

(none yet)
