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

## Amendment after an Aito result (2026-10-13, decided by Antti)

A1 failed because rule households browse food at random: 48 of their 640
dog dry-food impressions were grain-free. A real grain-free household
mostly looks at grain-free food, by search or filter. **This change is
made after seeing A1's result**, which the rule above says not to do;
Antti chose it (option 1 of two) over leaving A1 failed. A1 is re-run
once and reported whichever way it falls.

- **S1, browsing:** for a rule household, a food that keeps the rule is
  shown with 8× the weight and one that breaks it with 0.25×, in browse
  and in the products their searches start from.
- **New data check S1d:** at least 60 % of rule households' food
  impressions keep the rule.

## Amendment for the interactive shop (2026-10-13, before the reload)

Antti asked for an interactive shop and owner analytics on top of this
data (cart recommendations, a product page, autofill, "not what you
just bought"). Four columns and one new effect, so it all lands in one
reload. All in the initial schema.

| column | holds |
|:--|:--|
| `orders.skus` (Text) | the order's product SKUs |
| `orders.prev_skus` (Text) | the customer's previous order's SKUs |
| `orders.owned_before` (Text) | kit durables owned before this order (`small_animal_cage …`), for A2 |
| `impressions.basket_skus` (Text) | the SKUs in that month's basket, beside `basket_categories` |

**S8, recency, as first registered:** a staple restocked in the previous
order is restocked with P 0.45, one skipped with P 0.85. *Amended before
any Aito run:* in orders this fights ADR 0027's routine by construction
(fewer restocks means fewer re-buys; D1 fell to 43–47 % while S8a sat at
0.66–0.67 across three settings), and the ketchup case is about what to
**recommend**. So S8 moves to impressions: a product in the customer's
last order converts at 0.25× the odds in a later session, and the
impression carries that order's SKUs (`impressions.last_order_skus`,
Text). Orders keep ADR 0027's restocking unchanged.

| # | check | pass when |
|:--|:--|:--|
| S8a (data) | purchase rate of impressions whose product was in the last order ÷ that of products the same customer bought earlier but not in the last order (*amended before any Aito run: against "the rest" it was 0.79, because just-bought products are ones the customer likes; the control now holds that constant*). First generation with the control: 0.55 (8.2 % vs 14.8 %); the 0.25× odds then also apply to the click, as the complement odds do | ≤ 0.5 |
| A8 (Aito) | `_relate` on `impressions` with `purchased: true` and `last_order_skus` holding the shown product … (shape probed first); simpler form: `_relate` where `purchased: true`, related to a boolean `just_bought` | the just-bought lift's 95 % interval below 1 |
| A2 (Aito, now specified) | next add-on for owners of `small_animal_cage small_animal_water_bottle small_animal_hideout`: query shape probed first on the test env | an Exercise Wheel product in the top 3 |

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

### Aito checks, 2026-10-12, test env `shoppers` on shared (master untouched)

The env was cloned from master and reloaded with these fixtures (238,451
rows); the reloaded tables are on the v2 engine, and the new columns
have their declared types (`units_last_month` is `Int`, not `Unknown`).
All 23 earlier live checks pass on it.

| # | result | notes |
|:--|:--|:--|
| A4 | **pass**: December treats and toys, summer grooming, each interval above 1 (toys 2.65×, treats 1.89×, grooming 3.76×) | The registered shape, `_relate` on `monthly_sales`, failed (intervals 0.73–0.84 at the low end). It can't work: `monthly_sales` has one row per SKU and month whatever it sold, so a category's share of rows doesn't move with the season. Re-run over `order_lines` (`order_id.month` in the season), which counts purchases. The same flaw makes Demand's seasonality panel empty on any data. |
| A5 | **pass**: the 1–2 star band's interval is below 1 | |
| A1 | **fail, twice** | Run 1: `where` on `product_category` doesn't filter `_recommend` candidates (only `product_sku.*` does), so both queries returned health and toy products: a query error. Run 2 (`product_sku.category`): 0 of 10 grain-free. Cause: the generator kept the rule in orders but not in impression purchases (1,444 rule-breaking purchases), a bug against S1's registration, fixed and impressions reloaded. Run 3: 1 of 10. Rule households saw 640 dog dry-food impressions, only 48 grain-free, and bought 3: too few for Aito to learn from. Stopped here for a decision (CLAUDE.md: two failed attempts). |
| A2, A3, A6, A7 | not run | A2 needs a way to say what a customer owns before an order; A6 and A7 need the Smart Search changes. |

