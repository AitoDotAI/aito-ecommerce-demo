# Analytics audit B: Acquisition, Pattern Explorer, Basket Rules, Product Insights

Repo: /home/arau/episto/src/aito-ecommerce-demo (read-only audit; no Aito host was called). Aito docs: /home/arau/episto/src/aito-core.

## Routing facts (what the "views" really are)

- `/acquisition` is live: `frontend/app/acquisition/page.tsx` -> `GET /api/acquisition` (`src/app.py:688`) -> `src/acquisition_service.py:get_acquisition` (122). Live Aito queries, 6 h in-memory cache (`src/analytics_sections.py:24,27`). No stored snapshot.
- `/pattern-explorer` and `/basket-rules` are stubs that forward to `/patterns/` (`frontend/lib/moved-routes.ts`, ADR 0041). Pattern Explorer's anchor is Patterns' "Baskets" anchor filter. Basket Rules' confidence and support are Baskets columns. Page: `frontend/app/patterns/page.tsx`, `frontend/components/patterns/BasketRules.tsx`, `lead-sentences.ts`. API: `/api/shop-analytics/{funnel,who,baskets,search-words}` (`src/app.py:675-715`). All live Aito with the same 6 h cache. No precomputed file.
- `/product-insights` is a stub that forwards to `/product/` (`moved-routes.ts`). Page: `frontend/app/product/page.tsx` plus `frontend/components/product/*`. API: `/api/product`, `/api/product/{kpi,funnel,pricing,price-what-if,price-curve}` (`src/app.py:551-650`). Live Aito, 30 min cache for `/api/product`. No precomputed file. `data/precomputed/` holds only demand, overview, retention and supply for v2-master and v2-shoppers; none of the four views reads it.
- Global caveat: every row Aito holds comes from `data/generate_fixtures.py` and its helpers (planted effects, e.g. `data/acquisition.py` `STAY_FACTOR`, `regular_probability`). Below, "(a)" means the displayed number is the answer of an Aito query over those rows; "(c)" means a stored or constant value that is not computed from rows at view time.

## Aito capability references (cited in the tables)

- [SQL-GBY] `aito-core/docs/sql-support.md:72-88` (`count(*)`, `count(DISTINCT)`, `sum`, `avg`, `min`, `max`, `GROUP BY`, `HAVING`), `:162-187` (single-column GROUP BY, HAVING, ORDER BY aggregate, LIMIT), `:189-202` (multi-column GROUP BY; single-column is preferred), `:299-317` (aggregate expressions such as `sum(x)/count(*)` over one WHERE; not with GROUP BY/HAVING), `:443-447` (`/api/v2/_sql` is a read endpoint).
  - Gap: no stddev, variance, percentile or median in the dialect (grep of `sql-support.md` found none).
  - Whether this demo's Aito instance serves `_sql`: unverified.
- [AGG] `aito-core/api-docs/coreapi.yaml:1448-1456` (v2 `_aggregate`: grouped `$sum/$mean/$count`). Demo cheatsheet `docs/aito-cheatsheet.md:948-1012`: `$mean` also returns `samples`, `variance`, `standardDeviation` and `standardError`. v1 `_aggregate` is documented there as `$mean/$min/$max`. `_aggregate` is not allowed inside `_batch` (cheatsheet:1039).
- [RELATE] `coreapi.yaml:3293-3325`: `_relate` returns `related, condition, lift, ps, fs` only. `ps.pOnCondition / ps.p = lift` (`api-docs/content/operations/post-api-v1-relate.js:37`). The demo already reads `ps.pOnCondition` (`src/demand_service.py:175`). No interval, p-value or design-effect field is documented. The only Wilson/bootstrap code in aito-core is inside docs generators (`api-docs/src/generator/gen-eval-metrics.js:29-37,948`), i.e. Aito's own docs compute intervals app-side too. So an interval on a `_relate` lift or a count share needs an engine feature.
- [RELATE-NEST] `docs/aito-cheatsheet.md:584-606`: `_relate` answers 501 to a nested `from`, so a sub-population baseline cannot be set. `:685-710`: `_relate` cannot relate a numeric band (reported to core as td-20261003142449808722).
- [ORDERBY] `coreapi.yaml:3347,5048`: `orderBy {"$desc": {"$multiply": ["product.price","$p"]}}` exists. Arithmetic inside it is limited to documented forms; `price - cost` inside it is unverified.
- [EST] `docs/aito-cheatsheet.md:845-945`: `_estimate` returns a point estimate (`why` for regression). No interval is documented. `_evaluate` metrics: `coreapi.yaml:1534`; CI on them is unverified.

