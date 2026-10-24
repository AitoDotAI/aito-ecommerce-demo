# PetNord site review: duplicate views, and a target structure

Reviewed on 2026-10-24. Code: `aito-ecommerce-demo-observable` (branch `observable-data`, 99d14dc, dirty), running at :8500/:8501 against env `observable`. Proposals read: ADR 0034 (uci), 0037 (adr37), 0038–0040 (adr38). Read-only: no repo file edited, no Aito writes. Live numbers below come from GET calls on 2026-10-24.

## Main findings

1. **The Shop already does what the standalone shopper views do, with queries that measured better.** Smart Search, For You and Cart Completion each run one query that the Shop runs in a refined form. Bought Together's question is answered twice: in the Shop drawer per SKU, and in Shop analytics per category with intervals. The standalone views also personalise with `context.customer` (identity). ADR 0033's amendment (R1/R2 sweep) measured identity as a tie on hit@12 and worse on Brier, and dropped it from the Shop. So the demo's beats 2 and 3 show the pattern the project has rejected.
2. **ADR 0037's personalised-search benchmark measures Smart Search's query, which the Shop no longer ships.** That query is the one-query identity blend `_search impressions … where {context.customer}`. The Shop's search works differently: two steps, declared pets, the household rule as a filter (`src/shop_search.py` explains why the one-query blend can't filter). Decide which query the evidence is about before running it. Otherwise the number describes a view this review proposes to remove.
3. **Six places send the same `_relate`.** The query is `from orders where {line_categories: {$match: dog_dryfood}} relate line_categories`, in: Dashboard top patterns, Bought Together, Pattern Explorer, Basket Rules (once per anchor), Shop analytics Baskets, and Cart Completion. All of them show dog dry food → dental treats at 2.66×. Only Shop analytics gives it counts, a design-effect interval (2.34–3.03) and a Bonferroni bar. The rest show bare lifts.
4. **Three views and a proposal all look at one product.** Product Insights, Price's drill-down and what-if (ADR 0029), and ADR 0038's product manager view each pick a product. They should be one Product view. The Price fair-band table and Inventory/Demand/Markdown are catalogue lists that feed into it.
5. **Some screens are stale, and the 360° views show accuracy numbers.**
   - The live Dashboard serves an uncommitted snapshot (`data/precomputed/v2-observable/dashboard.json`, written 2026-10-20 19:43). That is older than 5bb0582 (2026-10-21, "derived dashboard pills"). It still prints the hand-written "Highest LTV · monthly food reorder · highest LTV" on Dog households (€74.34 basket), next to Dog & cat households at €108.38.
   - Dashboard copy still points to retired roles: "predicted-next column lands with For You" (`frontend/app/page.tsx:156`), and the insight's "drill into … Bought Together / Pattern Explorer" (`src/overview_service.py:471`).
   - Feedback predicts "Churn risk (90 d)" from review text. ADR 0039 finds that the generator *copies* churn into reviews, so this claim runs backwards.
   - The demo script's For You aside ("flip the goal to `{clicked: true}`") has no UI: the goal is hard-coded in `src/recommend_service.py:99`.
   - The demo script's numbers are stale (live values in brackets): 2.68× (2.66), 72 %/94 % rule confidence (67 %/97 %), dog wet-food ×1.5 (1.3), Shop analytics "about 2.8×" (2.66).
   - The sidebar badges are static: "98%" on Product Filling, "11,970 orders · 16ms avg" (live total: 11,909), "Live", "New".
   - ADR 0037 says "no screen in 360° shows an accuracy number". Today Churn (96 % vs 65 %), Demand (vs naive), Evaluation and the Product Filling badge all do.

---

## 1. Recommendation table

