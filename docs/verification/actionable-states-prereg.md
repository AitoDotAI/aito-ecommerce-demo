# Pre-registration: actionable states, reviews with consequences, acquisition (ADRs 0038–0040)

Written 2026-10-24, **before** the generator was changed for ADRs 0038, 0039
and 0040. It builds on the earlier pre-registrations, whose checks are re-run:
`lifecycle-data-prereg.md` (D1–D8), `shoppers-data-prereg.md` (S1–S8),
`product-states-prereg.md` (P1–P5, the absolute P2a and P6) and
`observable-data-prereg.md` (O1, O2, K1). Every metric, null and threshold
below is fixed now. The new fixtures go into a new env (`release2`), loaded by
Antti; master is not touched.

The generator is **not** re-tuned against these checks after seeing them. If
it has to change, this file is amended first, dated, with the reason.

**Names.** R1–R6 here are ADR 0039's effects, not the Aito checks R1–R6 of
`observable-data-prereg.md`. ADR 0032's absolute check "every row links to its
month's state" was also called P6; here it is **P0**, so that P6 can be ADR
0038's offer effect.

## Method, for every effect

- **Seeds** 42, 7 and 99 (as `./do planted-effects`).
- **Null generation:** the same seed with one switch off
  (`data/planted_switches.py`). Every other effect stays on.
- **Pass:** the check's value clears its margin **on every seed**, unless the
  row says *pooled*. "planted ÷ null" is the metric on the planted generation
  divided by the same metric on its null.
- **Each effect draws from its own seeded RNG**, and so do the draws it
  shares with the null (common random numbers):
  - an impression's click, cart and purchase come from its own RNG, keyed by
    (seed, shopper, session, position);
  - orders, experiences, reviews, replies, NPS, churn, sources and
    sensitivities each have one RNG per customer;
  - labels have one per month, stock one per product.

  So switching an impression effect off changes only the impressions it
  touches. Switching an order-side effect off (R4–R6, F4, F5) re-draws the
  histories of the customers it touches, and through stars (R5, R6) a few
  others.
- **Impression metrics read customers' impressions only.** Anonymous visitors
  (ADR 0040) have no hidden profile in the answer key and never buy.
- **"The effect's ratio among `high` ≥ 1.5× its ratio among `low`"** (ADR 0038)
  means:
  - for a sensitivity group, take the effect's contrast (e.g. purchase rate on
    offer ÷ not on offer) as planted ÷ null;
  - then divide the `high` group's value by the `low` group's value;
  - the `high` group's own planted ÷ null must also clear 1.3, so the check
    can't pass by `low` falling.