---

## 1. Acquisition (`/acquisition`)

First screen = lead sentence + 6-row source table; the "first basket" card sits just below.

| Number as shown | Where | Origin | Basis | If (b): Aito today? | Visibility |
|---|---|---|---|---|---|
| "n of N sessions" under Converts (N = landing + first-order sessions) | `src/acquisition_service.py:86-98` (queries), `:106` (sum) | a (two `_search limit:0` counts, one add in app) | `contexts where {source, surface:"landing"}` and `where {source, first_order:true}`, `total` | n/a. SQL `GROUP BY source` would do all 6 sources in one query [SQL-GBY] | high |
| Converts % bar | `acquisition_service.py:43-45,117` (`Rate.share`), `page.tsx:92` | b | first_orders / sessions | Counts yes, one `count(*) ... GROUP BY source`. The ratio is one division; `sum(x)/count(*)` works over one WHERE only [SQL-GBY :299-317]. A share per group via GROUP BY: unverified | high |
| Converts 95 % whisker "a-b %" | `acquisition_service.py:47-54` (`wilson`), Z95 at `:35` | b | Wilson score interval from successes and total | No. Needs an engine feature: interval on a proportion (count + n) or on `_relate`/`_aggregate` output. None documented [RELATE][AGG] | high |
| "n of N customers" under Becomes regular | `acquisition_service.py:88-97` | a | `customers where {first_source, became_regular:{$exists:true}}` and `{..., became_regular:true}`, `total` | n/a. SQL `GROUP BY first_source` works [SQL-GBY] | high |
| Becomes regular % bar and whisker | `acquisition_service.py:117` (`wilson`) | b | regular / labelled, Wilson | Share: as for Converts. Interval: needs an engine feature | high |
| Predicted to stay % | `acquisition_service.py:94-95,108,119` | a | `_predict became_regular where {first_source}` `$p` of the `true` hit | n/a | high |
| "source x1.23" under Predicted | `acquisition_service.py:109-113,119` | a | `$why` `relatedPropositionLift` for `{first_source}` | n/a | high |
| Visitors land on "category xN.N" (top 3) | `acquisition_service.py:100-103,114-115,119` | a for the lift (`_relate contexts where {source} relate landing_category`). b for the filter lift > 1.2 and top-3 cut. The 1.2 threshold is a hand constant (c) | `h["lift"] > 1.2`, first 3 | Lift yes. Ordering by lift: `_relate` has `orderBy` (`coreapi.yaml:3319-3323`). A threshold in the query: unverified. No interval is shown here | high |
| Lead sentence ("X converts best, at p %... only q % become regular") | `frontend/app/acquisition/page.tsx:119-136` | b (TSX) | sort by conversion, median, `regular.high < bestStay/2`, reuses the row shares | Needs a ranking over the two per-source shares plus a rule on an interval. Not available as one query; the interval is the missing feature | high |
| First-basket rows: "label = value, n of N regulars" | `acquisition_service.py:132-137` | a | `_relate customers where {became_regular:true} relate first_basket_categories`, `fs.fOnCondition / fCondition` | n/a | medium |
| First-basket lift xN.NN | same | a | `_relate` `lift` | n/a | medium |
| First-basket interval "lo-hi" | `src/lift_rows.py:89-100` (`_row`), `src/price_bands.py:32-49` (`lift_interval`) | b | relative-risk SE from `fs` counts, Bonferroni z, design effect fixed at 1.0 (hand constant, `acquisition_service.py:137`) | No. Needs an engine feature: lift interval or p-value on `_relate` hits [RELATE] | medium |
| Threshold line "N lifts tested, z=1.96..." | `lift_rows.py:71-87` (`bonferroni_z`, `judge`), `page.tsx:76` hard-codes `z: 1.96` and `tested = rows.length` | b | `tested` is set to the number of SHOWN rows, not the number tested. Possible display bug, unclear without a run. The 1.96 is a constant (c) | No (needs the interval feature) | medium |
| "queries sent" (panel) | `acquisition_service.py:138` | b | `len(queries)+len(SOURCES)+1` | n/a (meta) | low |