| Current view | Verdict | Reason (one line) | What is lost |
|---|---|---|---|
| Shop | **Keep** (the shopper side) | The best-measured queries: three per-intent views, cart, rules, search, drawer | — |
| Smart Search | **Move to Evidence** (live side-by-side on the "Personalised search" page) | The Shop's search is the shipped one. The BM25-vs-personalised contrast is evidence, not a shop function | The side-by-side as a top-level demo beat (it stays on the Evidence page) |
| For You | **Move to Query patterns** (as the plain `_recommend` example), then drop the view | "Picked for you" is the same `_recommend` with better context; identity was measured as no better | The three-persona flip and the purchased-vs-clicked goal teaching (keep in Query patterns) |
| Bought Together | **Drop** | SKU level is in the Shop drawer; category level is in Shop analytics Baskets, with intervals | Anchor sample-SKU tiles (minor) |
| Cart Completion (hidden) | **Drop** | The Shop's cart re-ranks "Picked for you" through `context.basket_categories`; the old view's hidden-route reason (a €108 bag for a €1.68 cart) is a symptom of its category-level `_relate` | Nothing the Shop lacks |
| Dashboard | **Keep, rebuild** as the owner's home: KPIs plus one headline per owner view, each a link | The current pattern row and household cards duplicate Shop analytics and Purchase analytics | — |
| Purchase Analytics | **Merge into Dashboard** (monthly trend, top products); household category mix → Shop analytics "Who buys what" | Descriptive `_search` counts with no Aito mechanism; households are already on the Dashboard | A standalone "data behind it" page |
| Shop analytics | **Keep**, rename "Patterns". It absorbs Pattern Explorer and Basket Rules | It is the only statistically honest relate view | — |
| Pattern Explorer | **Merge into Patterns** (a "less often than chance" band beside Baskets; Patterns already lists below-1 lifts that clear the bar) | Same `_relate`, no intervals | The free anchor picker (could become a filter on Baskets) |
| Basket Rules | **Merge into Patterns** (confidence both ways as columns on Baskets: `orders_with_both / orders_with_first` is already in the payload) | Same `_relate` swept per anchor, no intervals | The rule framing ("72 % confidence, asymmetric") becomes a column, not a page |
| Product Insights | **Merge into Product** (ADR 0038 product manager view) as its "History" tab | Same scope: one product | — |
| Price | **Split.** Per-SKU demand curve and what-if → Product "What if" tab. Catalogue fair-band table → Supply | Per-product pricing belongs with the product's other levers (discount, label, stock) | The sweet-spot `_relate` (shows nothing on today's data; drop) |
| Demand (hidden) | **Merge into Supply** with Inventory and Markdown; the accuracy block → Evidence | They share `demand_forecast.py`, and Inventory and Markdown consume the forecast | — |
| Inventory | **Merge into Supply** (its reorder queue is Supply's main list) | — | — |
| Markdown (hidden) | **Merge into Supply** (an overstock row's action) | It is an action on Inventory's overstock list | — |
| Churn | **Merge with Win-back into Retention**; the accuracy block → Evidence | At-risk list → the win-back offer is one workflow | — |
| Win-back (hidden) | **Merge into Retention** | As above | — |
| Feedback | **Keep as an Operate tool**, renamed "Review triage"; **drop its churn-risk field** | Text → category, sentiment, assignee is a valid `_predict`; churn-from-text is reversed in the data (ADR 0039) | The churn-risk field (it should go) |
| Product Filling | **Keep as an Operate tool**; drop the "98%" badge | Catalogue enrichment, not duplicated anywhere | — |
| Evaluation | **Move to Evidence** as "Model checks" (plus Churn's and Demand's accuracy, Filling's accuracy, ADR 0038's calibration check) | ADR 0037: accuracy numbers live in Evidence | Beat 6 as a 360° beat (it becomes the Evidence beat; Return risk's honest failure keeps its place there) |
| *Planned:* Product manager (0038) | **New: "Product"** | The one-product view | — |
| *Planned:* Reviews (0039) | **New: "Reviews & NPS"** | Effects chain with intervals | — |
| *Planned:* Acquisition (0040) | **New: "Acquisition"** | — | — |
| *Planned:* Business reorders (0034) | **Evidence** (as 0037 says) | Real data, a cleared claim | — |
| *Planned:* Evidence index (0037) | **New** | — | — |

---

## 2. Target information architecture

### Principles

- **One job per view, one view per job.** Every function below lands in exactly one view.
- **Sections follow the person, not the Aito endpoint.** The shopper, the owner running the shop, the operator automating chores, the evaluator asking "how well?". The endpoint is shown in the Aito panel on every view, which already teaches it.
- **Objects link across views.** A product, a shopper and a pattern open the same detail wherever they appear.
- **No accuracy numbers outside Evidence** (ADR 0037). 360° views link to the Evidence page that measures them.

### Sitemap

```
PetNord
│
├── 360° INTELLIGENT ECOMMERCE
│   │
│   ├── SHOP  (shopper)
│   │   └── Shop ........................ /shop
│   │         ├─ Buy again · Next for their kit · Picked for you
│   │         ├─ Search (in-grid)
│   │         ├─ Cart (URL)  ·  Fill my usual basket
│   │         └─ Product drawer: details, alternatives, often-in-same-basket,
│   │                            in your orders, ["Owner view →" Product]
│   │
│   ├── RUN THE SHOP  (owner)
│   │   ├── Overview .................... /            (Dashboard)
│   │   ├── Patterns .................... /patterns    (Shop analytics)
│   │   ├── Product ..................... /product?sku=&month=   (ADR 0038)
│   │   ├── Supply ...................... /supply      (Demand+Inventory+Markdown)
│   │   ├── Acquisition ................. /acquisition (ADR 0040)
│   │   ├── Retention ................... /retention   (Churn+Win-back)
│   │   └── Reviews & NPS ............... /reviews     (ADR 0039)
│   │
│   └── OPERATE  (back office automation)
│       ├── Product filling ............. /product-filling
│       └── Review triage ............... /review-triage   (Feedback)
│
├── EVIDENCE  (evaluator: "how well, against what?")
│   ├── Index ........................... /evidence   (Real / Synthetic marks)
│   ├── Business reorders (Real, UCI) ... /evidence/business-reorders   (ADR 0034)
│   ├── Personalised search (Synthetic)   /evidence/personalised-search (ADR 0037 §3,
│   │                                      + live side-by-side, ex-Smart Search)
│   ├── Search text relevance (Synth.) .. /evidence/search-relevance    (ADR 0026 report)
│   └── Model checks (Synthetic) ........ /evidence/model-checks        (ex-Evaluation,
│                                          churn/demand/filling accuracy, 0038 calibration)
│
└── FOR DEVELOPERS
    └── Query patterns .................. /query-patterns
          one runnable example per Aito endpoint, each linking to the view
          that uses it in production form (ex-For You's plain _recommend,
          goal purchased vs clicked; raw _relate; _evaluate; _estimate)
```

### Sidebar

| Group label | Items (order) |
|---|---|
| **Shop** | Shop |
| **Run the shop** | Overview · Patterns · Product · Supply · Acquisition · Retention · Reviews & NPS |
| **Operate** | Product filling · Review triage |
| **Evidence** | Evidence (index) · Business reorders · Personalised search · Search relevance · Model checks |
| **For developers** | Query patterns |

That is 17 entries: 12 now (6 of them planned) + 5 Evidence, against today's 19 shown and 4 hidden. Two top-level headings carry ADR 0037's split: "360° intelligent ecommerce" over the first three groups, "Evidence" over the last two. Replace the static badges with nothing, or with Real/Synthetic marks in Evidence.

### Each view's one job

| View | Primary user | Its one job (the question) | Main Aito queries |
|---|---|---|---|
| Shop | Shopper | "What should I buy now, for my pets, this visit?" | `_recommend impressions` (declared pets, month, cart words), `_predict skus.$feature` (own orders), `_predict product_sku order_lines` (kit), `_search products $similarity`, `_relate orders.skus`, `_batch` re-ask |
| Overview | Owner | "How is the shop doing, and where should I look?" | `_search` counts and `_batch`; one headline per owner view, as a link |
| Patterns | Owner / analyst | "What goes with a click, a purchase, a basket, a search word, a group?" | field `_relate` on impressions, order_lines, orders; design effect; Bonferroni |
| Product | Product manager | "What will this product do this month, why, and what if I change its price, discount, label or stock? For whom?" | `_predict clicked/purchased` with `$why`, `_estimate units_sold` (regression what-if), plus the History tab's `_batch` counts and `_relate` buyers |
| Supply | Buyer / ops | "What do I reorder, what is overstocked, and what markdown clears it?" | `_estimate units_sold` per SKU, Python bands, markdown at several prices |
| Acquisition | Marketer | "Which sources bring visitors who buy and stay?" | `_relate contexts.source`, `_predict became_regular` |
| Retention | CRM | "Who is about to leave, why, and what offer brings them back?" | `_predict churned_in_3_months`, `_relate` drivers, `_recommend winback_campaigns` |
| Reviews & NPS | Owner / CX | "What do reviews and experiences do to clicks, sales, NPS, churn, demand and price?" | `_relate` on impressions, nps_responses, customer_months; `_estimate`; ADR 0029 what-if |
| Product filling | Catalogue editor | "Fill this product's missing fields" | 5× `_predict products` with `$why` |
| Review triage | Support | "Route this review" | 3× `_predict reviews` (category, sentiment, assignee) |
| Evidence pages | Evaluator / CTO | "How well does it work, against what baseline?" | committed `data/evidence/*.json`; no live benchmark |
| Query patterns | Developer | "What does each Aito endpoint look like, minimally?" | one minimal call per endpoint |

### How a user moves between views

| From | Action | To |
|---|---|---|
| Shop product card / drawer | "Owner view of this product →" | Product `?sku=&month=` (same month as the Shop) |
| Shop reason chip ("Goes with your cart ×2.4") | click | Patterns, Baskets row for that pair |
| Shop search box | "How well does this work? →" (small link) | Evidence › Personalised search |
| Product › "For whom" row (high/low offer_share) | "See it as this shopper →" | Shop `?shopper=` (a persona from that band) |
| Product › stock = low | "Reorder →" | Supply, that row highlighted |
| Product › stars band | "What stars do →" | Reviews & NPS, filtered to the product |
| Patterns row (any product field) | click a product | Product |
| Overview headline tiles | click | their owner view |
| Supply overstock row | "Mark down" (in place) | — (markdown is a column/action, not a page) |
| Retention at-risk customer | "Win-back offer" (in place) | — |
| Acquisition cohort | "Will they stay? →" | Retention (cohort filter) |
| Any 360° view footer | "How well? →" | the matching Evidence page (Model checks for churn, demand, filling) |
| Any view's Aito panel | "Minimal form →" | Query patterns, that endpoint |

Today there is one cross-link in the whole app (Shop analytics → Basket Rules, `frontend/app/shop-analytics/page.tsx:94`), and the Shop links to no owner view.

### Where every current function goes

| Current function (view › block) | Lands in |
|---|---|
| Shop › Buy again, Next for kit, Picked for you, search, cart, Fill my usual basket, drawer | Shop (unchanged) |
| Smart Search › BM25 column vs personalised column, persona pills | Evidence › Personalised search (live illustration above the benchmark) |
| Smart Search › "food for an old dog" (words win) | Shop search (already true there); Evidence page example |
| For You › persona grid, `_recommend` with `context.customer` | Query patterns › `_recommend` (minimal form) |
| For You › goal purchased vs clicked (script aside, no UI today) | Query patterns › `_recommend` (with a goal toggle, if built) |
| Bought Together › anchor → category cross-sells | Patterns › Baskets |
| Bought Together › sample SKUs per category | Shop drawer › often in the same basket (SKU level) |
| Cart Completion › 4 scenario carts | Shop cart (live) |
| Basket Rules › confidence, support, direction | Patterns › Baskets (columns) |
| Pattern Explorer › positive / neutral / protective bands per anchor | Patterns › Baskets (anchor filter; below-1 rows that clear the bar) |
| Dashboard › top patterns row | Overview headline (one row, linking to Patterns) |
| Dashboard › KPIs, households, recent orders | Overview |
| Purchase Analytics › monthly orders/revenue, top products | Overview |
| Purchase Analytics › household KPIs | Overview (dedupe with the Dashboard's household cards) |
| Purchase Analytics › category mix by household | Patterns › Who buys what (already there, with intervals) |
| Shop analytics › what goes with a click/purchase, who buys what, baskets, search words | Patterns |
| Product Insights › funnel, surfaces, buyers, monthly units, reviews | Product › History |
| Price › per-SKU demand curve, what-if waterfall | Product › What if |
| Price › fair-band table (catalogue) | Supply (a price column / outlier flag) |
| Price › sweet-spot `_relate` | Drop (nothing passes the filter on today's data, by its own docstring) |
| Demand › top movers forecast | Supply |
| Demand › seasonality `_relate` | Patterns › Who buys what (season already a group there; "summer sells health") |
| Demand › accuracy vs naive | Evidence › Model checks |
| Inventory › KPIs, reorder queue, overstock | Supply |
| Markdown › proposal per overstock SKU | Supply (overstock row action) |
| Churn › KPI strip, at-risk list, drivers | Retention |
| Churn › `_evaluate` accuracy | Evidence › Model checks |
| Win-back › per-customer offer and €recoverable | Retention (at-risk row action) |
| Feedback › category, sentiment, assignee | Review triage |
| Feedback › churn risk (90 d) | Drop (reversed causality, ADR 0039); Retention covers churn |
| Product Filling › 5 fields with `$why` | Product filling |
| Evaluation › pet type, dietary, Return risk | Evidence › Model checks |
| ADR 0038 › state, CTR/conversion estimate, what-if, for whom | Product |
| ADR 0038 › label, stock, review_count lifts | Patterns › What goes with a purchase |
| ADR 0039 › six effects | Reviews & NPS |
| ADR 0040 › funnel by source, landing, will they stay, value | Acquisition |
| ADR 0034 › draft order, outcome, claim, UCI bought together | Evidence › Business reorders |

---

## 3. Inventory of today's views

| View (route) | Nav group | Question it answers | Audience | Aito queries · table | Backend | ADR | State |
|---|---|---|---|---|---|---|---|
| Dashboard `/` | Overview | Shop at a glance | Owner | `_search` counts, `_batch`, `_relate orders.line_categories` · orders, customers, order_lines | `overview_service.py` (precomputed) | 0005 | Snapshot is stale (see finding 5) |
| Shop `/shop` | Assist Customers | What should I buy now? | Shopper | `_recommend impressions` (declared pets + month + cart words), `_predict skus.$feature` (nested own orders), `_predict product_sku order_lines` (owned), `_search products $similarity`, `_relate orders.skus`, `_batch _predict purchased just_bought`, `_relate contexts.owned` | `shop_*.py` | 0031, 0033 | Current |
| Smart Search `/smart-search` | Assist | Text vs personalised ranking | Shopper → really developer/evaluator | `_search products $similarity` vs `_search impressions get product_sku orderBy $multiply[$p purchased, $similarity]` where `context.customer` | `search_service.py` | 0006, 0026 | Identity-based |
| For You `/recommendations` | Assist | Recommendations for a customer | Shopper → really developer | `_recommend impressions product_sku` where `context.customer`, goal purchased | `recommend_service.py` | 0007 | Identity-based; no goal toggle |
| Bought Together `/bought-together` | Assist | Cross-sell for a category | Owner, really (category level) | `_relate orders where line_categories $match relate line_categories` | `bought_together_service.py` | 0008 | Duplicate |
| Purchase Analytics `/purchase-analytics` | Analyze | Monthly orders, top products, households | Owner | `_search` paging + Python aggregation ("no new Aito mechanics") | `analytics_service.py` | 0011 | Duplicates Dashboard households |
| Product Insights `/product-insights` | Analyze | One product's funnel, surfaces, buyers, units, reviews | Product manager | `_batch` ~20 `_search limit 0`, `_relate order_lines` per buyer field (pets, dog_size, diet, region), `_search monthly_sales` | `product_insights_service.py` | 0028 | No intervals on buyer lifts |
| Shop analytics `/shop-analytics` | Analyze | What goes with click/purchase; who buys what; baskets; search words | Owner / analyst | field `_relate` impressions & order_lines; `_relate orders.line_categories`; `_relate context.search_query`; design effect, Bonferroni | `shop_analytics_service.py`, `basket_pairs.py`, `search_words.py`, `lift_rows.py` | 0031–0033 | Current, the strongest |
| Pattern Explorer `/pattern-explorer` | Analyze | Positive / neutral / protective co-occurrence for an anchor | Analyst | `_relate orders line_categories` (limit 30) | `pattern_service.py` | 0011 | Duplicate, no intervals |
| Basket Rules `/basket-rules` | Analyze | Association rules over all anchors | Analyst | `_relate orders line_categories` per anchor | `basket_rules_service.py` | 0022 | Duplicate, no intervals |
| Feedback `/feedback` | Understand | Triage a review | Support | 3–4× `_predict reviews` where text | `feedback_service.py` | 0012 | Churn field invalid per 0039 |
| Churn `/churn` | Understand | Who will churn, drivers, accuracy | CRM | `_predict churned_in_3_months customer_months`, `_relate customers` per field, `_evaluate` | `churn_service.py`, `churn_drivers.py` (precomputed) | 0013 | Shows accuracy (96 % vs 65 %) |
| Demand `/demand` *(hidden)* | Operate | Next month's units per SKU; seasonality; accuracy | Buyer | 25× `_estimate monthly_sales`, `_relate order_lines` season, `_evaluate` time split | `demand_service.py`, `demand_forecast.py`, `demand_evaluation.py` | 0014 | Hidden |
| Inventory `/inventory` | Operate | Reorder queue, overstock | Buyer / ops | `_search` inventory, products, monthly_sales; `_estimate` per critical row | `inventory_service.py` | 0015 | Current |
| Price `/price` | Operate | Fair bands, sweet spots, demand curve, what-if | Pricing | `_search product_states`, `_aggregate`, `_relate product_states`, `_estimate` at 7 prices, `_estimate model: regression` | `price_service.py`, `price_what_if.py`, `price_bands.py` | 0016, 0029 | Sweet-spot block empty by design |
| Markdown `/markdown` *(hidden)* | Operate | Discount depth for overstock | Merchandiser | `_estimate` at several prices | `markdown_service.py` | 0018 | Hidden |
| Cart Completion `/cart-completion` *(hidden)* | Operate | Complete 4 scenario carts | Shopper (in an owner group) | `_relate orders line_categories` + `_search products` | `cart_completion_service.py` | 0019 | Hidden; panel says `_recommend` though it runs `_relate` (`last_query` endpoint label at :372) |
| Win-back `/winback` *(hidden)* | Operate | Who to email with what | CRM | `_recommend winback_campaigns` goal responded, `_predict responded`, `_estimate` | `winback_service.py` | 0020 | Hidden |
| Product Filling `/product-filling` | Automate | Fill a product's missing fields | Catalogue | 5× `_predict products` | `filling_service.py` | 0009 | Static "98%" badge |
| Evaluation `/evaluation` | Automate | Do the models beat the prior? | Evaluator | 3× `_evaluate` (products ×2, order_lines) | `eval_service.py` (precomputed) | 0010 | Accuracy, belongs to Evidence |

---

## 4. Shopper side: what the Shop already does

| Standalone view | Its query | What the Shop does instead | Better or same? | What only the standalone teaches |
|---|---|---|---|---|
| **Smart Search** | Left: `_search products orderBy $similarity{name}` θ=4. Right: one `_search impressions get product_sku where {context.customer: id} orderBy $multiply[$p{purchased}, $similarity{name}]` | `shop_search.py`: (1) the same `_search products $similarity` to find matching names (score > 1); (2) the grid's `_recommend` `where` (declared pets as evidence, month, cart words, household rule), restricted to those SKUs; (3) ranked by P × text lift with Smart Search's own `TEXT_THETA`; top 12 re-asked for reasons | **Better.** Cart- and month-aware. Keeps the household rule (the one-query blend's `where` can't filter `product_sku.*`, probe 2026-10-17). No identity (ADR 0033 R1/R2). Live: "food" for Maija gives cat food in both | The **side-by-side** (text-only vs personalised, ★ "not in baseline top 10", rank deltas); the **one-query** `$multiply` form as an Aito pattern. Both are evidence/teaching, not shop functions |
| **For You** | `_recommend impressions product_sku where {context.customer: id} goal {purchased: true}` limit 12 | "Picked for you": `_recommend` on the same table and goal, with `context.customer.pets` `$and $match`, `context.month`, `context.basket_categories`, pets and diet filters, the just-bought re-ask via `_batch`, `$why` reason chips | **Better** (measured best of 11 queries on hit@12 and Brier, ADR 0033 amendment) | The minimal `_recommend` with only an id (a good first example for developers); "Aito learns the shopper from their own rows" (which the Shop deliberately stopped relying on). The goal toggle exists only in the script |
| **Bought Together** | `_relate orders where {line_categories $match anchor} relate line_categories` (category level) | Drawer "Often in the same basket": `_relate orders where {skus $match sku} relate skus` (SKU level, with counts). Category level: Shop analytics Baskets (same `_relate`, with interval) | **Better, split across two views** | Nothing beyond a picker of anchors |
| **Cart Completion** (hidden) | `_relate orders line_categories` per scenario cart, then popular products in the related category by `_search` | The cart re-ranks "Picked for you" through `context.basket_categories`; "Goes with your cart ×2.4" chip; kit items in the cart count as owned in "Next for their kit" | **Better** (product-level, priced in by the shopper's own conversion, not category popularity: the hidden reason "a €108 bag for a €1.68 cart" comes from the category-level shape) | Nothing |
| **Product Filling** | 5× `_predict products` from name + brand | Not in the Shop | Different job | All of it: catalogue enrichment. Keep (Operate) |

---

## 5. Owner side: the analytics compared

### Overlapping questions

| Question | Answered by today | Strongest | Others |
|---|---|---|---|
| Which categories go together in a basket? | Dashboard top patterns, Bought Together, Pattern Explorer, Basket Rules, Shop analytics Baskets, (Cart Completion) | **Shop analytics Baskets**: lift 2.66, interval 2.34–3.03, counts, design effect, Bonferroni | All five others send the same `_relate`, with bare lifts |
| Which categories go *less* together? | Pattern Explorer (protective band), Shop analytics (rows below 1 that clear the bar) | Shop analytics (it judges the effect; Pattern Explorer's 0.07× for small-animal dry food is an obvious pet-type split) | — |
| Rule direction / confidence | Basket Rules | Basket Rules (unique), but derivable from Shop analytics' `orders_with_both / orders_with_first` | — |
| Who buys what (households, diet, season) | Purchase Analytics category mix, Shop analytics Who buys what, Product Insights Who buys it, Demand seasonality | **Shop analytics** (intervals; season, segment, diet groups) | Purchase Analytics: Python counts. Demand seasonality: interval-filtered, overlaps the season group |
| How is one product doing? | Product Insights, Price drill-down, (ADR 0038 Product manager) | Will be ADR 0038 + Product Insights' History | Price's demand curve and what-if belong there |
| What drives a click/purchase? | Shop analytics funnel fields, (ADR 0038 per product), (ADR 0039 stars) | Shop analytics (catalogue level), Product (one product) | — |
| Household KPIs | Dashboard households, Purchase Analytics households | One view (Overview) | Exact duplicate data (`dog` 74.34 € in both) |
| Next month's demand | Demand, Inventory (per row), Price (curve), Markdown | One shared function (`demand_forecast.py`), four pages | → Supply + Product |
| Who leaves? | Churn, Win-back, Feedback churn field, (ADR 0039 churn effects) | Churn (panel `_predict`); ADR 0039 adds causes | Feedback's churn field: reversed data, drop |
| Is it accurate? | Evaluation, Churn accuracy block, Demand accuracy, Filling badge | → Evidence › Model checks | ADR 0037 rule |

### View by view

| View | Distinct value | Overlap | Rigor | Stale / issues | Verdict |
|---|---|---|---|---|---|
| Shop analytics | Field relates over impressions with state, declared, context and recency fields; search words with the right baseline | Superset of Pattern Explorer, Basket Rules, Bought Together | Intervals, design effect, support ≥ 30, Bonferroni | Demo script says "about 2.8×", live is 2.66× | Keep → **Patterns** |
| Purchase Analytics | Monthly trend, top products | Households = Dashboard; category mix = Shop analytics | Descriptive | Docstring: "no new Aito mechanics" | Merge → Overview |
| Pattern Explorer | Three-band chip display | Same `_relate` as 4 others | None | Dashboard insight still points to it | Merge → Patterns |
| Product Insights | Funnel, surfaces, monthly units, reviews for one SKU | ADR 0038 | Buyer lifts ranked by support only, no interval | — | Merge → Product |
| Basket Rules | Confidence, direction | Same `_relate` | None | Demo script 72 %/94 % vs live 67 %/97 % | Merge → Patterns |
| Churn | At-risk list, drivers | Win-back; ADR 0039 | `_evaluate` shown in a 360° view | Review copy to update per ADR 0039 | Merge → Retention; accuracy → Evidence |
| Win-back (hidden) | Offer per customer, € recoverable | Churn | Hidden for showing raw P as a response rate | — | Merge → Retention |
| Demand (hidden) | Forecast per SKU | Inventory, Price, Markdown | Accuracy vs naive | Hidden | Merge → Supply |
| Inventory | Reorder queue, tied capital | Demand | — | — | → Supply |
| Price | What-if waterfall (ADR 0029) is strong | Product (ADR 0038 what-if) | Sweet spot shows nothing on today's data | Fair-band table is catalogue-level stats | Split → Product (what-if) + Supply (bands) |
| Markdown (hidden) | Clearance depth | Inventory, Price | Lost margin on every row | Hidden | → Supply action |
| Evaluation | Return risk's honest failure | Churn and Demand accuracy blocks | Good, but an accuracy number | Retired fourth model noted | → Evidence |
| Feedback | Triage | ADR 0039 Reviews (different job: effects vs routing) | — | "Churn risk (90 d)" from text is reversed causality | Keep as Review triage, drop churn field |
| Dashboard | Landing | Duplicates Purchase Analytics households and the pattern row | — | Stale snapshot "Highest LTV"; "predicted-next column lands with For You"; insight links to Bought Together / Pattern Explorer | Rebuild as Overview; re-run `./do precompute` |

### Pre-ADR-0033 and stale leftovers

| Where | What | Fix |
|---|---|---|
| `data/precomputed/v2-observable/dashboard.json` (uncommitted, 2026-10-20 19:43) | `"note": "monthly food reorder · highest LTV"`, `"pill_text": "Highest LTV"` on Dog (€74.34) while Dog & cat is €108.38. The code has derived pills since 5bb0582 (2026-10-21) | Re-run `./do precompute` on `observable`; the other 6 snapshots in that folder predate code changes of 10-21 too |
| `frontend/app/page.tsx:156` | "predicted-next column lands with For You" | Remove |
| `src/overview_service.py:459,471` | Insight sends readers to Bought Together and Pattern Explorer | Point to Patterns |
| `src/feedback_service.py` / Feedback page | Predicts "Churn risk (90 d)" from review text; the label is copied from churn (ADR 0039) | Drop the field |
| `docs/demo-script.md` Beat 3 aside | Goal flip to `{clicked: true}`: no UI | Remove, or build it in Query patterns |
| `docs/demo-script.md` Beats 1, 4, Shop analytics beat | 2.68×, dog wet-food ×1.5, 72 %/94 %, cat litter 2.28×/2.14×, "about 2.8×" | Update from live values |
| `frontend/components/shell/Sidebar.tsx` | Static "98%", "Live", "New", "11,970 orders · 16ms avg" | Drop or make data-driven |
| `src/cart_completion_service.py:372` | Panel labels the query `_recommend` though it runs `_relate` | Moot if dropped |
| Smart Search, For You, `tests/test_aito_check.py:45,78,98` | Use `context.customer` (identity), which the Shop dropped after R1/R2 | Move to Evidence / Query patterns, as labelled teaching forms |

---

## 6. Demo script: what each change would break

| Change | Beat affected | What to do |
|---|---|---|
| Smart Search → Evidence | **Beat 2** (demo moment #1), Quick recovery row 1, "Common questions: does Aito learn the user's history?" | Re-tell beat 2 in the Shop (Maija "food" → cat food; Janne "food" → grain-free only; "food for an old dog" → dog food), with "how well → Evidence › Personalised search" |
| For You → Query patterns | **Beat 3** (demo moment #2), Quick recovery row 2 | Fold into the Shop beat ("Picked for you" per persona; same pets → same grid; Buy again sets them apart) |
| Bought Together dropped | **Beat 4** (demo moment #3), Quick recovery row 3, Dashboard insight copy | Shop drawer "often in the same basket" + Patterns › Baskets (dog dry food → dental 2.66×, interval) |
| Basket Rules → Patterns | Beat 4 optional follow-on | Confidence columns on Baskets |
| Pattern Explorer → Patterns | Quick recovery row 3 | — |
| Evaluation → Evidence | **Beat 6** (demo moment #5), Quick recovery row 4 | Becomes the Evidence beat ADR 0037 already plans ("for how well, here's the evidence section"); Return risk's zero gain stays the punchline |
| Product Filling | Beat 5 unchanged (keep the view); drop the "98%" badge claim | — |
| Dashboard → Overview | Beat 1 (its 2.68× pattern row) | Keep one headline pattern, linking to Patterns |
| Close (Beat 7) "a dozen views" | Wording | "Seven owner views, one shop, one Aito DB" |
| Churn/Win-back merge, Supply merge | Paused section only (Markdown, Win-back, Demand, Cart Completion are hidden) | Restore as Retention / Supply beats when ADR 0027's data lands |
| Tests | `test_aito_check.py`: Smart Search ×3, For You ×2, Basket Rules ×1 | Keep the query-level checks if the queries live on in Evidence / Query patterns; drop with the view otherwise |

Net effect: the script's five "demo moments" all sit on views this proposal moves. The rewritten path is Shop (shopper) → Product (owner, the same product) → Patterns → Evidence. That is the order ADRs 0031, 0037 and 0038 already describe in their demo-impact sections.
