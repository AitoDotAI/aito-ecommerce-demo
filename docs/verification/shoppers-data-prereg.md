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

## Amendments (2026-10-12, while writing the data tests, before any generation)

- **S1 covers food only** (dry and wet food), not treats. The catalogue
  has no sensitive or senior treats, so a treat rule could not be kept.
  `puppy` goes only to dog-only households (there is no puppy cat food).
  S1a reads "food lines of rule households that break the rule: 0".
- **S2's sequence is durables only**: small animal hideout → exercise
  wheel → tunnel. A wooden chew is consumable and re-bought, so it can't
  mark a step. With three steps a uniform pick of the second already gives
  50 %, so S2a's bar becomes **≥ 70 %**.
- **S4 adds a gift line**: staples fill most lines, so a pick-weight
  factor alone barely moves the December share. In December an order adds
  one treat or toy with P 0.35; in November with P 0.15. The thresholds
  are unchanged.
- **S5 and S6 odds apply at two funnel steps**, add-to-cart and purchase,
  not purchase alone: for an item that already converts well, doubling
  only the last step's odds moves its overall rate by far less than 2×.
  The thresholds are unchanged.

## Amendments after the first generation (2026-10-12, data checks only, before any Aito run)

The first generation passed S1a, S1b, S4a, S5a and S7a and missed five.
None of these are Aito checks, so strengthening a plant to meet its
pre-registered data threshold is building the effect, not tuning to a
result. **Thresholds are unchanged.**

| check | first generation | cause | change |
|:--|:--|:--|:--|
| S2a | 66 % (40/61) | random basket draws also pick add-on types out of order | next add-on P 0.75 → 0.90 |
| S4b | 1.27 | staples dilute a ×1.7 pick weight | a summer care line (grooming or health) with P 0.25 in June–August, like the December gift line |
| S5b | 0.73 | ×0.5 odds at two steps | ×0.35 odds |
| S5c | a band "2" | `round(2.5)` is 2 in Python | bug fix: bands by threshold (< 2.5, < 3.5, < 4.5) |
| S6a | 1.19 on search (14.8 % vs 12.4 %) | complements already convert near the ceiling after the click; the click is the real gate | a complement also doubles the click odds |
| S6a, second generation | 1.54 on search (18.6 % vs 12.1 %); all other checks pass | the comparison group holds the customer's best-fitting items | complement odds ×2 → ×3 at each step |
| D7 (ADR 0027) | 1.88× against all non-staple sends | the test compared against every non-staple send; D7 is registered against never-bought sends (5.1×) | test fixed to the registered definition |
| D8 persona Saara | churned | her last order month was a random draw; the shifted RNG moved it | a persona's history reaches the latest month by rule |
| D5 (ADR 0027) | −0.91 | gift, care and diet-substitute picks ignored promotions | they are weighted by this month's promotions, like every basket draw |
| S2a, S5a after that | 69.8 % (37/53); 0.82 | both were seed-sensitive, so too weak | a random out-of-order add-on is skipped with P 0.8; poor staple switch 0.30 → 0.50 |

Also before any Aito run: someone leaving a poorly made staple moves to one
that isn't (S5), which keeps D1 where it was before ADR 0030 (50.8 %).

## Results

### Data checks, 2026-10-12 (seed 42, the committed fixtures)

All ten S checks pass, and the full offline suite (213 tests) with them.

| check | value | bar |
|:--|:--|:--|
| S1a / S1b | 0 rule-breaking food lines; rule share in range | 0; 15–25 % |
| S2a | ≥ 70 % | ≥ 70 % |
| S4a / S4b | pass | ≥ 1.6 / ≥ 1.4 |
| S5a / S5b / S5c | pass | ≤ 0.8 / ≤ 0.7 / bands valid |
| S6a | pass on every surface with ≥ 200 complement impressions | ≥ 1.6 |
| S7a | pass | ≥ 90 % multi-word, ≥ 3 matches each |
| D1 (ADR 0027) | 50.8 % (unchanged from before ADR 0030) | ≥ 50 % |
| D5 (ADR 0027) | −1.31 | [−2, −1] |

### Seed robustness (seeds 7 and 99, not committed)

All ten S checks pass on both seeds. Three older checks are seed-sensitive
and are reported, not tuned:

- **D6** (planted mispricings) fails on seeds 7 and 99 **before** ADR 0030
  too: an ADR 0027 margin.
- **D1** sits on its floor by design (50.8 % on seeds 42 and 99 before ADR
  0030); with ADR 0030 it is 49.9 % on seed 99.
- **Signal 3** (Maija and Olli's top-5 pairs) fails on seed 7 because Maija
  buys only 4 distinct pairs there; the test assumes 5.

### Aito checks

*(not run yet: the next step is loading these fixtures into a non-master env)*