### Aito checks, 2026-10-13, test env `shoppers` reloaded with the interactive-shop columns

All 27 earlier and ADR 0030 live checks pass except A1 (run at 19:56 after
a first attempt at 10:01 was lost to this machine's DNS failures).

| # | result | notes |
|:--|:--|:--|
| A1, the agreed re-run after the browsing amendment | **fail**: 0 of 10 grain-free | Rule households bought only grain-free dog food (14 purchases, all grain-free), but 14 purchases is too little for `_recommend` to learn a rule from, so it ranks what dog owners buy in general (p ≈ 0.27). **Design lesson for the views:** a household's hard rule is a filter on the candidates (`product_sku.name` matching the rule's words), and Aito ranks within it. Reported as failed; not re-tuned. |
| A2 | **pass**: for owners of cage, water bottle and hideout, two Exercise Wheels top `_predict product_sku` on `order_lines` (p 0.25, 0.23), then tunnels | `where order_id.owned_before: {$and: [{$match: token}…]}` plus the pet and accessory/toy categories. |
| A4, A5 | **pass** again | |
| A8 | **pass**: `_relate` on `impressions` where `purchased`, related to `just_bought`: lift 0.48 on 40 of 12,135 purchases; 95 % interval about 0.36–0.66 | |
| A3 | pending on 2026-10-13: runs after 22:00, one query at a time. **Run on 2026-10-30, on release 3b: pass** (below) | Six parallel nested-`from` predictions (3.5 s each, ~36,000-row populations) drew a 502 from the shared instance at 19:57; prod stayed at 200. |
| A6, A7 | not run | need the Smart Search changes (ADR 0031) |

### Query-pattern probes (ADR 0031), 2026-10-13, `shoppers`

- **Same basket:** `_relate` on `orders` with `skus: {$match: SKU}`, related to `skus`, works on v2 (hits come back as `{"skus": {"$has": …}}`). It is thin at product level: SKU-PT-0177 is in 92 orders, and its partners appear 3–8 times each. Show counts and filter by interval.
- **Nested `from` with `_relate`: unsupported on 2.11.4** (501, "nested from (population restriction) is not supported with relate yet"). "In your baskets" is therefore a `_search` of the shopper's own orders: history, not inference.
- **Autofill:** `_predict` with `predict: "skus.$feature"` from a nested `from` of the shopper's orders works and returns one probability per SKU. The plain `predict: "skus"` returns whole SKU lists, each p = 0.1, which is useless for autofill.

### A3, run on release 3b (2026-10-30)

**Data:** release 3b as promoted on 2026-10-29, read as `v2@master` on shared.aito.ai (36,357 order lines, 3,000 customers). This is not the `shoppers` data this prereg was written for (2026-10-13): the generator and the data have changed since, so this is A3's question asked of the data the demo serves today.
**Run:** `PYTHONPATH=. python scripts/next_basket_eval.py`, read-only, one query at a time, 300 customers with at least 3 orders (seed 0), hit@10.

**The method changed before this run, and the change is visible here on purpose.** Until 2026-10-30 the model's population excluded only the sampled customer's own last order, while the popularity baseline excluded all 300 sampled last orders, so the model could read 299 other held-out baskets and the baseline none. The script now excludes every sampled customer's last order from the model's population as well. Before changing it the asymmetry was measured on 3b: 0.853 as it was, 0.857 symmetric, flattery −0.003 [−0.010, +0.000], so the change moves no number in the model's favour or against it. The script also now scores a household that declared no pets as its own group ("no declared pets"); on 3b it crashed on them (`KeyError: 'pets'`, `customers.pets` is nullable). It is still a leave-last-basket-out split, not a month-boundary split; a month split measured earlier on other data was indistinguishable (+0.600 vs +0.603, dev3, 2026-10-20).

| arm | hit@10 |
|:--|--:|
| model: `_predict product_sku` conditioned on the customer | 0.857 |
| popularity: the household group's 10 most bought products | 0.217 |
| control: conditioned on another random customer | 0.067 |

| comparison | difference | paired 95 % interval |
|:--|--:|:--|
| model − popularity | +0.640 | [+0.587, +0.693] |
| control − popularity | −0.150 | [−0.203, −0.100] |

**A3: pass.** The model beats popularity with the interval above 0, and the shuffled control does not. Script: `scripts/next_basket_eval.py`, test: `tests/test_next_basket_eval.py`.