## 2. Pattern Explorer + 3. Basket Rules (both = `/patterns/`)

First screen: "What goes with purchases" and "Who buys what" cards (side by side on wide screens). Baskets table is full width below. Search words is below that.

### 2a. "What goes with purchases/clicks" card (default kpi=purchased)

| Number as shown | Where | Origin | Basis | If (b): Aito today? | Visibility |
|---|---|---|---|---|---|
| Lift "N.NN x" per row | `src/shop_analytics_service.py:96-99,108-138`, `lift_rows.py:119-121` | a | `_relate impressions where {purchased:true, context.customer:{$exists:true}} relate <field>`, 11 fields (`:45-54`), `hit.lift` | n/a | high |
| "x of y purchases" | `shop_analytics_service.py:130-131`, `lift_rows.py:98` | a | `fs.fOnCondition / fs.fCondition` | n/a | high |
| Interval "lo-hi" | `lift_rows.py:89-100`, `price_bands.py:32-49`, design effect from `design_effect.py:62-86` | b | `exp(ln(lift) +/- z*SE)`, SE from the four `fs` counts divided by the design effect, Bonferroni z | No. Needs an engine feature: lift interval, ideally cluster-aware (by customer). Not documented [RELATE] | high |
| Design effect "(design effect 1.x)" | `design_effect.py:62-86`; inputs `shop_analytics_service.py:113-128` (2 `_relate` on `context.customer`, limit 10 000, plus one `_search` count) | b over a (per-customer row counts via `_relate`; Kish/ANOVA arithmetic in Python) | one-way ANOVA rho, `1+(m-1)rho` | Per-customer counts: yes, `GROUP BY customer` with `count(*)` and `HAVING` [SQL-GBY :162-187] (single column, and the customer is a link path: link-path GROUP BY unverified). The ANOVA/rho step: no stddev/variance in the SQL dialect; `_aggregate $mean` returns variance [AGG] but not a clustered one. Needs an engine feature: cluster-robust interval or design effect | medium |
| Threshold "N lifts had >= 30 independent rows... z = 2.xx" | `lift_rows.py:77-87`, `LiftParts.tsx:103-113` | b | count of candidates with `fOnCondition/deff >= 30` (`MIN_SWEET_SPOT_SUPPORT`, constant 30 at `price_bands.py:27`), Bonferroni inverse-normal | No (follows from the interval feature) | medium |
| "No clear effect: fields" | `lift_rows.py:124-126` | b | fields with no row after judging | No (same) | medium |
| Lead sentence ("Products on offer get 1.xx [lo-hi] their share...") | `frontend/components/patterns/lead-sentences.ts:27-37` | b (TSX) | picks a row by field/value rule; shows its lift and interval | No (selection rule is UI copy; the numbers come from the rows) | high |

### 2b. "Who buys what, and when" card (default who=summer)

| Number as shown | Where | Origin | Basis | If (b): Aito today? | Visibility |
|---|---|---|---|---|---|
| Lift, "x of y order lines" | `shop_analytics_service.py:148-155` | a | `_relate order_lines where {order_id.month:{$or:[...]}} relate product_sku.category / .dietary` (for pets/diet groups `order_id.customer_id.pets` / `.diet`) | n/a | high |
| Interval, design effect, threshold, lead | as 2a (design effect via `order_id.customer_id`) | b | as 2a | as 2a | high |
| Season to months mapping | `src/demand_service.py:season_months`, `shop_analytics_service.py:62,78` | c | hand-written season sets | n/a | low |

### 2c. Baskets table (Basket Rules' confidence and support, Pattern Explorer's anchor)

