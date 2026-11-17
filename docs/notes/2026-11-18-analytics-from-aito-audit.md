# Analytics audit: where do the numbers come from, and could Aito compute them?

Written 2026-11-17 for Antti (target Thu 19.11). Read-only audit of the demo's analytics views, release 5 (`1dbceec`).

**The question:** Antti wants more of the demo's analytics to come from Aito itself, either from functionality Aito already has, or by Aito providing the statistics the demo now computes itself.
**For every number on an analytics view:** (a) an Aito query (`_relate`, `_predict`, `_estimate`, `_evaluate`, SQL), live or snapshotted; (b) app-side arithmetic over rows fetched from Aito or from stored files; (c) generator constants or fixtures. For each (b): can Aito do it today, or which engine feature is missing.

## What the audit found, in six lines

1. **The statistics layer is (b) almost everywhere.** Aito supplies the counts, lifts and probabilities; the *interval, share, ratio, margin and bootstrap* on top are Python or TypeScript. The single most visible gap is the **interval on every lift** (Patterns, Acquisition, Baskets, Search words, Customers highlights): `_relate` returns `related, condition, lift, ps, fs` and nothing else (`aito-core/api-docs/coreapi.yaml`, `/api/v1/_relate` response).
2. **The Overview's headline numbers can move to Aito today.** Orders, Revenue, Average basket, Customers ordering, the monthly bars and the best sellers are computed by paging *every* order and line row out of Aito and summing in Python (`src/overview_service.py:85-98`, `:107-144`). v2 SQL `count/sum/avg` with a single-column `GROUP BY` covers all of them (`aito-core/docs/sql-support.md`, "GROUP BY", "Aggregate expressions").
3. **Customers is not an Aito view at all.** Every number is (b) over stored files (`data/customer_profiles/*.json`) built **offline from the fixtures** by `./do customer-profiles` (`scripts/generate_customer_profiles.py`, which has no Aito client), then re-counted in Python per ticked segment (`src/customer_selection.py:91`). The rows live in Aito; the derived per-customer values (profit, revenue after action costs) are not Aito columns.
4. **Supply is (b) over (c).** Stock, reorder point, unit cost, lead time and monthly sales are fixture values; the decision cards are arithmetic over them. Only the markdown sweep (five `_estimate units_sold` per SKU, 15 SKUs) is an Aito query.
5. **Retention is mostly (a)**: churn risk `$p` and `$why`, drivers `_relate`, win-back and per-action predictions are Aito. The headline *wrappers* (counts above a threshold, euros "over doing nothing") are (b).
6. **Two defects found on the way** (below): a wrong "tested" count on the Acquisition page, and a stale hard-coded footnote on Customers.

## Routing: four of the ten views are redirect stubs (ADR 0041)

`/churn` → Retention, `/demand` → Supply, `/shop-analytics`, `/pattern-explorer`, `/basket-rules` → `/patterns/`, `/purchase-analytics` → Overview `/`, `/product-insights` → `/product/` (`frontend/lib/moved-routes.ts`). The audit covers the destination pages. Detailed tables, with file:line for each number: `analytics-audit-2026-11-17/detail-A.md` (Customers, Patterns, Overview), `detail-B.md` (Acquisition, Patterns, Product), `detail-C.md` (Retention, Supply).

## Ranked by visibility in a demo

