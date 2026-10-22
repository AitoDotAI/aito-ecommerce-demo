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

## Amendment after the first null run (2026-10-17, before the second)

The first null run (`product-states-data.md` as of commit time; 17 of 27
pass) exposed two mechanisms that don't plant what the table above says.
Margins are **not** changed.

| check | planted ÷ null (seeds 42, 7, 99) | cause | change |
|:--|:--|:--|:--|
| P4a | 1.08, 1.12, 1.04 | The funnel's cart and purchase steps sit near their caps, so odds applied there saturate: even ×4.0 for 5 stars gave ×1.41 (probe, seed 42). Offers and novelty also scale the click (≈ 0.24) and show; stars didn't. | Stars scale the click too: shoppers see them before clicking. Strength unchanged. |
| P2c | 1.00, 1.00, 1.00 | Nothing planted it: the new product's ×2.0 pull barely dents its rivals (a slice holds ~20 products, and staples are kept). The state's `rival_launched` had no effect. | An incumbent's pick weight is ×0.75 for 3 months after a rival of its pet and category launches (`RIVAL_PICK_FACTOR`); the null switches it off with the launch pull. |

Left as they are, and reported as they come out: P1b on seed 99 (premium
1.305 against ≤ 1.3), P2b on seeds 7 and 99 (1.08, 1.26 against ≥ 1.3)
and P3a on seed 7 (0.935 against ≤ 0.92).

## Amendment after the second null run (2026-10-17, decided by Antti, before the third)

The second null run passed 22 of 27: P4a now passes on every seed; P2c
read 0.99 on every seed and P3a missed on seeds 7 and 99 (0.98, 0.98).
Cause: both effects reached fresh picks only, while most of a food's
sales are restocks of a staple chosen long before, which ignore rivals
and scale only their quantity with price.

**Change:** a household reconsiders its staple when it has just risen in
price or a rival has just launched in its slice: for `RECENT_MONTHS`
after either, the staple's switch probability is ×3 (`RECONSIDER_FACTOR`).
The nulls switch it off with their effect (price rise, launch pull).
Margins unchanged.

*Addendum, same evening, before any complete run:* the first attempt
crashed in the price-rise null (it no longer marked which products were
due to rise, so P3a had nothing to measure), and its one finished seed
showed P2c at 0.97: a household that switches mostly lands on *another
incumbent*, so incumbents as a group keep their sales. So a household
that reconsiders because a rival launched switches **to** that rival
(when it keeps the household's diet rule and is a staple for the pet);
the price-rise null keeps `price_change` marking the planned rise and
only switches its effect off.

## Post-hoc note after the third null run (2026-10-17, flagged to Antti)

The final seed-42 fixtures read D1 (food re-buy share) at **46.0 %**,
under the 48 % floor amended above. This one is post hoc: it was seen
before the floor moved. Cause: the restock amendment makes households
reconsider their staple after a rise or a rival's launch, which lowers
re-buys by design. D1's floor becomes 45 %. P2d missed on seed 42 (1.17
against ≥ 1.25) with its mechanism unchanged since it passed at 1.94 and
1.42 on that seed; it is reported as a miss, not tuned.

## Results

(none yet)

## B5 as run (design fixed 2026-10-22, before the run)

B5 was not run with ADR 0032's other checks. It runs now on env `observable`
(Aito 2.11.8), with the R1/R2 sweep's method (`observable-data-prereg.md`):

- **Sessions:** 1,400 held-out sessions (`random.Random(0).sample` of the
  sessions since 2025-05 that showed a product someone bought). The R1/R2
  run showed 150 is too few for hit-rate differences of this size.
- **Context, the same for both:** the Shop's "Picked for you" query (K+):
  declared pets, month, cart words, `just_bought: false`, the diet rule and
  the declared-pets filter, the cart excluded. Each session is left out of
  the data (a nested `from`).
- **Variants:** `recommend: "product_sku"` against
  `recommend: "product_state"` with `product_state.month` = the session's
  month (probed 2026-10-22: candidates narrow to the month, one state per
  product). The filters go through `product_state.product_sku.*`.
