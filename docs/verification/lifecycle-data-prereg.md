# Pre-registration: purchase data with a lifecycle (ADR 0027)

Written 2026-09-30, **before** the generator was changed. Every threshold
below is fixed now. The new fixtures are loaded into the non-master env
`lifecycle` on the shared instance; the old data is master, read-only.

## 1. Data-level checks (offline, on the fixture files)

Computed by `tests/test_fixtures.py`, failing the suite if missed.

| # | check | pass when |
|:--|:--|:--|
| D1 | food lines that re-buy a food the customer bought before | ≥ 50 % (was 6.7 %) and ≤ 90 %, so switching remains |
| D2 | small-animal first orders | ≥ 60 % of their lines are starter items (cage, water bottle, food); ≤ 10 % of later lines are starter durables |
| D3 | customers who buy a second cage | ≤ 2 % of cage buyers (was 17 %) |
| D4 | a customer's orders | strictly time-ordered, with no two orders in the same month for ≥ 90 % of customers |
| D5 | price sensitivity in the generator | median fitted per-SKU elasticity of units on price/list within [−2, −1] |
| D6 | planted mispricings | ≥ 12 SKUs whose list price sits outside mean ± 1.5σ of their realised prices, each with n ≥ 12 |
| D7 | win-back response | staple-category sends respond at ≥ 2× the rate of never-bought-category sends |
| D8 | existing engineered signals | every current signal test passes; any range that moves is changed in the diff with its reason |

## 2. The ADR's main test: next basket (Aito, old vs new)

- **Customers:** 300 with ≥ 3 orders, `random.Random(0)` over sorted ids.
- **Task:** predict the products of each customer's **last** order from
  their earlier orders.
- **Method:** `_recommend product_sku` over `order_lines`, conditioned on the
  customer (`order_id.customer_id`), from a nested `from` that excludes the
  last order's lines (so it never sees the answer).
- **Hit:** any product of the last order is in the top 10.
- **Baseline:** the 10 products most bought by the customer's segment,
  from the same training rows.
- **Control:** the same query with another random customer's id (a shuffled
  history). It must fall to the popularity baseline (within its CI).
- **Pass (new data):** hit rate @10 beats popularity with a paired
  bootstrap 95 % CI above 0, and the shuffled control doesn't.
- **Expected on old data (master):** no clear gain. That's the ADR's claim
  that today's data carries no pattern. Reported whichever way it falls.

## 3. Per-view unhide criteria (Aito, on `lifecycle`)

As in ADR 0027, each run as it will run in `tests/test_aito_check.py`:

| view | criterion |
|:--|:--|
| Demand | time split: the model beats the naive "same range as last month" (paired CI above 0) |
| Price | ≥ 3 outliers with n ≥ 12; ≥ 1 band × category lift whose 95 % interval excludes 1; no outlier with n < 6 |
| Markdown | no proposal loses margin vs holding at list; units never fall as price falls; implied sensitivity at −20 % within [−3, −0.5] for ≥ 90 % of scored SKUs |
| Win-back | `_evaluate predict responded` with the page's evidence beats the base rate in log-loss by ≥ 0.01, on seeds 0 and 1; no displayed rate > 0.5 |
| Cart Completion | held-out next item: hit rate @3 beats popularity-within-pet (paired CI above 0); no suggestion > 2× the cart value |

A view whose criterion fails stays hidden and is reported as such. The
generator is **not** re-tuned against these Aito checks after seeing them.
If the generator changes, this file is amended first, with the reason.