| # | Number(s) | View | Origin | Aito today? | Missing engine feature, or the data-model change |
|---|---|---|---|---|---|
| 1 | The interval beside every lift ("0.70–0.89"); the "N lifts tested … design effect 2.9" footer | Patterns (first screen), Acquisition, Baskets, Search words, Customers highlights | b (`src/lift_rows.py:89`, `src/price_bands.py:32`, `src/design_effect.py:62`) | **No** | **Lift interval / p-value on `_relate` hits**, ideally customer-clustered (impressions of one customer are not independent) and corrected for the number of lifts tested |
| 2 | Orders, Revenue, Average basket, Customers ordering, revenue and orders per month, best sellers (top 5 units) | Overview (first screen) | b (`overview_service.py:85-144`: pages all rows, sums in Python) | **Yes**: `SELECT count(*)`, `sum(total_eur)`, `sum()/count(*)`, `count(DISTINCT customer_id)` (sole select item), `… GROUP BY month`, `GROUP BY product_sku` | none (unverified: `GROUP BY` a product with a link-path filter `order_id.month`) |
| 3 | Revenue €463,669, profit per customer €77, NPS, churn 33 %, revenue beside every condition | Customers (first screen) | b over stored files from fixtures | Sums and means: **yes** once per-customer revenue and profit are columns | **Data model:** profit = price paid − unit cost − action costs (`src/customer_profit.py:22`) is derived per customer and not an Aito column. Then segment counts become `_relate`/SQL |
| 4 | "Profit per customer ±" interval; margins and "difference in points" rows | Customers (Highlights) | b: 500-resample bootstrap in numpy (`src/customer_segments.py:169`), z = 1.96 or 3 normal margins | **No** (no bootstrap/quantile/median in SQL or `_aggregate`; `_aggregate` does return `$mean` with `standardError`, `docs/aito-cheatsheet.md:972-975`) | **Bootstrap / quantile aggregate**, and the lift interval in row 1 |
| 5 | Product Funnel: clicks, CTR, purchases, units, revenue, profit, break-even (the default right tab) | Product | b over a: chained `_estimate`/`_predict`, rescaled to the product's own history (`_carry`, `src/product_funnel.py:266`), times hand constants `AD_SPEND_EUR`, `BAND_DISCOUNT_PCT` (c) | Partly: each `$p` is Aito; `orderBy $multiply [col, $p]` exists (`coreapi.yaml:5048`) | **Training on all showings, or conditioning on the ranked surface**, so no carry-over is needed; the money stays app logic (hand constants) |
| 6 | "Reorder these 83 now", "€14,383 at risk", "833 units, €12,620 at cost" | Supply (first screen) | b over c (`src/supply_rows.py:166-180,247-254`: `max(0, 3-month mean + safety − stock)`) | Grouped means: yes. The `max(0, …)` and an aggregate expression with `GROUP BY`: **no** | **Conditional / GREATEST scalar and grouped aggregate expressions**, or a derived `recent_units` column |
| 7 | "€27,691 tied up in 79 overstocked" | Supply | b over c (`supply_service.py:97,112`) | Closest to doable: `sum(expr)` with a computed `WHERE` (`sql-support.md` computed columns); per-row expression inside `sum` is unverified | none, or as row 6 |
| 8 | Headline table (converts %, becomes regular %), with Wilson intervals | Acquisition | counts a, shares and intervals b (`src/acquisition_service.py:47-54`) | Counts and the 6-way split: **yes** (`GROUP BY`, `count(*)`); the interval: **no** | **Proportion interval** (with row 1) |
| 9 | "€6,498 spent"; "54 of 2,034 likely to leave"; "€284 over doing nothing" | Retention (cards) | b around Aito outputs | €6,498: **yes** (`sum(spent_eur) GROUP BY customer_id`). 54 of 2,034: **no**. €284: business arithmetic over `_predict`/`_estimate`, no feature needed | **Aggregate over predictions** (`PREDICTION()` is per-row only, `sql-support.md:84-88`, and invalid with `GROUP BY`) |
| 10 | Basket confidence, reverse confidence, support | Patterns (Baskets) | b: ratios of the `fs` counts Aito returns (`src/basket_pairs.py:142-143`) | **Yes**, the counts are already in the response (does `ps.pOnCondition` equal the raw confidence? unverified) | none |
| 11 | Search-word lift ("converts above or below the average search") | Patterns | b: Aito's own lift uses all impressions as the baseline and is wrong here (about 2.5× for every word, `src/search_words.py:8-18`) | **No** | **`_relate` over a restricted population** (a nested `from` answers 501 on 2.11.4) |
| 12 | Tenure bands in "Drivers" | Retention | b: four `_search` counts divided in Python | **No** | **`_relate` over a numeric range** (`docs/aito-cheatsheet.md:690-713`, td-20261003142449808722), or a pre-banded column |
| 13 | "Tells" card (flags, NPS bands, rates and lifts) | Retention (high) | b: five whole tables joined in Python with 3-month windows | Yes, as `_relate` on derived flag columns of `customer_months` (cheatsheet Q11) | **Data model:** derived flag columns in the generator, not an engine feature |
| 14 | Offer & margin: margin per 100 showings, break-even ×, "expected ×", advised band | Product (2nd tab) | b over a and c (`src/product_decision.py:86-93`; hand constants `BAND_DISCOUNT_PCT`) | Partly via `orderBy $multiply`; `price − cost` inside it unverified | none, constants stay app logic |
| 15 | Supply price bands (mean ± 1.5σ), season test in "Candidates to end" | Supply (lower blocks) | b (`src/supply_end_of_line.py:289-299`) | **No**: grouped stddev not in SQL (only count/sum/avg) | **Per-group stddev**; multi-key grouped aggregation (works but in memory) |
| 16 | Top movers, rating and sentiment bars, "Sold in month", review counts | Supply, Product history | b (Python `Counter`, stored rows) | **Yes**: `avg(units_sold) GROUP BY product_sku ORDER BY … LIMIT 10`, `count(*) GROUP BY rating` | none |

