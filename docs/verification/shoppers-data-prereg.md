# Pre-registration: shoppers with a story (ADR 0030)

Written 2026-10-12, **before** the generator was changed for ADR 0030. It
builds on ADR 0027's lifecycle data (`lifecycle-data-prereg.md`, whose
checks D1–D8 still apply). Every threshold below is fixed now. The new
fixtures are loaded into a non-master env on the shared instance first;
master is not touched until these pass.

The generator is **not** re-tuned against the Aito checks after seeing
them. If it has to change, this file is amended first, with the reason.

## The planted effects

| # | Effect | How it is planted |
|:--|:--|:--|
| S1 | Diet rules | ~20 % of dog and cat households have one rule: grain-free, sensitive stomach, senior or puppy. Their food and treat lines only ever carry that dietary. Stored on `customers.diet_rule` and denormalised onto `order_lines` and `impressions`. |
| S2 | Guided kit | After the starter kit, add-ons are bought in a fixed order per pet type (small animal: hideout → exercise wheel → wooden chew → tunnel). Each order takes the **next** add-on with P 0.75, a random unowned one otherwise. |
| S3 | Routine | ADR 0027's staples, unchanged. |
| S4 | Seasons | Pick weight ×1.4 in November and ×2.0 in December for treats and toys; ×1.7 June–August for grooming and health. |
| S5 | Ratings matter | 15 % of products are poorly made. Their reviews skew to 1–2 stars, they are switched away from as staples at 0.30 instead of 0.07, and an impression of one converts at 0.5× the usual odds. `products.avg_rating` and `products.rating_band` come from the reviews. |
| S6 | Basket context | Each impression session carries the categories in the customer's basket that month (`impressions.basket_categories`, Text). A product that complements the basket converts at 2× the odds: an add-on of a kit item in the basket, or dental treats with dog dry food. |
| S7 | Real search queries | Search sessions use 2–3 word queries drawn from the shown products' own words ("grain free puppy food", "clumping cat litter", "hamster wheel"), not one category word. |

New columns are in the **initial schema** (ADR 0030: columns added in
place come back typed `Unknown`).

## 1. Data-level checks (offline, `tests/test_fixtures.py`)

| # | check | pass when |
|:--|:--|:--|
| S1a | food and treat lines of rule households that break the rule | 0 |
| S1b | dog and cat households with a rule | 15–25 % |
| S2a | small-animal owners whose 2nd add-on (by order) is the next in sequence | ≥ 60 % (uniform would give ≤ 34 %) |
| S4a | treats + toys share of December lines ÷ their share in March–October | ≥ 1.6 |
| S4b | grooming + health share of June–August lines ÷ share in October–April | ≥ 1.4 |
| S5a | staple re-buy rate of poorly made products ÷ that of the rest | ≤ 0.8 |
| S5b | impression purchase rate of poorly made products ÷ the rest | ≤ 0.7 |
| S6a | purchase rate of complement impressions ÷ non-complement, same surface | ≥ 1.6 |
| S7a | search queries with ≥ 2 words | ≥ 90 %; every query matches ≥ 3 products by name |
| D8 | existing engineered signals (dental lift, persona separation, …) | still pass; any range that moves is changed in the diff with its reason |

## 2. Aito checks (on the test env, then `tests/test_aito_check.py`)

| # | check | pass when |
|:--|:--|:--|
| A1 | `_recommend` on `impressions` for a grain-free dog household (`where` with `customer_diet_rule`), goal purchased, top 10 | ≥ 9 of 10 grain-free or not food/treats; the same query without the rule: ≤ 7 |
| A2 | next add-on for a small-animal owner who owns cage + water bottle + hideout | "Exercise Wheel" in the top 3 of `_predict` (query shape probed first, see below); popularity-within-pet baseline reported beside it |
| A3 | next basket (ADR 0027 §2, `scripts/next_basket_eval.py`) | hit @10 beats popularity, paired 95 % CI above 0; shuffled control does not |
| A4 | `_relate` on `monthly_sales`, `season: winter` → category | treats and toys lift with a 95 % interval above 1; `summer` → grooming the same |
| A5 | `_relate` on `impressions`, `purchased: true` → `product_sku.rating_band` | the lowest band's interval below 1 |
| A6 | Smart Search: the same query for one persona with two baskets (empty; with a cage) | top 5s differ, and an add-on ranks higher with the cage |
| A7 | Smart Search: "grain free" query for a grain-free persona vs a no-rule persona | top 5s differ; the grain-free persona's are all grain-free |

## 3. Query patterns to probe before use

Per CLAUDE.md, each is run on the test env, its response inspected, and
written into `docs/aito-cheatsheet.md` before a view uses it:

1. A customer's own history as the population (nested `from`), for
   "Your usual basket".
2. A per-item probability for each of a customer's staples (several
   independent `_predict`s, or one multi-label form if the engine has
   one), for the basket prefill.
3. `_recommend` / `_predict` with `basket_categories: {"$match": …}` as
   context, for A2 and A6.

Each result, pass or fail, is recorded below with the date and the env.

## Results

*(none yet)*