| Number as shown | Where | Origin | Basis | If (b): Aito today? | Visibility |
|---|---|---|---|---|---|
| Lift "N.NN x" | `src/basket_pairs.py:115-117,120-133` | a | `_relate orders where {line_categories:{$match:A}} relate line_categories` (10 anchors) | n/a | medium |
| Interval | `basket_pairs.py:174` -> `lift_rows.py:89` | b | as 2a, design effect per anchor (`:149-172`) | No: needs an interval feature | medium |
| "N orders with both" | `basket_pairs.py:137-141` | a | `fs.fOnCondition` | n/a | medium |
| A -> B confidence % | `basket_pairs.py:142` | b | `fOnCondition / fCondition` | Partly. `_relate` returns `ps` (`ps.pOnCondition`), which may equal this confidence; whether it is the raw or the smoothed share is unverified [RELATE]. The two counts come from `_search limit:0` or SQL `count(*)` [SQL-GBY]. A conditional ratio in one SQL expression is not documented (aggregate expressions only over one WHERE, `sql-support.md:299-317`) | medium |
| B -> A confidence % | `basket_pairs.py:142` (swapped in `BasketRules.tsx:10-15`) | b | `fOnCondition / f` | as above (the reverse direction needs a `_relate` anchored on B, or the counts) | medium |
| Support % | `basket_pairs.py:143` | b | `fOnCondition / n` | Count yes; the share is a division. SQL `count(*)` with a filter over `count(*)` total: two queries, or an expression if documented: unverified | medium |
| "N pairs clear the bar", "+N more" | `BasketRules.tsx:50,77-78` | b (TSX) | length of the filtered array | n/a (UI) | low |
| Lead ("...had none": orders_with_first - both of first) | `lead-sentences.ts:50-57` | b (TSX) | subtraction of two `fs` counts | Counts yes; difference trivial | medium |
| Design-effect range "1.x-1.y by anchor", threshold | `BasketRules.tsx:79-80`, `lift_rows.py:81` | b | as 2a | as 2a | low |

### 2d. Search words card

| Number as shown | Where | Origin | Basis | If (b): Aito today? | Visibility |
|---|---|---|---|---|---|
| Word lift | `src/search_words.py:160` | b | `(purchases/search_purchases)/(impressions/search_impressions)`, two `_relate`s divided | Needs an engine feature: `_relate` against a sub-population baseline (a nested `from` answers 501, cheatsheet:584-606) | low |
| "x purchases of y (z %)" | `search_words.py:97-104,135-149` | a for counts (`_relate` hits, `fOnCondition`). b for z % (`SearchWordList`, `patterns/page.tsx:153`) | `_relate impressions where {surface:search[,purchased:true]} relate context.search_query` | counts: n/a. Share: division | low |
| Average search "p % of N impressions bought" | `search_words.py:143-151`; `patterns/page.tsx:148,158` | a (`fCondition` of the two relates), b for the ratio | purchases / impressions | Counts yes, division trivial | low |
| Interval | `search_words.py:164`, `lift_rows.py:89` | b | as 2a, design effect from `search_words.py:148-149` | No: needs an interval feature | low |
| "~N expected" (never bought) | `search_words.py:158` | b | `impressions * average` | Arithmetic over two Aito counts; not a query feature | low |
| Phrase merging, "N words and phrases in all" | `search_words.py:107-132,169` | b over a (`_search` count checks) | identical-count grouping in Python | Unclear (GROUP BY on a Text token is unverified) | low |

## 4. Product Insights (= `/product/`)

First screen: picker, hero facts, left property editor, and the right Funnel tab (default `kpi=funnel`). Offer & margin, Clicks and Purchases are other tabs. What if, History and For whom are the tabs below the workbench (default What if).

### 4a. Hero

| Number as shown | Where | Origin | Basis | If (b): Aito today? | Visibility |
|---|---|---|---|---|---|
| List price | `src/product_service.py:120` (`products.json` price) | c (catalogue fixture) | `data/products.json` | n/a | high |
| Cost (unit cost) | `product_service.py:142-146` | c | `inventory.unit_cost_eur`, a generator ratio of retail price (`data/generate_fixtures.py:2844`) | n/a | high |
| Stars band, reviews in month | `src/product_history.py:136-161` | c for the stored `rating_band`. b for the review count: `Counter` over fetched `reviews` rows (`:151,159`) | `product_states.rating_band`; reviews rows counted in Python | Review count: yes. `count(*) GROUP BY created_at` on `reviews where product_sku` [SQL-GBY :162-187] | high |
| "Sold in month: N units" | `product_history.py:146-150` | c | stored `monthly_sales.units_sold`, materialised by the generator (`generate_fixtures.py:2701`); not an Aito aggregate | Aito could derive it: `sum(qty) ... GROUP BY month` on `order_lines` [SQL-GBY] if month is reachable by a link: unverified | high |