Rows that are (a) already and need nothing: churn risk `$p` and `$why`, the Retention drivers `_relate` (apart from tenure), the win-back `_recommend`/`_predict`/`_estimate`, "bought when shown" per discount band and the `$why` chain, the lift and `fs` counts on Patterns, buyer lifts on Product, the feedback patterns lift lists (computed offline by `scripts/feedback_patterns_prototype.py`, which does query Aito; its p-values are Python).

## Engine features implied, in one list

| Feature | Unlocks | Today |
|---|---|---|
| **E1. Interval / p-value on `_relate` hits** (and on `_aggregate` means); optionally cluster-robust (by customer) and multiple-test corrected | rows 1, 4, 8, 11 and every lift on Patterns, Customers, Acquisition | nothing in `aito-core/docs` or `api-docs` ("interval", "bootstrap" find only benchmark prose) |
| **E2. Proportion interval on counts** (Wilson), if not part of E1 | row 8 | none |
| **E3. Bootstrap / quantile / median aggregate** | row 4 (and "median €", "top tenth earns" on Customers) | none; `_aggregate` has `$mean` + `standardError` |
| **E4. `_relate` over a numeric range or band** | row 12 | reported (td-20261003142449808722) |
| **E5. `_relate` over a restricted population** (nested `from`) | row 11 | 501 on 2.11.4 |
| **E6. Aggregate over predictions** (count of rows with P > x, mean P) | row 9 ("54 of 2,034") | `PREDICTION` is per-row only |
| **E7. SQL: conditional/GREATEST scalar, aggregate expression with `GROUP BY`, per-group stddev, grouped `count(DISTINCT)`; window functions and subqueries** | rows 6, 7, 15; Customers journeys, rolling NPS, monthly churn, quintile ranking | listed "Not supported yet" (`sql-support.md`) |
| **E8. Training on all showings, or surface-conditioned estimates** | row 5 | not documented |

**Data-model changes (not engine features), cheaper and ours to do:** per-customer derived columns (revenue, profit, action costs) on `customers`; derived flag columns on `customer_months` for Tells; a banded tenure column; a stored `recent_units` column for Supply.

## Doable now, with Aito as it is

Rows 2, 10, 16, and the €6,498 in row 9: no engine feature, only moving the computation from Python into a `_sql`/`_search` call. The Overview is the strongest first move: it is the first screen, its numbers are plain `count/sum/avg`, and it currently pages **every order and line row** out of Aito to add them up (`overview_service.py:85-98`).
Before building on SQL, check that the engine the demo serves answers `POST /api/v2/_sql` (the demo reports `"api": "v2@master"`, but I did not call it): unverified.

## Defects found on the way (not part of the audit's question)

- **Acquisition, "What the first basket says" threshold line** passes `tested: data.regular_basket.length`, the number of *rows shown*, instead of the number of candidates tested (`frontend/app/acquisition/page.tsx:73`). The backend drops the real value: `basket, _ = judge(...)` (`src/acquisition_service.py:137`). The footer therefore states a smaller family size than was tested and a smaller Bonferroni correction than was applied. Read in the code, not run. Should be a failing test first, then the fix.
- **Customers footnote** hard-codes "165 kept lines" and "about two-thirds" of base price (`frontend/app/customers/page.tsx:112-118`): these are (c) and go stale when the data changes.

## How this was made, and its limits

Three read-only research agents traced each view's page components → API fields → backend functions → the Aito query or the arithmetic, and checked claims about Aito against `aito-core/docs`. **No query was run against any engine.** I spot-checked five claims against the code and docs: `PREDICTION` is a per-row projection and invalid with `GROUP BY`, and `GROUP BY` takes one column (`sql-support.md`); `_relate` returns `related, condition, lift, ps, fs` (`coreapi.yaml`); `generate_customer_profiles.py` has no Aito client; `overview_service.all_rows` pages and sums in Python; the Acquisition threshold bug. Line numbers are approximate to a few lines.
**Unverified, marked so in the detail files:** `_sql` served by the demo's engine; `GROUP BY` with a link-path column; whether `ps.pOnCondition` equals confidence; MAE/RMSE for `_estimate`; and `sql-support.md` contradicts itself on whether `evaluate`/`estimate` work in SQL ("Supported" in one section, "Still open" in its roadmap).
Supply and Retention headline cards on the Overview were traced only to their snapshots (`data/precomputed/v2-master/*.json`, written by `./do precompute`, which queries Aito and then does Python arithmetic).