- **Primary metric:** hit@10, i.e. a product bought in the session is among
  the top 10 (for states, the state's product). The paired difference
  (state − product) has a 95 % CI (normal approximation over sessions).
- **Decision (as pre-registered above):** the Shop switches to
  `product_state` only if the CI's lower bound is above −0.02.
- **Reported, not deciding:** Brier of `$p` over the products the session
  showed. The probe saw higher `$p` on states (top item 0.65 vs 0.44).

Script: `scripts/product_state_sweep.py`.

**Amendment (2026-10-22, after 121 sessions, before any result was read).**
The run stopped at SESS-001970: a state it showed (SKU-PT-0568-2025-11) has
no impressions outside that session, so with the session held out,
`_recommend product_state` cannot return it. The product variant can, from
the product's other months. Hit@10 is unchanged: a bought state that can't
be recommended is a miss, the state variant's real cost. Brier leaves such
"unseen" states out for **both** variants, so they are compared on the same
rows, and the run reports how many were left out. The first 121 sessions
had none (the run would have stopped on them).

### B5 result (2026-10-22, env `observable`, Aito 2.11.8, n = 1,400 held-out sessions)

| metric | product | state | state − product, paired 95 % CI |
|:--|--:|--:|:--|
| hit@10 | 0.1471 | 0.1586 | +0.0114 [−0.0048, +0.0276], a tie |
| Brier (reported) | 0.1942 | 0.2047 | +0.0105 [+0.0079, +0.0131], state worse |

20 unseen states (one in each of 20 sessions) were left out of Brier for both
variants, as amended.

**Under the rule:** the CI's lower bound (−0.005) is above −0.02, so a switch
is *allowed*; the rule names a condition for switching, not a reason to.
Ranking is a tie and the state's `$p` calibrates measurably worse, and the
Shop shows `$p` on every card. **The Shop keeps `recommend: product_sku`**,
with the month's state read as facts on the card. States stay where they
explain (Shop analytics' findings), and a state with no impressions of its
own can't be recommended at all, which a live shop meets every month start.

**Exploratory, after B5 (2026-10-22): the state with `basedOn: ["product_sku"]`.**
Antti's question: can a state borrow its product's evidence from other
months? Probe first (held-out SESS-001970, November 2025): the candidates
are still only states with impressions (48; the unseen chew stays out), and
the top `$p` rises from 0.54 to 0.77 against a base rate of 0.12, the
`basedOn` inflation seen in R1/R2's variant D (td-20261020211932494271). The
same 1,400 sessions are scored as a third column, paired against both. Not
part of B5's decision.

**Exploratory, more `basedOn` fields (Antti, 2026-10-22).** Probed first:

- `basedOn` takes only fields of the target's own table. `product_sku.tags`
  for a `product_state` target answers 400 ("not a field of the predict
  target's linked table").
- Each added state field raises the top `$p`. With `product_sku` and all
  seven state fields, the top states read 0.96–0.97 against a base rate of
  0.12.
- `availability` has no history: `inventory` holds today's stock only, and
  isn't linked from impressions. It is left out (it would leak the present
  into past sessions).

Two more columns on the same 1,400 sessions:

- `product_state` with `basedOn: [product_sku, price_eur, rating_band,
  discount_band, on_offer, age, price_change, rival_launched]`;
- `product_sku` with `basedOn: [tags, price_eur, rating_band, category,
  brand, dietary]` (its own table, so tags fit).

**Observed in the same probe, for Aito core:** without `basedOn`, 26 of the
48 small-animal states for November 2025 get `$p` ≤ 0.001. Their data are 0
purchases from 1–11 impressions (SKU-PT-0536-2025-11: 0 of 11), against a
base rate of about 0.09 for the context. Their `$why` multiplies a link
prior (×0.15) with the state's own lift, so thin, purchase-free rows go to
an extreme instead of shrinking toward the base rate.

**Stopped (2026-10-22, 13:07).** The `basedOn: ["product_sku"]` column stopped
after 253 of 1,400 sessions. At SESS-007197 (a dog household, April 2026,
five category words in the cart) Aito answers 500: `$p` is NaN, "the evidence
lifts multiplied past the range of a double". The refusal is deterministic.
The same body answers without `basedOn` (top `$p` 0.975), and without the cart
words (0.76). Not worked around: skipping such sessions would bias the
column. Repro for core: aito-core `.ai/results/recommend-lifts-saturate-many-conditions-2026-10-22.md`.

**Stopped too (2026-10-22, 16:05).** The product-fields column (`product_sku`
with `basedOn: [tags, price_eur, rating_band, category, brand, dietary]`)
stopped after 316 of 1,400 sessions on the same refusal: NaN `$p`, "lifts
multiplied past the range of a double". This time it hit the product itself,
not a state, so the overflow isn't specific to states. With the plain state
and product columns complete, B5's result above stands; the `basedOn`
columns wait on Aito core.