### 4b. Funnel tab (right side, default)

| Number as shown | Where | Origin | Basis | If (b): Aito today? | Visibility |
|---|---|---|---|---|---|
| Impressions (estimated) | `src/product_funnel.py:279-284` | b over a | `mean_showings` (Python mean of `monthly_sales.showings`, `:133-134`) x `_estimate showings_index` (regression, `:108-111,278`) | Estimate: yes (a). The mean over history: `avg(showings)` [SQL-GBY] or `_aggregate $mean` [AGG]. The product is app-side glue | high |
| Clicks, click-through % | `product_funnel.py:288-292` | b over a | `_carry(_predict clicked $p, ranked_ctr, own_ctr)`; the odds-ratio rescale is in Python (`:266-272`) | The `$p` is a; the rescale from the ranked-showings level to the product's own is app arithmetic. Needs an engine feature: train on all showings (ranked and unranked) or condition on the surface, so no carry-over is needed. Unverified | high |
| Purchases, "% of clicks" | `product_funnel.py:289-295` | b over a | `_predict purchased where {..., clicked:true}` `$p` (`:306-313`), carried, x clicks | as above | high |
| "n x units each" blocks, units total | `product_funnel.py:296-297`, shares from `:225-251` (`order_lines` counts by qty) | b over a | counts via `_batch` `limit:0`, then shares and `sum(q*share)` in Python | Counts: yes, `count(*) GROUP BY qty` [SQL-GBY]. Arithmetic: app-side | high |
| "re-ordered without a showing" (other_units) | `product_funnel.py:236-248` | b | `units - purchased*mean_qty`, over months | Arithmetic over Aito counts; no query feature | medium |
| Price paid, Revenue | `product_funnel.py:294,301` | b over c | units x price; the price from the state (`_offer_pct`, `BAND_DISCOUNT_PCT` hand constants, `src/product_decision.py:19-20`) | App-side; no direct feature | high |
| Gross profit, Profit headline | `product_funnel.py:298-302` | b over c | `units*(price-cost)` minus ad spend. `AD_SPEND_EUR` = 0/60/180 is a hand constant (`:34`, shown as "assumed") | Partly: `$multiply` with `$p` in `orderBy` exists [ORDERBY], but a profit that combines two estimates and a constant is not documented. Unverified | high |
| "actual N" marks (impressions, clicks, purchases, units, money) | `product_funnel.py:170-184` | a for the counts (`_search limit:0` on impressions and `unranked_showings`). b for the money (`units*price`) | `{product_state: id, [clicked|purchased]:true}` | Counts yes (a); money is a product of count and constant | high |
| "Showings estimated from N earlier months" | `product_funnel.py:135` | b | `len(earlier)` | trivial | low |
| Cross-check "units by price give X" + 25 % gap | `product_funnel.py:149-156`; `CHECK_GAP` at `:36` | b over a | `_estimate units_index` at the price x mean units, gap in Python | App-side; no direct feature | low |

### 4c. Offer & margin tab (OfferDecision) and What if tab (DiscountWhatIf)