- **Expected values** are computed from the ADRs' parameters before any run,
  so a threshold can be seen not to be set from a result. Odds applied at the
  click, cart and purchase steps compound to about the odds on the purchase
  rate (P1's ×2.5 read 2.1–2.4 planted ÷ null).

## Choices the ADRs leave open, fixed here

1. **Stars under P7.** The ADR gives 5 and 1–2 stars. 4 stars gets the square
   root of the 5-star factor, 3 stars ×1.0, unrated ×0.9 (P4's) for everyone.
2. **P8 replaces P2's `NEW_ODDS`** (×1.6 for flexible shoppers). ADR 0038 lists
   it as one of the three fixed-trait effects it replaces. P2's pick pull,
   rival share and restock reconsideration stay.
3. **Sensitivity draws.** "`high` at 2× the rate" multiplies P(high), capped at
   0.9. The rest is split between `mid` and `low` in their base proportions.
   F3 multiplies on top: affiliate ×2.5 for discount, social ×2 for newness.
4. **Quality → experience** of an order line:

   | quality | bad | ok | good |
   |:--|--:|--:|--:|
   | poor | 0.45 | 0.40 | 0.15 |
   | ok | 0.06 | 0.54 | 0.40 |
   | good | 0.02 | 0.33 | 0.65 |
   | excellent | 0.01 | 0.14 | 0.85 |

   - An **order's experience** is its worst line's.
   - "An excellent one +0.7" (R3) is read as an order whose lines were all
     good.
   - A delivery incident is drawn per order at 6 %. It moves NPS only, not
     reviews or churn: ADR 0039's churn rise is "each bad experience".
   - `poor` is the 8 % of SKUs with the lowest hash. That is a subset of
     today's 15 % "poorly made", so S5's rules apply to `poor`:
     - switched away from at 0.5;
     - its leavers move to a non-poor staple.
     
     R2's ×0.6 replaces the ×0.35 on the cart and purchase steps.
5. **Reviews.** Each order line is reviewed with P 0.25 / 0.08 / 0.15 after a
   bad / ok / good experience, drawn in the order's month.
   - **Rating by experience:**
     - bad: 1 ×0.50, 2 ×0.35, 3 ×0.15;
     - ok: 2 ×0.10, 3 ×0.50, 4 ×0.40;
     - good: 4 ×0.30, 5 ×0.70.
   - **Category by rating**, so the text matches the stars:
     - 1–2: quality 0.40, shipping 0.32, fit 0.20, question 0.08;
     - 3: question 0.35, quality 0.25, shipping 0.20, fit 0.20;
     - 4: praise 0.70, question 0.20, quality 0.05, fit 0.05;
     - 5: praise 0.90, question 0.10.
   - **Replies:** 40 % of negative reviews (rating ≤ 2) are replied to,
     chosen at random.
   - **No per-customer cap** on reviews: a cap would make one review depend on
     another.
6. **NPS:** 30 % of orders are surveyed, in the order's month. The score is
   N(8.0, 1.5) plus the effects, rounded and clipped to 0–10.
7. **Churn** is a monthly hazard, drawn from the customer's churn RNG, from
   the month after their first order through 2026-04.
   - **Base hazard:** `_churn_propensity` (unchanged, so the segment, region,
     lifestyle and loyalty drivers stay), spread so that the customer's whole
     window carries it.
   - **The rise:** each bad-experience order multiplies the hazard ×1.8 for
     the next 3 months, or ×1.4 when the customer's negative review of that
     order was replied to.
   - A churned customer places no more orders. Personas never churn.
   - **Labels:** `churned` keeps its definition (last order ≤ 2026-01).
     `churn_within_90d` keeps its own (the reviewer churned and never ordered
     after the review's month), now computed from churn that followed.
8. **Low stock:** a monthly order-up-to plan per product.
   - Each delivery fills to 2.2 months of the trailing 3-month demand;
     8 % of deliveries are late (own RNG).
   - A month is `low` when its closing stock is under two weeks of the
     forecast demand.
   - Expected share of state-months: 5–20 % (descriptive, not a check).
9. **Labels.**
   - `recommended` and `staff_pick`: 5 % each of the products on sale in a
     month, drawn at random and disjoint.
   - `popular`: the top 5 % (at least one) of last month's units in each
     category.
   - A random label wins over `popular`.
10. **Derived shares** (`offer_share`, `new_share`, `label_share` on
    `contexts`): read from the shopper's **impressions purchased in earlier
    months**.
    - ADR 0038 says "orders and impressions", but ADR 0038 plants the
      sensitivities on impressions only, so order lines would only dilute
      the share (a deviation, flagged to Antti).
    - **Bands:** `none` with no earlier purchase; else `high` at or above
      0.4 (offer), above 0 (new), 0.25 (label); `low` below.
11. **Visitors** (ADR 0040).
    - `visitor` is a String id on `contexts` and `customers`, not a link to a
      table of its own: the table would hold only ids. `contexts.customer`
      becomes nullable.
    - **Never-buy visitors:** for each (source, month), never-buy sessions
      number Poisson(n·(1/c − 1)). Here n is that month's first orders from
      the source, and c is the source's F2 conversion.
      - Each visitor has 1–3 sessions.
      - 80 % bounce, with no impressions; the rest see 2–4 products on their
        landing page (`surface: landing`).
      - Never-buy visitors never buy.
    - **A customer's sessions** fall in [joined, last order + 2 months]. The
      first is the first-order session: its source is `first_source`, and
      `first_order` is true.
    - **`first_order`** (Boolean) is added to `contexts` so the funnel's
      conversion step is countable. ADR 0040's column list doesn't name it
      (flagged).
    - **Sources:**
      - first sources: organic 30 %, paid 20 %, direct 20 %, affiliate 12 %,
        email 10 %, social 8 %;
      - returning sessions: direct 35 %, email 25 %, organic 20 %, paid 10 %,
        social 5 %, affiliate 5 %.
12. **F4 and F5** are planted through a latent "regular" draw.
    - **The draw:** P = q0 × F4[source] × (2 if the first basket holds a
      staple). q0 = 0.315 keeps the overall rate at today's 52 % (seed 42,
      measured before this file).
    - **What it does to the plan:**
      - a regular customer's plan gets at least 3 orders in its first 6
        months;
      - any other customer's gets at most 2;
      - later months are as today.
    - **Staples in the first order:** the first order holds the household's
      staples with P 0.6, otherwise they start with the second order. Today
      every first order holds a staple, so F5 would have nothing to compare.
    - **`became_regular`** exists for customers who joined by 2025-11.
13. **R5 and R6.**
    - R5's factor reaches every fresh pick, as P2's pull does: the basket
      draw, the staple choice, the preference re-pick and the seasonal lines.
      It doesn't reach restocks of a staple already chosen.
    - R6 sets ε by the month's band: 5 stars −1.0, 1–2 stars −2.4, otherwise
      the product's own ε. R6 reaches promotions, rises and stock-ups alike.
14. **Stars come from reviews written before the month,** for every table: the
    generator runs month by month, so an order in March sees the stars of
    reviews written through February.

## The planted effects

### ADR 0038: actionable states and sensitivities

| # | planted as | null | metric (customers' impressions) | expected | pass when |
|:--|:--|:--|:--|:--|:--|
| P6 | on offer ×(1 + k · discount_pct / 10), k 1.0 / 0.4 / 0.1 by discount sensitivity; click, cart, purchase | P6 off | purchase rate on offer ÷ not, planted ÷ null; `high` ÷ `low` | high ≈ 2.5, low ≈ 1.15, ratio ≈ 2.2 | ratio ≥ 1.5 and high ≥ 1.3 |
| P7 | stars by stars sensitivity, 5 / 1–2: ×1.7 / ×0.45, ×1.25 / ×0.8, ×1.05 / ×0.95 | P7 off | purchase rate at 5 stars ÷ at 1–2, planted ÷ null; `high` ÷ `low` | high ≈ 6, low ≈ 1.15 | ratio ≥ 1.5 and high ≥ 1.3 |
| P8 | new, by newness sensitivity ×2.2 / ×1.3 / ×0.9 | P8 off | on launched products, purchase rate while new ÷ once established, planted ÷ null; `high` ÷ `low` | high ≈ 2.2, low ≈ 0.9, ratio ≈ 2.4 | ratio ≥ 1.5 and high ≥ 1.3 |
| P9 | label by label sensitivity: high ×1.8 / ×1.6 / ×1.7 (recommended / staff pick / popular), mid ×1.25, low ×1.0 | P9 off | purchase rate with a **random** label (recommended, staff pick) ÷ unlabelled, planted ÷ null; `high` ÷ `low` | high ≈ 1.8, low = 1.0 | ratio ≥ 1.5 and high ≥ 1.3 |
| P9p | the same for `popular` (a rule, so confounded) | P9 off | as P9, popular only | high ≈ 1.8 | reported |
| P10 | low stock ×1.25 on the purchase step only, every shopper | P10 off | P(purchase \| added to cart) on low-stock impressions, planted ÷ null | ≈ 1.05 (the step sits near 0.75) | ≥ 1.03 |
| V1 | the derived band follows the sensitivity | P6 off | P(discount `high` \| `offer_share` high) ÷ P(… \| low), over contexts, planted ÷ null | > 1 | ≥ 1.2 |

**Aggregate offer and stars**, ADR 0038's "stay inside P1's and P4's
ranges", re-checked against the new nulls:

| # | null | metric | expected | pass when |
|:--|:--|:--|:--|:--|
| P1a | P6 off | budget shoppers: purchase rate on offer ÷ not, planted ÷ null | ≈ 2.0 | ≥ 1.5 (unchanged) |
| P1b | P6 off | budget's planted ÷ null over premium's | ≈ 1.15 | ≥ 1.05 (**moved**, see below) |
| P4a | P7 off | purchase rate at 5 ÷ at 3 stars, quality not poor, planted ÷ null | ≈ 1.4 | ≥ 1.15 (unchanged) |

### ADR 0039: reviews with consequences

| # | planted as | null | metric | expected | pass when |
|:--|:--|:--|:--|:--|:--|
| R1 | P7, on the click | P7 off | click rate at 5 ÷ at 1–2 stars, planted ÷ null | ≈ 1.75 | ≥ 1.4 |
| R2a | P7 on the purchase | P7 off | purchase rate at 5 ÷ at 1–2 stars, planted ÷ null | ≈ 2.6 | ≥ 1.8 |
| R2b | a `poor` product's impression ×0.6 on cart and purchase | quality odds off | purchase rate of `poor` products ÷ the rest, planted ÷ null | ≈ 0.71 | ≤ 0.8 |
| R3a | NPS: base 8.0 (σ 1.5); bad experience −3.5, incident −2.0, all-good +0.7, a reply to the respondent's negative review of the order +2.0 | R3 off | mean NPS after a bad-experience order, planted − null | ≈ −3.4 | ≤ −2.5 |
| R3b | the same, for every buyer | — | after a bad-experience order: non-reviewers' mean NPS (planted); and the difference between unreplied reviewers and non-reviewers | ≈ 4.6; ≈ 0 | ≤ 5.5; within ±0.5 |
| R3c | a reply recovers +2.0 | — (replies are random) | mean NPS of negative-review writers with a reply − without, on the surveyed order | ≈ +2.0 | ≥ +1.2 |
| R4a | each bad experience ×1.8 on the churn hazard for 3 months | R4 off | P(the customer churns in the 3 months after a bad-experience order), from the answer key's churn month, orders through 2026-01; planted ÷ null | ≈ 1.75 | ≥ 1.4 |
| R4b | a reply halves the rise (×1.4) | reply effect off | P(churn in the 3 months after a replied negative review) among its writers, planted ÷ null, **pooled** over the three seeds | ≈ 0.78 | ≤ 0.9 |
| R4c | the same rise, as a shop sees it | R4 off | share of bad-experience orders (through 2026-01) after which the customer never orders again, planted ÷ null | ≈ 1.08 | reported |
| R5 | pick weight by the month's band: 5 ×1.3, 1–2 ×0.6 | R5 off | units per state-month at 5 stars ÷ at 1–2, planted ÷ null | ≈ 1.5–2.0 | ≥ 1.4 |
| R6 | ε by band: 5 stars −1.0, 1–2 −2.4 | R6 off | (units on offer ÷ off offer per state-month) at 1–2 stars ÷ the same at 5 stars, planted ÷ null | ≈ 1.3 | ≥ 1.1 |

### ADR 0040: acquisition

| # | planted as | null | metric | expected | pass when |
|:--|:--|:--|:--|:--|:--|
| F1a | organic search lands on product pages 70 % | F1 off (one landing mix for every source) | P(landing = product \| organic), planted ÷ null | ≈ 2.0 | ≥ 1.6 |
| F1b | social lands on toys and treats 55 % | F1 off | P(landing category ∈ toys, treats \| social), among contexts with a landing category, planted ÷ null | ≈ 2.5 | ≥ 1.8 |
| F1c | email and affiliate land on offers 60 % | F1 off | P(landing = offer \| email or affiliate), planted ÷ null | ≈ 3 | ≥ 2.0 |
| F2a | a new visitor's session converts at email 6 %, paid 4 %, organic 3 %, direct 5 %, affiliate 3.5 %, social 1.2 % | F2 off (every source at the pooled rate) | conversion = first-order sessions ÷ all new-visitor sessions; email's ÷ social's, planted ÷ null | ≈ 5 | ≥ 3.0 |
| F2b | the same | — | each source's conversion on the planted data | its rate | within ±20 % of it |
| F3a | an affiliate customer is discount-`high` at 2.5× | F3 off | P(discount high \| affiliate) ÷ P(… \| other sources), customers, planted ÷ null | ≈ 2.1 | ≥ 1.8 |
| F3b | a social customer is newness-`high` at 2× | F3 off | P(newness high \| social) ÷ P(… \| other), planted ÷ null | ≈ 2.0 | ≥ 1.5 |
| F3c | affiliates buy on offer | F3 off | affiliate customers' on-offer share of their purchased impressions ÷ others', planted ÷ null | > 1 | reported |
| F4a | P(regular) by first source: organic ×1.4 … affiliate ×0.5 | F4 off | `became_regular` rate, organic ÷ affiliate, planted ÷ null | ≈ 2.5 | ≥ 1.6 |
| F4b | social ×0.6 | F4 off | `became_regular` rate, social ÷ organic, planted ÷ null | ≈ 0.45 | ≤ 0.7 |
| F5a | a staple in the first basket ×2 | F5 off | `became_regular` rate with ÷ without a staple in the first basket, planted ÷ null | ≈ 1.9 | ≥ 1.5 |
| F5b | "whatever the source" | F5 off | F5a within organic and within affiliate | ≈ 1.9 | reported |

## Where the ADRs' own numbers can't hold (found before any run)

1. **P1b premium ≤ 1.3.**
   - P6 gives premium shoppers the base sensitivities (30 % discount-high),
     so their offer odds average ≈ 1.9; the ratio is expected ≈ 1.8.
   - ADR 0038's "stays inside P1's ranges" can't hold for this half. It is
     retired, with that reason.
   - The other half (budget's lift ÷ premium's ≥ 1.4) comes only from
     budget's 2× discount-high rate now: expected ≈ 1.15. It moves to
     ≥ 1.05.
2. **P2d** (flexible ÷ loyal take to new, ≥ 1.25):
   - P8 links newness to loyalty only through the 2× rate, so the ratio is
     expected ≈ 1.15. It already missed once at 1.6 planted.
   - It is retired; P8 supersedes it.
3. **R4b, "≤ 0.75× an unreplied one's".**
   - The rise is ×1.8 unreplied and ×1.4 replied, so the expected churn
     ratio is (1 + 0.4) ÷ (1 + 0.8) ≈ 0.78 whatever the base hazard. The
     ADR's 0.75 can't be met.
   - The ADR's headline quantity is the *added* churn, which the reply does
     halve (0.4 against 0.8). The check above measures it against the
     reply-off null.
   - About 280 replied reviews per seed make one seed too few, so it is
     pooled.
   - **For Antti:** at this strength the Reviews view's replied ÷ unreplied
     interval will probably overlap 1. The observable churn effect of a bad
     experience (R4c ≈ 1.08) is small: the base hazard is ≈ 1.6 % a month.
4. **ADR 0039's test** ("reviews disabled, churn rate unchanged") is false by
   design. Two of the ADR's planted paths go from reviews to churn:
   - a reply lowers its writer's churn (R4);
   - stars move which products are bought (R5, R6), and so which
     experiences follow.

   The test instead:
   - runs with replies' churn effect, R5 and R6 off, and asserts that every
     customer's churn month is *identical* with and without reviews;
   - asserts that a review's rating, category and text depend only on its
     line's experience, not on the writer's churn.

   That is the reversed path the ADR removes.
5. **Signal #8, P(churn | 1★) ≥ 1.6 × P(churn | 5★)** (`tests/test_fixtures.py`).
   - It held because churn wrote the reviews. Through the causal path it is
     expected ≈ 1.1.
   - It is retired; R4 and the two tests above replace it.
   - The Feedback view's "churn risk from text" will be weaker, truthfully.
6. **Review volume 5,000–7,000** (`test_reviews_count_supports_explanations`):
   - ADR 0039's review rates give ≈ 5,000 on about 39,000 lines, at the
     floor.
   - The band becomes 4,000–7,000.

## The older checks

- **`./do planted-effects`** runs P1a, P1b, P2b, P2c, P3a, P4a, P5a, K1a and
  K1b with their registered nulls and margins.
  - P1's null is now P6 off, and P4's null P7 off.
  - P2's null keeps its launch pull, rival share and reconsideration, without
    `NEW_ODDS`, which P8 replaces.
  - The report is `docs/verification/actionable-states-data.md`;
    `product-states-data.md` stays as ADR 0032's record.
- **`./do test` on the seed-42 fixtures** runs the rest: D1–D8, S1–S8, O1,
  O2, P0, P2a and the other signal tests.
- **A moved range** is either of:
  - a check here that fails;
  - an older check that fails where it last passed: a `./do test` data test
    on seed 42, or a planted ÷ null check on a seed where its last recorded
    run passed.

  Each is reported with its value and a diagnosed cause. Its range changes
  only by a dated amendment below, with the reason, before it is re-run.
- **A threshold set above** is not moved by an amendment of this kind. A
  failure of one is reported as a failure.

## Table sizes (expected; measured in the results)

- `impressions` ≈ +45 % (anonymous landing pages), ≈ 170,000.
- `contexts` ≈ 8× (bounced visits are rows without impressions),
  ≈ 100,000.
- `nps_responses` ≈ 3,600.
- The other tables stay within 10 % of today, except `reviews` (≈ 5,000).

## Amendment after the first generation (2026-10-24, older checks only, before any null run)

The first seed-42 generation passed every `./do test` data check but two.
Both are older ranges that moved, with the causes below. Neither is a check
registered above, and the generator is not changed for them.

| check | before (seed 42) | now | cause | change |
|:--|--:|--:|:--|:--|
| Signal #6, a region's churn ≥ 1.3× the base (`test_signal_6_churn_drivers_are_learnable`) | oulu 1.37× | oulu 1.29× | Churn is now a monthly hazard spread over the customer's whole window, through 2026-04 (choice 7). The quarter of it that falls after 2026-01 doesn't mark `churned`. The churn of sparse ordering, which has no driver, is unchanged, so the driver's share of the label is diluted. Among hazard churn, oulu's rate is 4× helsinki's. | Floor 1.25×. That still clears the Churn view's \|lift − 1\| ≥ 0.15. |
| D1, food re-buy share ≥ 45 % (`test_d1_customers_rebuy_their_food`) | 46.0 % | 43.0 % | Two causes, both by design. 40 % of households now start their staples with their second order (choice 12), so a first-order food comes from the basket draw and is often not the food they settle on. Customers who don't become regular have at most 2 orders in their first 6 months, so there are fewer restocks (3.77 orders a customer, was 3.97). | Floor 40 %. |

Signal #8 (1★ ÷ 5★ churn) read 1.71 on this generation; it stays retired as
registered above. 2★ reviews read 0.065 against 5★'s 0.070, so at 218 one-star
reviews the ratio is noise around the causal path's ≈ 1.1.

## Results

### Offline checks, 2026-10-24 (seeds 42, 7, 99; `./do planted-effects`)

Full table: `actionable-states-data.md`. **114 of 118 judged rows pass.** Every
new effect passes on every seed except R2b. One older check, P2c, misses on
one seed.

| # | threshold | seed 42 | seed 7 | seed 99 | result |
|:--|:--|--:|--:|--:|:--|
| P6 high ÷ low (high alone) | ≥ 1.5 (≥ 1.3) | 1.90 (2.18) | 1.98 (2.32) | 1.92 (2.25) | pass |
| P7 high ÷ low (high alone) | ≥ 1.5 (≥ 1.3) | 3.92 (4.17) | 3.59 (3.93) | 2.95 (3.26) | pass |
| P8 high ÷ low (high alone) | ≥ 1.5 (≥ 1.3) | 2.39 (2.06) | 1.93 (1.83) | 2.18 (1.99) | pass |
| P9 high ÷ low (high alone) | ≥ 1.5 (≥ 1.3) | 1.58 (1.58) | 1.59 (1.59) | 1.63 (1.63) | pass |
| P9p (popular) | reported | 1.51 | 1.51 | 1.56 | — |
| P10 | ≥ 1.03 | 1.032 | 1.037 | 1.036 | pass |
| V1 | ≥ 1.2 | 1.45 | 1.51 | 1.47 | pass |
| P1a | ≥ 1.5 | 1.91 | 2.03 | 1.93 | pass |
| P1b (moved) | ≥ 1.05 | 1.16 | 1.22 | 1.13 | pass |
| P4a | ≥ 1.15 | 1.33 | 1.31 | 1.31 | pass |
| R1 | ≥ 1.4 | 1.65 | 1.59 | 1.52 | pass |
| R2a | ≥ 1.8 | 2.01 | 1.92 | 1.85 | pass |
| **R2b** | ≤ 0.8 | **0.827** | **0.822** | **0.831** | **fail** |
| R3a | ≤ −2.5 | −3.45 | −3.37 | −3.33 | pass |
| R3b (non-reviewers' NPS) | ≤ 5.5 | 4.26 | 4.21 | 4.47 | pass |
| R3b gap | ≤ 0.5 | 0.24 | 0.01 | 0.07 | pass |
| R3c | ≥ 1.2 | 1.79 | 2.25 | 1.71 | pass |
| R4a | ≥ 1.4 | 1.97 | 2.13 | 1.70 | pass |
| R4b, pooled (23/398 planted, 33/398 null) | ≤ 0.9 | | | 0.697 | pass |
| R4b per seed | reported | 0.71 | 0.60 | 0.75 | — |
| R4c (observable churn) | reported | 1.17 | 1.20 | 1.16 | — |
| R5 | ≥ 1.4 | 1.57 | 1.71 | 1.47 | pass |
| R6 | ≥ 1.1 | 1.44 | 1.17 | 1.35 | pass |
| F1a / F1b / F1c | ≥ 1.6 / 1.8 / 2.0 | 2.01 / 2.51 / 3.03 | 1.99 / 2.43 / 3.00 | 1.99 / 2.46 / 3.05 | pass |
| F2a | ≥ 3.0 | 5.12 | 5.06 | 4.98 | pass |
| F2b (worst source off its rate) | ≤ 0.2 | 0.021 | 0.014 | 0.009 | pass |
| F3a / F3b | ≥ 1.8 / 1.5 | 2.28 / 2.06 | 2.01 / 1.94 | 1.97 / 2.25 | pass |
| F3c | reported | 1.13 | 1.13 | 1.13 | — |
| F4a / F4b | ≥ 1.6 / ≤ 0.7 | 3.05 / 0.40 | 2.88 / 0.48 | 3.00 / 0.48 | pass |
| F5a | ≥ 1.5 | 2.07 | 1.99 | 1.99 | pass |
| F5b organic / affiliate | reported | 2.03 / 2.61 | 1.87 / 2.22 | 2.18 / 2.16 | — |
| P2b, P3a, P5a, K1a, K1b | as registered | pass | pass | pass | pass |
| **P2c** | ≤ 0.95 | 0.943 | 0.949 | **0.957** | **fail on seed 99** |

**R2b fails on every seed**, at 0.82–0.83 against ≤ 0.8 (expected ≈ 0.71). It
is reported as a failure and nothing is retuned. The expectation assumed the
cart and purchase steps sit near 0.7–0.75. The likely cause, not yet checked:
many poor products' impressions sit at those steps' caps (0.92, 0.95), where
×0.6 odds move the rate less. ADR 0032's first null run saw the same
saturation for stars. A poor product still converts at ≈ 0.83 of the rest on
top of its low stars. Moving the threshold or strengthening the ×0.6 (the
ADR's number) is Antti's call, by amendment.

**P2c misses on seed 99** at 0.957 (≤ 0.95). It passed there at 0.943 in the
last recorded run (`product-states-data.md`). Its mechanism is unchanged; its
margin was already thin (0.943–0.949 on the other seeds). R5's star-weighted
picks and the month-by-month order loop re-draw the histories it reads. This
is an older range that moved. It is reported, not amended.

**Retired as registered:** P1b's premium half and P2d. Signal #8 read 1.71
(see the amendment above).

**What a shop sees of churn:** R4c, the share of bad-experience orders after
which the customer never orders again, is ×1.16–1.20 against its null. The
hidden hazard reads ×1.7–2.1. The replied ÷ unreplied contrast rests on 23
against 33 churners in three seeds, so the Reviews view's interval for it
will overlap 1, as predicted above.

### Decision (2026-10-24, delegated by Antti, after the results above)

**R2b and P2c are accepted as recorded failures.** No threshold or parameter
changes.
- Both effects exist but are weaker than registered: a poor product converts
  at ≈ 0.83 of the rest against its null, and incumbents lose ≈ 5 % to a
  launch.
- The views won't quote R2's size.
- R2b's likely cause (the cart and purchase steps at their caps) is untested.

**The choices made beyond the ADRs' text are accepted as made:**
- `offer_share`, `new_share` and `label_share` are read from impression
  purchases in earlier months, not from orders;
- `contexts.first_order` (Boolean) makes the funnel's conversion step
  countable;
- `visitor` is a String id on `contexts` and `customers`, not a link to a
  table of its own;
- a visitor who hasn't bought yet is shown products on `surface: landing`.

**One rename.** `nps_responses.order` becomes `surveyed_order`, so the column
is clear of any reserved word in Aito without probing that with a write.
- Only the column's name changes; every other fixture is byte-identical.
- The rename touches the schema, the generator, the R3 metrics and ADR 0039's
  table.

### Table sizes (seed 42)

| table | rows | before |
|:--|--:|--:|
| impressions | 168,496 | 117,026 (+44 %; 54,258 on visitors' landing pages) |
| contexts | 103,134 | 12,662 (90,775 before a first order; most bounced, with no impressions) |
| nps_responses | 3,420 | new |
| reviews | 4,627 | 6,000 |
| orders / order_lines | 11,318 / 35,943 | 11,909 / 39,098 |
| customer_months | 27,008 | 27,525 |
| product_states, monthly_sales | 15,157 | 15,157 |

`contexts.json` is 37 MB. It joins `impressions.json` (46 MB) as generated and
gitignored; `./do` regenerates both when missing.

## Addendum (2026-10-24): ADR 0044, what a shop can know about a person

Written **before** the generator changes for ADR 0044. Everything registered
above stands; this adds C1–C3 and says how consent changes the older checks.

### What changes in the data

- **`customers` gains:**
  - `consent_behavioural` (Boolean, P 0.6, its own RNG per customer, so it is
    independent of every hidden trait). The three generator personas
    (CUST-00001…3) consent: their behaviour anchors the older demo views.
  - `sex` (`female` / `male` / `other`, filled for 55 %; no effect anywhere).
  - `postcode_area`: the first 3 digits, drawn within the customer's region
    (Helsinki 001–009, Espoo 020–028, Turku 200–209, Tampere 330–339,
    Jyväskylä 400–409, Oulu 900–909).
  - `delivery_method` (home delivery 0.45, parcel locker 0.40, store pickup
    0.15).
  - `loyalty_member` (P 0.4).
  - `interests`: nullable whitespace Text, about 35 % filled, from the fixed
    list `training grooming natural_food toys_and_play health_and_care
    budget_buys`.
- **Consent and behaviour rows.** A non-consenting customer has no
  `contexts` or `impressions` rows. Their orders, reviews and NPS answers are
  unchanged: no order-side draw reads consent.
- **Visitors.** Consent is one decision per device, made on the cookie
  banner before any purchase:
  - a never-buy visitor consents with P 0.6, from its own RNG; a
    non-consenting one leaves no rows at all;
  - a customer's consent is the one they gave as a visitor, so their
    first-order visit is recorded only if they consent.

  So F2's numerator and denominator thin alike, and conversion by source
  keeps its expected value.
- **Interests.** A customer declares interests with P 0.35. Each topic is
  then included independently:
  - `natural_food`: 0.95 for a grain-free diet-rule household, 0.40 for a
    high health focus, 0.05 otherwise;
  - `budget_buys`: 0.6 if budget, else 0.1;
  - `toys_and_play`: 0.6 if the treat affinity is high, else 0.15;
  - `health_and_care`: 0.5 if the health focus is high, else 0.15;
  - `grooming` and `training`: 0.25 each;
  - when none is drawn, one of the five other than `natural_food`, uniformly.
- **The answer key** records `consent_behavioural` beside the hidden traits.

**Why `natural_food` reads the diet rule too.** Measured on the current seed-42
data before this addendum: the hidden health focus alone moves the grain-free
share of food and treat lines from about 0.21 to 0.29 (×1.37). A declaration
drawn from health focus alone can't reach ADR 0044's ≥ 1.8. The grain-free
diet-rule households are the other trait consistent with "natural food". With
the weights above, the expected ratio is ≈ 2.0, computed on the same data
before any change. A test of C1 then reads that "natural food" declarers are
mostly those households: consistent, not a new cause.

### The planted effects

| # | planted as | null | metric | expected | pass when |
|:--|:--|:--|:--|:--|:--|
| C1 | interests drawn from the hidden traits | C1 off: every topic at 0.3, whatever the traits | grain-free share of food and treat lines, customers declaring `natural_food` ÷ every other customer (planted); and planted ÷ null | ≈ 2.0; ≈ 2.0 | planted ≥ 1.8; planted ÷ null reported |
| C2 | consent independent of the traits | — | consent rate overall; for every level of `segment`, `lifestyle`, `health_focus`, `treat_affinity`, `brand_loyalty` and the four sensitivities with ≥ 100 customers, \|its consent rate − the overall\| (the largest) | 0.60; ≈ 0.03 (one level of ~750 has SE ≈ 0.018) | 0.55–0.65; largest gap ≤ 0.07 |
| C3 | sex has no effect | — | for each category with ≥ 1,000 lines, its share of female buyers' lines ÷ its share of male buyers' lines; the largest \|log ratio\| | ≈ 1.0 | every ratio within 0.8–1.25 |

C2 and C3 are judged on the planted data alone: there is nothing to switch off.
They run on every seed.

### What consent does to the older checks

Every impression-based check now reads about 60 % of the customers'
impressions. That covers P6–P10, V1, P1a, P1b, P4a, R1, R2a, R2b, F1, F2, F3c,
K1a and K1b, and the S5b, S6 and S8 tests.
- **Expected values don't change**, because consent is independent of the
  traits (C2).
- **The noise of a planted ÷ null ratio grows** by about √(1 / 0.6) ≈ 1.29.
- **Order-side checks don't move at all:** R3–R6, F3a, F3b, F4, F5, P2b,
  P2c, P3a, P5a, the D checks and the reviews.

**Thresholds are not moved for power.** The checks whose last margin is
small against that noise, with their expected values (the mean of the last
run's three seeds), fixed now:

| check | last run (42 / 7 / 99) | expected | margin | risk |
|:--|:--|--:|:--|:--|
| P10 | 1.032 / 1.037 / 1.036 | 1.035 | ≥ 1.03 | high: a seed can miss by noise alone |
| P9 high ÷ low | 1.58 / 1.59 / 1.63 | 1.60 | ≥ 1.5 | moderate |
| R2a | 2.01 / 1.92 / 1.85 | 1.93 | ≥ 1.8 | moderate |
| R1 | 1.65 / 1.59 / 1.52 | 1.59 | ≥ 1.4 | low |
| P1b | 1.16 / 1.22 / 1.13 | 1.17 | ≥ 1.05 | low |
| F2b (worst source off its rate) | 0.021 / 0.014 / 0.009 | ≈ 0.03 | ≤ 0.2 | low (fewer sessions per source) |

R2b and P2c stay the accepted failures recorded above. P2c is order-side, so
its values repeat exactly.

**Rows** (expected): impressions ≈ 101,000 and contexts ≈ 62,000, both about
60 % of the last run's. Every other table is unchanged in rows.


### A change to the catalogue, not an effect (2026-10-24, before the run)

239 of 658 SKUs shared a display name with another SKU of identical attributes,
e.g. "Trixie Hideout" (SKU-PT-0563, -0564). The variant loop of `gen_products`
draws them, and food collides too (the same pack size and dietary drawn twice).
A merchant reads that as a duplicate.

- **The change:** each product of a shared name gets a distinguishing
  variant, after a comma, in SKU order: "Trixie Hideout, small" / ", medium";
  "… Dog Food 2kg, classic recipe" / ", light recipe". The variant is also a
  new `products.variant` column, absent where the name was already unique.
- **No RNG draw:** every other byte of the data stays as it was.
- **Names are parsed in two places,** and both are updated:
  - `lifecycle.item_type` drops what follows the comma, so kit items, durables
    and search phrases read as before;
  - the search-phrase matcher ignores the comma.
- **A test asserts** that product names are unique.

It plants nothing and moves no registered value: the effects read SKUs and
attributes, not names. It is re-run with everything else.

### Amendment after the first ADR 0044 generation (2026-10-24, before the null run)

One older test moved, by sample size only, as the addendum foresaw for S8.

- **The test:** S8 (`test_s8_a_product_just_bought_converts_less_when_shown_again`)
  requires at least 1,000 impressions in each of its two groups, before
  comparing their purchase rates.
- **What moved:** with behaviour recorded for about 60 % of customers, the
  groups hold 767 (just bought) and 725 (bought earlier).
- **What didn't:** the ratio it judges reads 0.25 (34/767 ÷ 128/725), against
  ≤ 0.5, as before.
- **Change:** the floor becomes 600, about 60 % of 1,000. The ratio's
  threshold is unchanged.

### Results with ADR 0044 and the catalogue change (2026-10-24; seeds 42, 7, 99)

Full table: `actionable-states-data.md`. **126 of 130 judged rows pass.** The four
that fail are the accepted failures decided above: R2b on every seed, and P2c
on seed 99. Nothing was retuned.

| # | threshold | seed 42 | seed 7 | seed 99 | result |
|:--|:--|--:|--:|--:|:--|
| C1 (planted) | ≥ 1.8 | 2.09 | 2.27 | 2.24 | pass |
| C1 ÷ its null | reported | 2.24 | 2.08 | 2.00 | — |
| C2, consent rate off 0.6 | ≤ 0.05 | 0.003 | 0.018 | 0.007 | pass |
| C2, largest trait-level gap | ≤ 0.07 | 0.046 | 0.030 | 0.027 | pass |
| C3, largest \|log\| female ÷ male category share | ≤ 0.223 | 0.053 | 0.150 | 0.041 | pass |
| P10 (power-risk) | ≥ 1.03 | 1.031 | 1.041 | 1.037 | pass |
| P9 high ÷ low (power-risk) | ≥ 1.5 | 1.60 | 1.57 | 1.66 | pass |
| R2a (power-risk) | ≥ 1.8 | 2.00 | 1.85 | 1.86 | pass |
| R1 | ≥ 1.4 | 1.66 | 1.58 | 1.53 | pass |
| P1b | ≥ 1.05 | 1.19 | 1.19 | 1.14 | pass |
| F2b | ≤ 0.2 | 0.017 | 0.082 | 0.100 | pass |
| R2b (accepted failure) | ≤ 0.8 | 0.812 | 0.812 | 0.832 | fail |
| P2c (accepted failure) | ≤ 0.95 | 0.943 | 0.949 | 0.957 | fail on 99 |

- **Every other row** passes as before; the values are in the full table.
- **The order-side checks repeat exactly**, as the addendum predicted: R3–R6,
  F3a, F3b, F4, F5, P2b, P2c, P3a and P5a. Consent and the variant names draw
  nothing those checks read.
- **Of the impression checks,** P10 kept its margin on seed 42 by 0.001.
- **The `./do test` data checks** pass on seed 42, with S8's sample floor as
  amended.
- **Rows:** impressions 100,450, contexts 61,995 (54,670 before a first
  order). Every other table is unchanged in rows.

## Addendum (2026-10-24): ADR 0045, one source for showings and sales, and partial pet profiles

Written **before** the generator changes for ADR 0045. Everything registered above
stands unless an item below says it moves, and why.

### The session model, fixed now

- **Sessions:** every customer has one session in each month they plan to
  order, consenting or not, until churn. Consent decides only whether its
  `contexts` and `impressions` rows are written (ADR 0044).
- **Orders:** a session's purchases are its order, so there is at most one
  order a month (D4 keeps its meaning). A session without purchases leaves no
  order.
- **Before the first order:** a session before the customer's first purchase
  is a visitor's session, with no `customer` and the first source.
- **What a session shows:** one page, recorded in a new column
  `impressions.placement`. ADR 0045 doesn't name it; it is needed so a
  position means one thing.
  - **`buy_again`** — what the household came for, computed exactly as the
    old order lines were chosen:
    - the starter kit (first order);
    - each staple (first choice, restock, or a switch, as now);
    - the next add-on (as now);
    - the December gift and summer care lines (S4, as now).

    Each is purchased with its intent probability, as odds with every
    state and price odd applied:

    | item | intent probability |
    |:--|--:|
    | a restock | 0.6 (`RESTOCK_P`) |
    | a first choice or a switch, a kit item | 0.95 |
    | an add-on, a seasonal line | 0.9 |
  - **`list`** — 6–14 products the shop's ranker picked and ordered,
    shown on 70 % of sessions; the other 30 % are `direct`, reorders without
    browsing (ADR 0045).
    - Candidates are drawn by the old affinity and filler weights, times the
      **merchandising factor**:
      - offer band ×1.3 (10–15 %), ×1.5 (15–20 %), ×1.8 (20 %+);
      - new ×2.0 (P2's pull);
      - a rival's launch ×0.75;
      - stars, R5's ×1.3 / ×0.6;
      - the season (S4).
    - They are ordered by that factor × lognormal noise (σ 0.5).
    - The funnel is the old one. On top of it:
      - clicks × 0.9 per slot (position bias);
      - × 2.0 click odds for a month the household shops;
      - owned durables × 0.02;
      - an out-of-order add-on × 0.2 (the old skip of 0.8).
  - **`checkout`** — a dental chew after dog dry food was bought, with the
    old probabilities by treat affinity, at intent 0.9 (Signal #2).
- **Price acts in one place: each showing's odds.**
  - The offer, by discount sensitivity (P6).
  - The list price against the original, as (price ÷ original)^ε, with ε by
    the product's stars (P3, R6).
  - Quantities no longer stock up on offer.
  - No pick weight reads price.
- **Product states are drawn at each month's start,** from what happened
  before it:
  - `popular`: last month's units;
  - stars and review counts: reviews before the month;
  - `stock: low`: the opening stock (after this month's delivery, or none
    if it is late) is under the month's forecast plus two weeks;
  - late deliveries become 15 %, so the low share stays near 10 %.

  The old `low`, which read the month's own demand, can't be known before
  the month.
- **`monthly_sales` = Σ purchased order lines,** plus:
  - `price_index`: price ÷ that month's list price;
  - `discount_band`;
  - `showings`: recorded impressions of the product that month.
- **Derived shares** (`offer_share` …) are now read from the customer's
  earlier order lines. Every purchase is now a showing, so orders and
  impressions agree. This replaces choice 10's "impression purchases only".

### Partial pet profiles (Antti, 2026-10-24)

- **`customers.pets` becomes nullable:** about 40 % fill a pet profile (own
  RNG per customer, independent of the traits). `dog_size` exists only
  with a profile. The generator personas (CUST-00001…3) keep theirs.
  `customer_months.pets` and `dog_size` copy them and become nullable too.
- **`contexts.pets_from_orders`** (whitespace Text): the pet types of the
  products in the customer's orders before the month. It is derived visibly
  and computed in one place (`data/observable.py`), as ADR 0033 asks.
- **Personas:** Päivi keeps a declared profile, or is re-picked to a customer
  with one. One more Shop shopper has no profile.

### The new checks

| # | null | metric | expected | pass when |
|:--|:--|:--|:--|:--|
| O1 | — | `monthly_sales.units_sold` = Σ that month's purchased order lines, every product and month; every purchased impression has its order line (same customer, month, SKU) | exact | test |
| O2 | offers off (P6 and the merchandising offer factor) | units per state-month at a 20 %+ offer, planted ÷ null | ≈ 2.0–3.0 (per-showing lift ≈ 2 on lists, ≈ 1.2 on buy-again; placement ≈ 1.5 on lists) | ≥ 1.8 (ADR) |
| O3a | placement off (the offer factor only) | recorded showings per on-offer state-month, planted ÷ null | ≈ 1.3–1.5 | ≥ 1.2 (ADR) |
| O3b | — | customers' list click rate by position, slots 0–9 | falls ≈ 10 % a slot | falls at every slot (monotone) |
| O4 | — (live, env `release2`) | `_estimate units_sold` with `price_index`, within product, on a held-out month: the implied ε | ≈ −2 … −3 | in [−2.5, −0.5] (ADR). **Pending:** needs the loaded env |
| O5 | — | every older check re-run | — | moved ranges amended, dated |

### What ADR 0045 moves, expected now

| check | why | expected | change, made now |
|:--|:--|:--|:--|
| Impression checks (P6–P10, V1, P1, P4a, R1, R2, F3c, K1, S5b, S6, S8, C-none) | they read the shop's lists; buy-again and checkout showings are intent | as before, minus some compression from the click intent | they read `placement: list` only; thresholds unchanged |
| D5, median fitted elasticity in [−2, −1] | offers now act through P6 (by sensitivity) and placement, not ε | ≈ −3 (units ≈ ×1.9 at 17.5 % off) | range becomes [−4, −1]: demand still falls with price, more steeply |
| R6, offer response by stars | offers no longer read ε, so this metric no longer measures R6. R6 acts only on list-price changes (60 rises: too few to judge) | — | **reported**, not judged; flagged to Antti |
| P10 | the low share falls with the causal stock state; late deliveries go to 15 % to keep it near 10 % | ≈ 1.04 | unchanged ≥ 1.03; high risk |
| Review volume 4k–7k, D2 (starter share ≥ 60 %) | order lines are now purchases from a page | lines ≈ 30–35 k, reviews ≈ 4.0–4.6 k; D2 ≈ 0.6 | unchanged; at risk, amended with a reason if they move |
| Signal #3, persona separation | personas' histories re-drawn | — | re-picked or amended if it moves |

### A sweep for the Shop, to run once `release2` is loaded (design only)

**Question:** for a shopper without a pet profile, what should "Picked for you"
condition on?

- **Sessions:** 1,400 held-out customer sessions from 2025-05 on, drawn with
  `random.Random(0).sample`. Each comes from a customer without `pets`, with
  at least one earlier order and at least one product bought in the session.
  Each session is left out of the data (nested `from`, as ADR 0033's sweep).
- **Query:** the Shop's "Picked for you" query (month, cart words,
  `just_bought: false`, the diet rule when declared). Three variants:
  - **I:** identity, `context.customer`;
  - **P:** `context.pets_from_orders` as evidence, and as the candidate
    filter that declared pets are for others;
  - **I+P:** both.
- **Metrics:**
  - **primary:** hit@12;
  - **secondary:** Brier score of `$p` over the products shown.
- **Comparisons:** paired 95 % CIs over sessions, for P − I, I+P − P and
  I+P − I.
- **Decision:** the Shop uses the best variant on hit@12 whose Brier score
  is within 0.01 of the best. A difference whose CI includes 0 is a tie, and
  a tie goes to P, which needs no identity.

### Amendment after the first ADR 0045 generation (2026-10-24, before any null run)

**One omission of the rewrite, restored.** The first seed-42 generation read D1
(food re-buy) at 32.7 %, against 40 %.

- **Cause:** the old basket draw re-pointed a drawn food to the household's
  settled staple 85 % of the time (`STAPLE_LOYALTY`, ADR 0027). The rewrite
  carried the staples into `buy_again`, but not that rule into the list.
  So a list sold any food of the staple's category: food reached 53 % of
  lines.
- **The rule restored, as odds:** another food of a pet and category the
  household has a staple for sells at ×0.15 (= 1 − 0.85) on a list.
- **Why this isn't a retune:** this is the registered "computed exactly as
  the old order lines were chosen", now implemented. No threshold moves, and
  nothing is tuned to a value.

**The tests read what was registered:** S5b, S6 and S8 read
`placement: list`, as the addendum says impression checks do.

**Stars now reach orders.** A purchase is a showing, so P7's stars reach
orders. The test that "without reviews every customer churns as with them"
therefore switches P7 off too, beside R5, R6 and the reply. A review's
stars are a fourth planted path from a review to churn, in the causal
direction.

### Amendment after the second ADR 0045 generation (2026-10-24, before any null run)

Restoring the staple rule moved D1 from 32.7 % to 37.7 %. Nothing in the
generator changes after this. These older ranges moved, each with its cause:

| check | now (seed 42) | cause | change |
|:--|:--|:--|:--|
| Order volume 11k–16k (`test_volumes_match_task_md_bands`) | 10,834 | a session that buys nothing leaves no order (ADR 0045); 3.61 orders a customer, was 3.77 | 10k–16k |
| D1, food re-buy ≥ 40 % | 37.7 % | a list's other foods still sell at ×0.15 odds of a list's base rate, where the old re-pick turned 85 % of food draws into re-buys outright | ≥ 35 % |
| D5, median fitted elasticity | −2.00 | as pre-registered: offers act through P6 and placement | [−4, −1], the range registered in the addendum |
| Signal #6, a region's churn ≥ 1.25× | oulu 1.22× | fewer orders a customer means more churn from sparse ordering, which has no driver; among hazard churn, oulu's rate is still 4× helsinki's | ≥ 1.2× (still clears the view's \|lift − 1\| ≥ 0.15) |
| S8 sample floor ≥ 600 | 359 just-bought list impressions | S8 now reads lists only, as registered, and a restocked staple is shown in buy-again, not the list | ≥ 300; its ratio, 0.34 against ≤ 0.5, holds |
| Signal #3, Maija's top 5 pairs | 4 pairs | her 12 orders hold staples and accessories only: since ADR 0045 a list sells only what its odds sell, and she is low on treats | compare each persona's top pairs, up to 5. Disjointness, the point of the test, reads 0 shared |

### Results with ADR 0045 and partial pet profiles (2026-10-24; seeds 42, 7, 99)

Full table: `actionable-states-data.md`. **118 of 136 judged rows pass.** Nothing
was retuned after the run. The failures are reported, by check:

| # | threshold | seed 42 | seed 7 | seed 99 | result |
|:--|:--|--:|--:|--:|:--|
| **O2**, units at a 20 %+ offer ÷ offers-off null | ≥ 1.8 | 1.64 | 1.59 | 1.65 | **fail** every seed |
| **O3a**, showings on offer ÷ placement-off null | ≥ 1.2 | 1.21 | 1.20 | 1.20 | **fail** on 7 and 99 (just under) |
| O3b, list slots clicked as often as the slot above | 0 | 0 | 0 | 0 | pass (clicks fall at every slot) |
| O4 | live | | | | **pending** `release2` |
| **P8** high ÷ low | ≥ 1.5 | 1.38 | 1.94 | 1.74 | **fail** on 42 |
| **P9** high ÷ low | ≥ 1.5 | 2.01 | 1.68 | 1.30 | **fail** on 99 |
| **V1** | ≥ 1.2 | 1.22 | 1.28 | 1.14 | **fail** on 99 |
| **R1** | ≥ 1.4 | 1.69 | 1.34 | 1.37 | **fail** on 7 and 99 |
| **R2a** | ≥ 1.8 | 2.15 | 1.75 | 1.60 | **fail** on 7 and 99 |
| **R5** | ≥ 1.4 | 1.50 | 2.33 | 1.15 | **fail** on 99 |
| **P2c** (older) | ≤ 0.95 | 0.958 | 0.961 | 0.982 | **fail** every seed |
| **P3a** (older) | ≤ 0.92 | 0.920 | 0.940 | 0.943 | **fail** on 7 and 99 |
| R2b (accepted failure before) | ≤ 0.8 | 0.713 | 0.715 | 0.786 | pass |
| P6, P7, P10, P1a, P1b, P4a, R3, R4, F1–F5, C1–C3, P2b, P5a, K1 | as registered | | | | pass |
| R6 | reported | 0.94 | 0.92 | 0.99 | — (offer response no longer reads ε, as registered) |

**What changed the noise (diagnosed after the run; nothing changed for it).**

- **Before ADR 0045,** an impression effect's null changed only the
  impressions that effect touched (common random numbers).
- **Now** every sale is a purchased showing. So switching off P7 or P9
  changes orders, and with them stars, `popular` labels, stock, experiences
  and churn, and every later session. A planted ÷ null ratio now carries the
  divergence of two whole histories.
- **The spread across seeds** grew several-fold:
  - P9 high ÷ low read 1.57–1.66 before and 1.30–2.01 now;
  - P8 read 2.15–2.29 and now 1.38–1.94.
- The registered noise model no longer holds for the impression checks.
  Their misses are more likely noise than a weaker effect. That is not
  shown here, and they are reported as failures.

**What the run shows about O2 and O3.**

- **Placement:** an offer raises a product's recorded showings ×1.20 (O3a),
  not the ×1.3–1.5 expected. Sampling 6–14 products from an
  affinity-weighted pool spreads the ×1.3–1.8 factor thin.
- **Units:** units at a 20 %+ offer rise ×1.6 against the null, below the
  ADR's ≥ 1.8.
- **Order:** clicks fall with the slot at every position (O3b).

**What a fix would need**, decided by Antti and amended here before any re-run:
- **for the noise:** more seeds, or a pooled metric for the impression
  checks;
- **for O2 and O3:** a stronger placement factor, or one that reaches the
  candidate pool rather than only the draw from it.

**Rows (seed 42):**

| table | rows |
|:--|--:|
| impressions | 96,028 |
| contexts | 61,484 (54,760 visitors before a first order) |
| orders | 10,834 |
| order lines | 36,771 |
| reviews | 4,795 |
| nps_responses | 3,274 |
| customer_months | 27,003 |
| product_states, monthly_sales | 15,157 |

### The Shop sweep for shoppers without a pet profile

Registered above; it waits for `release2`. Its sessions exist: customers with no
`pets`, with an earlier order and a purchase in the session.

### Decision (2026-10-24, delegated by Antti, after the results above)

- **O2 and O3a are accepted as recorded failures,** with no generator change.
  - The ranker's placement works through drawing 6–14 products from an
    affinity-weighted pool, which dilutes its ×1.3–1.8 factor.
  - Measured: an offered product's showings ×1.20, and units at a 20 %+
    offer ×1.6, against the offers-off null.
  - The views quote these measured values, never the planted ones.
- **P2c and P3a are accepted as recorded failures.** Since ADR 0045 their
  mechanisms act through the shop's ranker (a rival's launch ×0.75 on being
  shown) and the showing's odds (a list-price rise through ε), not through
  order pick weights.
- **R6** stays reported, not judged.

### Amendment (2026-10-24, before the run it governs): pooled judging of the impression-side checks

**The reason is structural, not the results.** Since ADR 0045 every sale is a
purchased showing. A null that changes an impression effect therefore
propagates:
- through the orders it changes,
- into stars, `popular` labels, stock, experiences and churn,
- and so into every later session.

The per-seed noise model the checks were registered under (common random
numbers, a null touching only its own impressions) no longer holds.

**From now on these checks are judged by a pooled estimate:** P6, P6 high,
P7, P7 high, P8, P8 high, P9, P9 high, P10, V1, R1, R2a, R2b, R5, O2,
O3a, O3b.

- **Seeds:** 10 — the three registered (42, 7, 99) and seven new fixed
  seeds, listed now before any run: **1, 2, 3, 11, 13, 17, 23**.
- **Each seed's value** is computed exactly as registered (planted ÷ the
  check's null).
- **Ratio checks:**
  - the pooled point estimate is the geometric mean over the 10 seeds;
  - its 95 % interval is exp(mean log ± t₀.₉₇₅,₉ · sd(log) / √10), with
    t₀.₉₇₅,₉ = 2.262;
  - a "≥" check passes when the pooled estimate meets its threshold **and**
    the interval's lower bound is above the null's value, 1.0;
  - a "≤" check (R2b) passes when the estimate meets its threshold **and**
    the upper bound is below 1.0.
- **O3b** (a count of slots where clicks don't fall) is judged on the
  arithmetic mean over the seeds, against its threshold 0: every seed
  must read 0.
- **The thresholds are the registered ones.** The accepted failures above
  stay recorded and are judged again here; the decision stands whatever the
  pooled result.
- **The three-seed table stays in the record beside the pooled one**
  (`actionable-states-data.md`). The pooled run writes
  `actionable-states-pooled.md`.
- **Unchanged:** every other check keeps its per-seed judgement.

### Note on the pooled run (2026-10-24, before it was re-run)

The first attempt stopped. Two seeds of the seven new ones met cases the three
registered seeds never had; both are generator bugs, fixed without changing a
byte of seeds 42, 7 and 99.

- **Seed 13:** a household's diet rule left no dog wet food on sale that
  it could keep, and the staple choice asserted. Now that household has no
  such staple until one is on sale (and a switch with nothing else to keep
  the rule stays with the current staple). The same assert existed before
  ADR 0045.
- **Seed 23:** five litter products shared a name, and the litter variants
  listed only four. Two more variants were added, after the existing ones.

### Pooled results (2026-10-24; seeds 42, 7, 99, 1, 2, 3, 11, 13, 17, 23)

Full table, with every seed's value: `actionable-states-pooled.md`. **16 of 17
pooled checks pass.** The three-seed table above stays as recorded. The
pooled run's values for seeds 42, 7 and 99 equal it exactly, so the
two bug fixes left those seeds unchanged.

| # | threshold | pooled | 95 % interval | result |
|:--|:--|--:|:--|:--|
| P6 high ÷ low (high alone) | ≥ 1.5 (≥ 1.3) | 1.96 (2.25) | 1.81–2.12 (2.15–2.35) | pass |
| P7 high ÷ low (high alone) | ≥ 1.5 (≥ 1.3) | 2.73 (3.36) | 2.23–3.35 (3.05–3.70) | pass |
| P8 high ÷ low (high alone) | ≥ 1.5 (≥ 1.3) | 2.06 (1.86) | 1.74–2.43 (1.71–2.02) | pass |
| P9 high ÷ low (high alone) | ≥ 1.5 (≥ 1.3) | 1.65 (1.62) | 1.49–1.84 (1.50–1.75) | pass |
| P10 | ≥ 1.03 | 1.056 | 1.036–1.076 | pass |
| V1 | ≥ 1.2 | 1.25 | 1.20–1.30 | pass |
| R1 | ≥ 1.4 | 1.44 | 1.35–1.54 | pass |
| R2a | ≥ 1.8 | 1.86 | 1.64–2.10 | pass |
| R2b | ≤ 0.8 | 0.765 | 0.730–0.801 | pass |
| R5 | ≥ 1.4 | 1.54 | 1.34–1.77 | pass |
| **O2** | ≥ 1.8 | **1.61** | 1.57–1.65 | **fail** (accepted, as decided above) |
| O3a | ≥ 1.2 | 1.204 | 1.199–1.209 | pass (it missed two seeds by 0.001) |
| O3b | 0 | 0 | 0 on every seed | pass |

- **The one-seed misses were noise, as diagnosed.** P8, P9, V1, R1, R2a and
  R5 each pass pooled, with intervals above 1.
- **O2 is a precisely measured shortfall,** not noise: ×1.61, interval
  1.57–1.65, against ×1.8. The views quote ×1.6.
- **The rule's interval bars:** R1, R2a and R5 clear their thresholds only by
  their point estimates (their intervals reach below them); the rule asks
  only that intervals exclude 1.0.

## Amendment (2026-10-24, before either run): O4's procedure and the Shop sweep's details, fixed

`release2` is loaded (Aito 2.11.8, counts as `data/release-env.json`). The two
live items above leave details open. They are fixed here before any O4
estimate or sweep query was sent; only the local fixtures (row counts, value
ranges) were looked at.

### O4, the implied elasticity

- **Held-out month:** 2026-04, the last month with sales (`LATEST_MONTH`).
  Aito learns from the other months only, through a nested `from`:
  `{"from": "monthly_sales", "where": {"month": {"$lt": "2026-04"}}}`.
- **Products:** every product with a 2026-04 row (658).
- **Query, primary (A):** `_estimate units_sold`, `model: "regression"` (the
  Price view's model; k-NN isn't monotone in price, see the cheatsheet), with
  `where {product_sku, price_index}`: within product, so the slope is the
  price index's term with the product held fixed.
- **Two points per product:** `price_index` 1.00 (list price) and 0.83
  (17 % off, the middle of the offered rows' range).
- **A product's implied ε:** ln(U(0.83) ÷ U(1.00)) ÷ ln(0.83).
  - A product whose U(1.00) is under 1 unit is counted and reported, not
    used: on a near-zero base the ratio is noise.
  - A non-positive estimate at either point is counted and reported.
  - If either count exceeds 10 % of the products, O4 is reported as not
    measurable, not as a pass or fail.
- **O4's value:** the median implied ε over the products used. **Pass:** in
  [−2.5, −0.5], as registered.
- **Reported, not judged:**
  - **B:** the same with `discount_band` in `where` (`none` at 1.00,
    `15-20` at 0.83), if `_estimate` accepts the column;
  - **k-NN:** A without `model`;
  - **held-out accuracy:** A's mean absolute error on 2026-04 at each
    product's actual `price_index`, against the product's mean units over
    the training months.

### The Shop sweep for shoppers without a pet profile

- **The cart.** Since ADR 0045 a session's `basket` is its own order: in a
  local count of 2,000 eligible sessions, 1,889 hold a bought SKU in the
  basket. Cart words from the session would carry the answer, and leaving
  the cart's SKUs out of the candidates would make a hit impossible. So
  "Picked for you" is scored **on arrival, with an empty cart**: no cart
  words and no cart SKUs. (A deviation from "month, cart words", made
  before the run, flagged.)
- **The three `where`s,** each with `context.month` (the session's) and
  `just_bought: false`, and the diet rule's filter when the customer
  declared one:
  - **I:** `context.customer` (the session's customer);
  - **P:** `context.pets_from_orders` as `$and` of `$match` per pet type
    (the session's value), and `product_sku.pet_type: {"$or": those types}`
    as the candidate filter;
  - **I+P:** both.
- **Hold-out:** `from: {"from": "impressions", "where": {"$not": {"context":
  <session>}}}` for every query, as ADR 0033's sweep.
- **hit@12:** 1 when any product purchased in the session is among the
  `_recommend` top 12.
- **Brier:** over the session's shown products whose pet type is in the
  session's `pets_from_orders` and that the diet rule keeps, the **same set
  for every variant**, so the comparison is paired. Each variant's `$p`
  comes from the same `_recommend` restricted to that set
  (`product_sku: {"$or": set}`). A session with an empty set is left out of
  the Brier comparison and counted.
- **Paired 95 % intervals:** per-session differences, mean ± 1.96 · sd ÷ √n.
- **The decision rule, operationally:**
  1. eligible: the variants whose mean Brier is within 0.01 of the best;
  2. among them, the leader on mean hit@12;
  3. if the leader isn't P, P is eligible, and the leader − P hit@12
     interval includes 0, the Shop uses P;
  4. otherwise the leader. If I and I+P tie in step 2 with P not eligible,
     the Shop uses I (the simpler where).
- **Sample:** `random.Random(0).sample` of 1,400 from the eligible sessions
  sorted by `context_id` (2,333 in the seed-42 fixtures).

### O4, live (2026-10-24, env `release2`, Aito 2.11.8): blocked, not measured

The registered procedure can't run. `_estimate` refuses the nested `from`
that holds 2026-04 out, on both models:

```json
POST /_estimate
{"from": {"from": "monthly_sales", "where": {"month": {"$lt": "2026-04"}}},
 "where": {"product_sku": "SKU-PT-0203", "price_index": 1.0},
 "estimate": "units_sold", "model": "regression"}
```

→ 501 `"nested from (population restriction) is not supported with _estimate
yet"`.

- **O4 is reported as not measured,** neither a pass nor a fail.
- **No workaround was run:**
  - an in-sample estimate isn't a held-out month;
  - a training-only env would need a write to `shared.aito.ai`.
- **The ways forward, for Antti:**
  - Aito core supports a population on `_estimate`;
  - or a `release2-train` env without 2026-04 is loaded at night.
- **Seen in the shape probe** (plain `from`, one product, so not O4): with
  zero-sale months in the data, `price_index` is one linear term in units,
  the same slope for every product. SKU-PT-0203 reads 22.12 units at 1.00
  and 23.26 at 0.83, an arc ε of about −0.27 on its base of 22 units. A
  product's ε under this model is the shared slope over its own base, so the
  registered median ranges over the products' bases.
- `discount_band` is accepted in the plain form (variant B's shape).

### The no-profile Shop sweep, live (2026-10-24, env `release2`): stopped at 306 of 1,400

`scripts/no_profile_shop_sweep.py`, as amended above. **It hasn't concluded,
so its decision rule isn't applied.**

- **What stopped it:** three runs ended on a 502 Bad Gateway from
  `shared.aito.ai` for a `_batch`.
  - The first, at 90 items a batch, failed after about 8 batches of 45–52 s
    of Aito time each.
  - The next two, at 18 items a batch, each failed after exactly 153 more
    sessions (about 7–8 minutes).
  - A resume right after the second failure got a 502 on its first batch.
- **Each failing batch's queries answer 200 alone** and as a batch a minute
  later. So the cause isn't one query.
- **The likely cause, not shown:** every session's held-out `from` is a new
  population. A failure every ~150 sessions, with a 502 just after, looks
  like the engine filling and restarting on the shared instance. That
  instance also serves the demo.
- **Not retried in a loop,** and not run further. The run resumes from its
  checkpoint (`data/evidence/no-profile-shop-sweep.partial.jsonl`, kept,
  gitignored) once Antti or core says the instance can take it.
- **Interim, over the first 306 sampled sessions** (reported, not judged):

  | variant | hit@12 | Brier |
  |:--|--:|--:|
  | I | 0.585 | 0.2714 |
  | P | 0.500 | 0.2819 |
  | I+P | 0.706 | 0.2618 |

  Paired: P − I hit −0.085 [−0.153, −0.017]; I+P − P +0.206 [+0.146,
  +0.266]; I+P − I +0.121 [+0.082, +0.160]. Brier I+P − I −0.010
  [−0.013, −0.006].
