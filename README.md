# Predictive E-commerce — Aito.ai demo

> What an online store looks like when predictions are native to
> every screen: search, recommendations, cross-sell, catalog
> enrichment, customer-feedback triage, churn prediction. **No
> model training. No retraining schedule. No MLOps.** Powered by
> [Aito.ai](https://aito.ai)'s predictive database. Ten views,
> all live against the same Aito DB.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Powered by Aito.ai](https://img.shields.io/badge/Powered%20by-Aito.ai-orange)](https://aito.ai)
[![Companion demos](https://img.shields.io/badge/Companion-aito--erp--demo%20%C2%B7%20aito--accounting--demo-lightgrey)](#companion-demos)

Family-line brand: **Predictive E-commerce** · matches the sibling
demos [`aito-accounting-demo`](https://github.com/AitoDotAI/aito-accounting-demo)
(*Predictive Ledger*) and
[`aito-erp-demo`](https://github.com/AitoDotAI/aito-erp-demo)
(*Predictive ERP*). PetNord is the dataset — a Nordic-flavoured
online pet store with ~700 SKUs, 3,000 customers, 12,000 orders,
39,000 order lines, and 2,000 customer reviews.

![Predictive E-commerce — 8 views, one predictive database](assets/teaser.png)

---

## Try it now

The cheatsheet ([`docs/aito-cheatsheet.md`](docs/aito-cheatsheet.md))
carries verified live query bodies for every endpoint. A one-line
probe against the live PetNord DB:

```bash
# Lift query — "what's bought with dog dry-food?" — same body the
# Bought Together view runs on every anchor change.
curl -X POST https://shared.aito.ai/db/aito-ecommerce-demo/api/v1/_relate \
  -H "x-api-key: $AITO_API_KEY" \
  -H "content-type: application/json" \
  -d '{
    "from": "orders",
    "where": { "line_categories": { "$match": "dog_dryfood" } },
    "relate": "line_categories",
    "limit": 5
  }'
# → dog_dentaltreats lift 2.72×, dog_wetfood 1.54×, dog_treats 1.53×, …
```

Returns in ~200 ms. Same query the Dashboard's top-patterns row
runs in parallel × 6 anchors.

---

## The six demo moments

Six visible, quotable predictions form the demo's narrative.
Each is in its own view, each builds on the previous:

| # | Moment | View | Aito |
|---|---|---|---|
| 1 | Smart Search rank flip — cat food drops from rank 1 to rank 6 for a dog-owner persona | [Smart Search](#2-smart-search--predictive-re-ranking) | `_search` + `_recommend` |
| 2 | For You persona switch — grid re-ranks in <300 ms on pill click | [For You](#3-for-you--personalised-tile-grid) | `_recommend` |
| 3 | Bought Together 2.72× — dog dry-food → dental treats, live | [Bought Together](#4-bought-together--co-purchase-lift) | `_relate` |
| 4 | Product Filling 5 fields — multi-`_predict` in ~480 ms | [Product Filling](#9-product-filling--catalog-enrichment) | `_predict` × 5 |
| 5 | Evaluation honest failure — Return Risk +0.0 pp gain | [Evaluation](#10-evaluation--honest-passfail) | `_evaluate` × 4 |
| 6 | **Churn ranking** — 100 customers scored by P(churn) in 2 s; drivers + held-out accuracy on one page | [Churn](#8-churn--the-killer-understand-view) | `_predict` × N + `_relate` × 3 + `_evaluate` |

The two-minute narrated walkthrough is in
[`docs/demo-script.md`](docs/demo-script.md).

---

## What's inside

Ten views grouped under five sidebar sections, all reading from
a single Aito DB. Click any guide for the full implementation,
data-schema excerpts, and tradeoffs.

### 1. 📊 Dashboard — KPIs, top patterns, segments, live insight

![Dashboard](screenshots/01-dashboard.png)

```json
{
  "from": "orders",
  "where": { "line_categories": { "$match": "dog_dryfood" } },
  "relate": "line_categories",
  "limit": 20
}
```

KPI grid + top-patterns bars (six parallel `_relate` calls) +
segment cards (`_search` per segment) + recent orders. Same query
body Bought Together runs per anchor — same 2.72× lift surfaces
in both views.
[→ Implementation](src/overview_service.py) | [Use case guide](docs/use-cases/01-dashboard.md) | [ADR](docs/adr/0005-dashboard.md)

### 2. 🔍 Smart Search — predictive re-ranking

![Smart Search](screenshots/02-smart-search.png)

```json
{
  "from": "order_lines",
  "where": {
    "product_sku.name": { "$match": "food" },
    "customer_pet_size": "large"
  },
  "recommend": "product_sku",
  "goal": { "customer_segment": "dog_owner" },
  "limit": 10
}
```

Side-by-side standard `_search` vs. predictive `_recommend`. Same
query string, different `where` + `goal` per persona — the right
column flips entirely when you click the Maija / Olli / Saara
pills. **Demo moment #1.**
[→ Implementation](src/search_service.py) | [Use case guide](docs/use-cases/02-smart-search.md) | [ADR](docs/adr/0006-smart-search.md)

### 3. ✨ For You — personalised tile grid

![For You](screenshots/03-for-you.png)

```json
{
  "from": "order_lines",
  "where": { "customer_pet_size": "large" },
  "recommend": "product_sku",
  "goal": { "customer_segment": "dog_owner" },
  "limit": 12
}
```

Same `_recommend` shape as Smart Search minus the `name $match`.
The whole catalog re-ranks per persona; Maija (cat owner) sees
cat food + litter at the top, Saara (large breed dog) sees dog
dry-food + dental treats. **Demo moment #2.**
[→ Implementation](src/recommend_service.py) | [Use case guide](docs/use-cases/03-for-you.md) | [ADR](docs/adr/0007-for-you.md)

### 4. 🛒 Bought Together — co-purchase lift

![Bought Together](screenshots/04-bought-together.png)

```json
{
  "from": "orders",
  "where": { "line_categories": { "$match": "dog_dryfood" } },
  "relate": "line_categories",
  "limit": 12
}
```

Anchor product + 4 cross-sell tiles with live lift scores. Order-
level co-occurrence via the denormalised `orders.line_categories`
Text column — Aito's `_relate` operating on a single-hop within-
row shape. **Demo moment #3** — dog dry-food → dental treats at
2.72× baseline.
[→ Implementation](src/bought_together_service.py) | [Use case guide](docs/use-cases/04-bought-together.md) | [ADR](docs/adr/0008-bought-together.md)

### 5. 📈 Purchase Analytics — the data behind the predictions

![Purchase Analytics](screenshots/05-purchase-analytics.png)

```python
# Page through the table, aggregate locally — Aito doesn't expose
# GROUP BY in _search.
while True:
    res = client.search("orders", limit=5000, offset=offset)
    for o in res["hits"]:
        monthly_counts[o["month"]] += 1
        monthly_revenue[o["month"]] += float(o["total_eur"])
    if len(res["hits"]) < 5000: break
    offset += 5000
```

Monthly orders + revenue (24 months), top-10 SKUs by line count,
per-segment KPIs, per-segment category mix. `_search` with
`offset` pagination + Python aggregation — no new Aito mechanics,
the "show me the numbers" companion to the predictive views.
[→ Implementation](src/analytics_service.py) | [Use case guide](docs/use-cases/05-purchase-analytics.md) | [ADR](docs/adr/0011-analytics-and-patterns.md)

### 6. 🔗 Pattern Explorer — the full lift band

![Pattern Explorer](screenshots/06-pattern-explorer.png)

```json
{
  "from": "orders",
  "where": { "line_categories": { "$match": "dog_dryfood" } },
  "relate": "line_categories",
  "limit": 30
}
```

Same `_relate` body Bought Together uses, no lift filter. Surfaces
the **full band** — positive (green, lift ≥ 1.5), neutral (grey),
protective (red, lift < 0.7). The "what's NOT bought together"
side of the equation, plus richer fields per row (lift, support
counts, p_given vs. p_overall).
[→ Implementation](src/pattern_service.py) | [Use case guide](docs/use-cases/06-pattern-explorer.md) | [ADR](docs/adr/0011-analytics-and-patterns.md)

### 7. 💬 Feedback — review triage via multi-field `_predict`

![Feedback](screenshots/09-feedback.png)

```json
{
  "from": "reviews",
  "where": { "text": "Package arrived late. The seal was broken." },
  "predict": "category"
}
```

Three parallel `_predict` calls over the review's `text` Text
column return **category**, **sentiment**, and the suggested
**assigned_to** agent in one round-trip. Same fanout shape as
Product Filling, applied to free-form text instead of structured
attributes — the Aito panel cycles through the three predict
bodies as you flip reviews.
[→ Implementation](src/feedback_service.py) | [Use case guide](docs/use-cases/09-feedback.md) | [ADR](docs/adr/0012-feedback-multi-predict.md)

### 8. 📉 Churn — the killer Understand view

![Churn](screenshots/10-churn.png)

```json
{
  "from": "customers",
  "where": {
    "segment": "small_animal_owner",
    "region": "oulu",
    "tenure_months": 24,
    "total_orders": 2,
    "total_spent_eur": 47.5
  },
  "predict": "churned"
}
```

KPI strip + at-risk leaderboard (per-customer `_predict churned`
× 100 in parallel) + drivers (`_relate` × 3 over the churned
subset) + honest accuracy (`_evaluate` with the timestamp held
out). Predict who's about to stop buying — from who they are,
not from when they last ordered.
[→ Implementation](src/churn_service.py) | [Use case guide](docs/use-cases/10-churn.md) | [ADR](docs/adr/0013-churn-prediction.md)

### 9. ⚡ Product Filling — catalog enrichment

![Product Filling](screenshots/07-product-filling.png)

```python
# 5 _predict calls in parallel, one per field, same `where`
where = {"name": "Hill's Sensitive Adult Dog Turkey 2kg",
         "brand": "Hill's Science Plan"}
for predict_field in ["pet_type", "category", "weight_kg", "dietary", "tax_class"]:
    client.predict("products", where=where,
                   predict_field=predict_field, limit=5)
```

Five product attributes — pet_type, category, weight_kg, dietary,
tax_class — predicted in parallel from a single product's name +
brand. Each field renders with confidence chip + top-3
alternatives + `$why` factor tooltip. **Demo moment #4** — all
five at ≥ 0.87 in ~480 ms.
[→ Implementation](src/filling_service.py) | [Use case guide](docs/use-cases/07-product-filling.md) | [ADR](docs/adr/0009-product-filling.md)

### 10. 🧪 Evaluation — honest pass/fail

![Evaluation](screenshots/08-evaluation.png)

```json
{
  "testSource": { "from": "order_lines", "limit": 200 },
  "evaluate": {
    "from": "order_lines",
    "where": {
      "product_sku.category": { "$get": "product_sku.category" },
      "product_sku.pet_type": { "$get": "product_sku.pet_type" },
      "customer_segment":     { "$get": "customer_segment" }
    },
    "predict": "returned"
  },
  "select": ["accuracy", "baseAccuracy", "n"]
}
```

Four `_evaluate` calls in parallel, three pass, **one honest
failure**. The "Return Risk" model deliberately fails its 10 pp
threshold — the 3% returned rate has no signal Aito can beat the
baseline on, and the view renders that as a red row. **Demo
moment #5.**
[→ Implementation](src/eval_service.py) | [Use case guide](docs/use-cases/08-evaluation.md) | [ADR](docs/adr/0010-evaluation.md)

---

## Quick start

```bash
git clone https://github.com/AitoDotAI/aito-ecommerce-demo
cd aito-ecommerce-demo

# 1. Drop your Aito credentials into .env
cp .env.example .env
$EDITOR .env

# 2. Install deps
./do setup

# 3. (Optional) Regenerate the PetNord dataset + upload to Aito
./do generate-fixtures
./do reset-data           # full bring-up, ~50 s

# 4. Run
./do dev
# → http://localhost:8500
```

`./do help` lists every verb.

---

## How it works

```
Browser → Next.js (port 8500) → fetch("/api/...") → FastAPI (port 8501)
                                                      ↕
                                                    AitoClient
                                                      ↕
                                                    Aito REST API
                                                      ↕
                                                    two-layer cache
                                                    (memory + Aito table)
```

- **Backend** — Python 3.12 + FastAPI. One service module per view
  (`src/<view>_service.py`). Each module builds an Aito query body,
  calls `AitoClient`, and translates the response to a DTO the
  frontend renders.
- **Frontend** — Next.js 16 (App Router) + TypeScript. One page per
  view in `frontend/app/<view>/page.tsx`. The locked Aito side
  panel reads its config from `frontend/lib/panel-content.ts` and
  updates its `query` block with the actual body that ran.
- **Schema** — Four tables (`products`, `customers`, `orders`,
  `order_lines`) with link declarations chained so `_recommend`
  and `_relate` traverse one hop without manual joins. Two
  denormalised columns for cases where Aito only supports
  single-hop traversal: `order_lines.{customer_segment,
  customer_pet_size}` and `orders.line_categories`.
- **Cache** — Two layers: in-memory LRU per process + Aito-backed
  `prediction_cache` table that survives restarts. Read-only API
  keys disable the persistent layer cleanly.

---

## Aito operators used

| Operator | What it does | Used in |
|---|---|---|
| `_search` | Retrieve rows / count via `limit=0` | Dashboard KPIs, Smart Search baseline, Purchase Analytics, Bought Together sample SKUs |
| `_match` (via `$match`) | Token match on Text columns | Smart Search, Bought Together (`line_categories`), Pattern Explorer |
| `_recommend` | Rank rows by `P(goal | row)` | Smart Search predictive column, For You |
| `_relate` | Co-occurrence with lift / support / `pOnCondition` | Dashboard top patterns, Bought Together, Pattern Explorer, Churn drivers × 3 parallel |
| `_predict` | Predict a field with `$p` + `$why` factor tree | Product Filling × 5 parallel, Feedback × 3 parallel, Churn at-risk × N parallel |
| `_evaluate` | Cross-validation accuracy + baseline + per-row results | Evaluation × 4 parallel, Churn × 1 |

Verified query bodies + Aito-API gotchas (multi-field `goal`
semantics, hyphen tokenisation, single-hop link traversal, the
`_evaluate` body shape) are captured in
[`docs/aito-cheatsheet.md`](docs/aito-cheatsheet.md).

---

## Project structure

```
src/                Python FastAPI backend
  app.py              All endpoints — table of contents
  aito_client.py      Thin REST wrapper, retries + `$why`-decorated `_predict`
  cache.py            Two-layer cache (memory + Aito table)
  rate_limit.py       Two-tier rate limiter (per-IP + global)
  data_loader.py      Schema + fixture upload
  overview_service.py    Dashboard
  search_service.py      Smart Search
  recommend_service.py   For You
  bought_together_service.py
  pattern_service.py
  analytics_service.py
  feedback_service.py
  churn_service.py
  filling_service.py
  eval_service.py

frontend/           Next.js 16 (App Router)
  app/<view>/page.tsx           per-view pages
  components/shell/             AppShell · TopBar · Sidebar · AitoPanel · ErrorState · ScaffoldStub
  components/prediction/        PredictionBadge · ConfidenceBar · WhyTooltip · PredictedField · LiftHint
  lib/api.ts                    apiFetch + latency-event broadcast
  lib/panel-content.ts          per-view Aito-panel configs
  lib/types.ts                  shared DTOs

data/               Deterministic JSON fixtures (seed = 42)
  generate_fixtures.py          single source of truth — re-runs idempotent
  products.json · customers.json · orders.json · order_lines.json · reviews.json

tests/              pytest — fixture signal checks + AitoClient body shape
screenshots/        Canonical per-view screenshots (the inspect/ subfolder is the workshop)
docs/
  use-cases/                    8 per-view implementation guides
  adr/                          11 Architecture Decision Records — read these first
  aito-cheatsheet.md            verified query patterns + Aito gotchas we hit
  demo-script.md                two-minute walkthrough
  product-sheet/                outreach PDF
  sessions/                     session logs (the working notebook)
do                              task runner — `./do help`
```

Ports: Next.js on **8500**, FastAPI on **8501**.

---

## Deep dive

- **[Use case guides](docs/use-cases/)** — 8 per-view
  implementation guides with code, schema, and tradeoffs
- **[Architecture Decision Records](docs/adr/)** — 11 ADRs walking
  the design rationale top-to-bottom
- **[Aito cheatsheet](docs/aito-cheatsheet.md)** — verified live
  query bodies + the Aito-API gotchas we hit during the build
- **[Demo script](docs/demo-script.md)** — two-minute narrated
  walkthrough; five demo moments in narrative order
- **[Cross-demo framework](aito-demo-framework.md)** — the
  conventions shared across the family of Aito vertical demos
- **[TASK.md](TASK.md)** — the working brief that drove the build

---

## ADRs

Read top-to-bottom and you have the demo's full design rationale.

| # | Title | Status |
|---|---|---|
| 0001 | [Scaffold + stack mirrored from `aito-erp-demo`](docs/adr/0001-scaffold-and-stack.md) | Accepted |
| 0002 | [Data model + deterministic fixtures](docs/adr/0002-data-model-and-fixtures.md) | Accepted |
| 0003 | [Aito schema, data loader, query-method surface](docs/adr/0003-aito-schema-and-loader.md) | Accepted |
| 0004 | [Layout shell + design tokens](docs/adr/0004-layout-shell.md) | Accepted |
| 0005 | [Dashboard view + overview_service](docs/adr/0005-dashboard.md) | Accepted |
| 0006 | [Smart Search — predictive re-ranking](docs/adr/0006-smart-search.md) | Accepted |
| 0007 | [For You — personalised tile grid + persona switcher](docs/adr/0007-for-you.md) | Accepted |
| 0008 | [Bought Together — order-level co-occurrence](docs/adr/0008-bought-together.md) | Accepted |
| 0009 | [Product Filling — multi-field `_predict`](docs/adr/0009-product-filling.md) | Accepted |
| 0010 | [Evaluation — honest pass/fail](docs/adr/0010-evaluation.md) | Accepted |
| 0011 | [Purchase Analytics + Pattern Explorer](docs/adr/0011-analytics-and-patterns.md) | Accepted |
| 0012 | [Feedback — multi-field `_predict` over review text](docs/adr/0012-feedback-multi-predict.md) | Accepted |
| 0013 | [Churn — the killer Understand view](docs/adr/0013-churn-prediction.md) | Accepted |

---

## EU hosted · No PII stored

`customer_id` is anonymous (`CUST-NNNNN`). The Aito DB lives in
the EU. Public-demo deployments run with `PUBLIC_DEMO=1` which
locks down CORS, returns 404 from `/api/schema`, and disables the
write side of the cache so a read-only API key is sufficient.

---

## Companion demos

The Aito predictive-database family of OSS vertical demos:

- **[aito-accounting-demo](https://github.com/AitoDotAI/aito-accounting-demo)** —
  *Predictive Ledger*. Multi-tenant AP automation: GL coding,
  approver routing, payment matching, anomaly detection. 255
  customers, 128K invoices, one shared Aito instance.
- **[aito-erp-demo](https://github.com/AitoDotAI/aito-erp-demo)** —
  *Predictive ERP*. Procurement-to-pay workflow loop: PO routing,
  smart entry, approval routing, inventory replenishment. Three
  industry profiles (industrial maintenance / retail / services).
- **[aito-demo](https://github.com/AitoDotAI/aito-demo)** — the
  original grocery e-commerce reference; the `ContextPanel`
  design here is the canonical Aito-panel pattern the vertical
  demos import.

---

*Apache 2.0 licensed. Open issues, send PRs, fork into your own
e-commerce vertical.*