| Number as shown | Where | Origin | Basis | If (b): Aito today? | Visibility |
|---|---|---|---|---|---|
| "Bought when shown" % per band | `src/discount_what_if.py:79-82,103-136` | a | `_predict purchased where {product_sku, product_state.discount_band}` `$p` | n/a | medium |
| `$why` chain (base p, product lift, band lift, normaliser) | `discount_what_if.py:112-136` | a | `$why` factors | n/a | medium |
| "x1.xx vs no discount" | `discount_what_if.py:94` | b | `p_band / p_none` | Two `_predict`s divided; no ratio feature documented. `_predict` with `$why` lift of the band gives most of it (a) | medium |
| "shown N, bought M" per band | `discount_what_if.py:79-97` | a | `impressions` counts with and without `purchased` | n/a | medium |
| Margin per 100 showings | `src/product_decision.py:86-93` | b | `100 * p * (price - cost)`, price = list x (1 - BAND_DISCOUNT_PCT[band]) | Partly. `orderBy {"$multiply":[col,"$p"]}` is documented [ORDERBY]; `price-cost` inside it is unverified. The typical discount per band is a hand constant (c, `:19-20`; the comment says the medians are within 0.2 points) | medium |
| Advised band / headline | `product_decision.py:53-83` | b | `argmax` of margin | as above | medium |
| "Sales needed to break even xN.NN" | `product_decision.py:72-76`; also recomputed in `OfferDecision.tsx:63` | b | `(list-cost)/(price-cost)` | App-side; arithmetic on constants and cost | medium |
| "Expected x" | `product_decision.py:81` | b | `p_best / p_none` | as above | medium |
| "% change in margin" | `OfferDecision.tsx:61` | b (TSX) | ratio of two margins | app-side | medium |
| Next month units / profit (price model) | `src/price_what_if.py:61-103` | b over a | `_estimate units_sold` (regression); revenue = `price*units`, profit = `(price-cost)*units` | Estimate: yes (a). Margin: app arithmetic | medium |
| Factor waterfall (base + factors) | `price_what_if.py:106-155` | a (regression `why` terms) | folded and sorted in Python; checks that the chain multiplies out | n/a | low |
| "units per EUR" slope | `ProductWhatIf.tsx:40`, `OfferDecision.tsx:64` | b (TSX) | `(units_hi - units_lo)/(price_hi - price_lo)` over curve ends | No regression-slope output documented: unverified | low |

### 4d. Clicks / Purchases tabs (KpiPanel)

| Number as shown | Where | Origin | Basis | If (b): Aito today? | Visibility |
|---|---|---|---|---|---|
| "N %" shoppers shown a product like this click/buy | `src/product_kpi.py:128-157,160-193` | a | `_predict clicked|purchased where {product props}` `$p` | n/a | medium |
| Per-property lifts, base rate, normaliser | `product_kpi.py:160-193` | a | `$why` | n/a | medium |
| "x of y showings" (this product), similar products shown/clicked | `product_kpi.py:143-148` | a | `_search limit:0` counts | n/a | medium |
| "+N %" with changes | `KpiPanel.tsx:67` | b (TSX) | `p/before.p - 1` | trivial | medium |

### 4e. Pricing tab

| Number as shown | Where | Origin | Basis | If (b): Aito today? | Visibility |
|---|---|---|---|---|---|
| Units, profit, revenue per list price | `src/product_pricing.py:141-152` | b over a | `_estimate units_index` x `mean_units` (Python mean of `monthly_sales`, `:98-99`); profit = `units*(price-cost)` | Estimate: a. Mean: `avg`/`$mean` [SQL-GBY][AGG] | low |
| Best price, in-range flag | `product_pricing.py:120-121,152` | b | argmax over curve, range from min/max of own `price_index` | `min`/`max` exist [SQL-GBY]; argmax of profit is app-side | low |
| Tried range, own months table | `product_pricing.py:100-102,123-124` | c for stored `price_index`/`units_index` (generator-backfilled, `generate_fixtures.py:2861-2890`) | rows from `monthly_sales` | n/a | low |
| Seven-price curve (price-curve endpoint) | `src/price_curve.py:63-126` | b over a | `_estimate units_sold` x 7, profit in Python; mean of own prices in Python | as above | low |

### 4f. History tab and For whom tab

| Number as shown | Where | Origin | Basis | If (b): Aito today? | Visibility |
|---|---|---|---|---|---|
| Funnel counts (impressions, clicked, cart, purchased) | `src/product_history.py:81-97,99-118` | a | four `_search limit:0` counts | n/a | low |
| Surface bars and % | `product_history.py:84-92`, `ProductHistory.tsx:74` | a for counts; b (TSX) for the percentages | counts per surface, with and without `purchased` | `count(*) GROUP BY context.surface` as one query [SQL-GBY] (link-path group column: unverified) | low |
| Rating bars, sentiment bars | `product_history.py:128-134,111-116` | b | `Counter` over fetched `reviews` rows | Yes: `count(*) GROUP BY rating` [SQL-GBY :162-187] | low |
| Months chart: units, price, stars, flags | `product_history.py:136-161` | c (stored rows) joined in Python | `product_states` + `monthly_sales` rows | n/a | low |
| Buyer lifts "N.NN x", "n of m lines" | `src/product_buyers.py:66-96` | a | `_relate order_lines where {product_sku} relate order_id.customer_id.{pets,dog_size,diet,region}`; `fs` counts | n/a | low |
| Clear/grey split (>= 10 lines, |lift-1| > 0.15) | `product_buyers.py:50-56,40-44` | b | hand thresholds (constants, c) | threshold on a lift: unverified; no interval is computed for these (the module states so, `:8-9`) | low |
| "See it as this shopper" link | `product_buyers.py:98-111` | b | sum of log-lifts over matched profile values | App-side; no direct feature | low |

---

## Top (b) items by visibility (high first)

1. Intervals on every lift (Patterns funnel and who cards, Acquisition first-basket, Baskets, Search words): `lift_rows.py:89` / `price_bands.py:32`. Aito cannot today (`_relate` has no interval field). Needs an engine feature: lift interval or p-value on `_relate` hits, ideally with a cluster/customer correction. Visibility high on `/patterns` and medium on `/acquisition`.
2. Acquisition Wilson intervals and shares (Converts, Becomes regular; the headline table): `acquisition_service.py:47-54,117-119`. Counts and the 6-way split are available now (SQL `GROUP BY` or `_search` counts). The interval needs an engine feature: proportion interval. Visibility high.
3. Product Funnel arithmetic (impressions x ctr x conversion, units, revenue, profit; `product_funnel.py:275-304`, constants `AD_SPEND_EUR`, `BAND_DISCOUNT_PCT`). The estimates are Aito (`_estimate`/`_predict`), but chaining them, carrying odds from ranked to all showings (`_carry`, `:266-272`), and the money are app-side. Visibility high (default right tab). Partial: `$multiply` with `$p` exists in `orderBy` [ORDERBY]. Funnel chaining and `_carry` need an engine feature, or training on all showings.
4. Lead sentences (Acquisition `page.tsx:119-136`, Patterns `lead-sentences.ts`): UI selection over rows; numbers come from the rows. Visibility high.
5. Design effect (`design_effect.py:62-86`): per-customer counts could come from `GROUP BY customer` where a link-path group column is supported (unverified); the ANOVA step needs variance, which the SQL dialect lacks. Needs an engine feature (cluster-robust interval). Visibility medium (shown on every Patterns card).
6. Basket confidence and support (`basket_pairs.py:142-143`): counts and `ps` exist now; division is trivial. Whether `ps.pOnCondition` equals the raw confidence is unverified. Visibility medium.
7. Offer decision (`product_decision.py:86-93`): margin, break-even and expected ratio are arithmetic over an Aito `$p` and constants. Partial via `orderBy $multiply` [ORDERBY]. Visibility medium (second tab).
8. Hero "Sold in month" and review counts: stored rows or Python `Counter`; `SUM/COUNT GROUP BY` can compute them [SQL-GBY]. Visibility high but trivial to move.

## Things I could not fully verify

- Whether the demo's Aito deployment exposes `/api/v2/_sql`; whether SQL `GROUP BY` accepts link paths such as `context.surface`, `order_id.month` or `order_id.customer_id` (docs mention link joins at `sql-support.md:393`, not for GROUP BY columns).
- `Threshold` in `acquisition/page.tsx:76` passes `tested: data.regular_basket.length` (the shown rows) where the other views pass the tested count; this looks like a display discrepancy. The backend discards the `Significance` returned by `judge` (`acquisition_service.py:137`, `basket, _ = judge(...)`). Not run to confirm.
- `ProductEditor.tsx:165` (reviews, `avg_rating`) comes from the sandbox `/api/levers/review` write path; not traced.
