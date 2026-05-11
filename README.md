# Predictive E-commerce — Aito demo

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

This is what an e-commerce platform looks like when predictions are
native — search, recommendations, catalog enrichment, pattern
discovery, evaluation. **No model training. No retraining schedule.
No MLOps.** The Aito side panel makes the prediction layer visible on
every screen.

Powered by [Aito.ai](https://aito.ai)'s predictive database. Sister
demos: [accounting.aito.ai](https://accounting.aito.ai) ·
[erp.aito.ai](https://erp.aito.ai). This one runs at
**[ecommerce.aito.ai](https://ecommerce.aito.ai)** and lives on
GitHub as
[aito-ecommerce-demo](https://github.com/AitoDotAI/aito-ecommerce-demo).

![Predictive E-commerce — 8 views, one predictive database](assets/teaser.png)

---

## See it in action

Eight views, all live against the same Aito DB. Run `./do dev` and
open <http://localhost:8500>. The screenshots in
[`screenshots/`](screenshots/) are produced by
`frontend/scripts/inspect-views.cjs` (gitignored — regenerate
locally; the teaser image above is built from them via
`./do teaser`).

The two-minute narrated walkthrough is in
[`docs/demo-script.md`](docs/demo-script.md); the five demo moments
in order are Smart Search → For You → Bought Together → Product
Filling → Evaluation.

For a print-ready overview, the
[product sheet](docs/product-sheet/product-sheet.pdf)
(`./do product-sheet`) collects the same content as an 11-page PDF
with each view's spotlight.

---

## Try it now

The cheatsheet (`docs/aito-cheatsheet.md`) carries verified live
query bodies for every endpoint. A one-line probe against the live
PetNord DB (read-only API key in `.env.example`):

```bash
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

Same query body the **Bought Together** view runs on every
anchor change.

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

## What's inside

Eight views grouped under four sidebar sections, all reading from a
single Aito DB:

| Section | View | Endpoint | What it shows |
|---|---|---|---|
| Overview | **Dashboard** | `_search` + Python aggregation + `_relate`-derived insight | KPIs, lift bars, segment cards, recent orders |
| Assist customers | **Smart Search** | `_search` + `_recommend` | Side-by-side standard vs predictive results — the **rank-flip moment** |
| Assist customers | **For You** | `_recommend` | Personalised tile grid per customer pill |
| Assist customers | **Bought Together** | `_relate` | Anchor → 4 cross-sells with live lift |
| Analyze | **Purchase Analytics** | `_search` + Python aggregation | MoM bars, top SKUs, per-segment KPIs |
| Analyze | **Pattern Explorer** | `_relate` | Full lift band (positive · neutral · protective) |
| Automate | **Product Filling** | `_predict` × 5 parallel | Five fields filled from product name + brand |
| Automate | **Evaluation** | `_evaluate` × 4 parallel | Pass/fail with one engineered honest-failure |

The five **demo moments** from `TASK.md` are now all live, each
described in [`docs/demo-script.md`](docs/demo-script.md):

1. **Smart Search rank flip** — same query, totally different list per persona
2. **For You persona switcher** — grid re-ranks in < 300 ms on pill click
3. **Bought Together 2.72×** — dog dry-food → dental treats, live
4. **Product Filling 5 fields** — multi-`_predict` in ~480 ms
5. **Evaluation honest failure** — Return Risk +0.0 pp gain

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
  view in `frontend/app/<view>/page.tsx`. The locked Aito side panel
  reads its config from `frontend/lib/panel-content.ts` and updates
  its `query` block with the actual body that ran.
- **Schema** — Four tables (`products`, `customers`, `orders`,
  `order_lines`) with link declarations chained so
  `_recommend` and `_relate` traverse one hop without manual joins.
  Two denormalised columns for cases where Aito only supports
  single-hop traversal: `order_lines.customer_segment` /
  `customer_pet_size` and `orders.line_categories`.
- **Cache** — Two layers: in-memory LRU per process + Aito-backed
  `prediction_cache` table that survives restarts. Read-only API
  keys disable the persistent layer cleanly.

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
  products.json · customers.json · orders.json · order_lines.json

tests/              pytest — fixture signal checks + AitoClient body shape
docs/
  adr/                          11 Architecture Decision Records — read these first
  aito-cheatsheet.md            verified query patterns + Aito gotchas we hit
  demo-script.md                two-minute walkthrough
  sessions/                     session logs (the working notebook)
do                              task runner — `./do help`
```

Ports: Next.js on **8500**, FastAPI on **8501**.

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

The cheatsheet ([`docs/aito-cheatsheet.md`](docs/aito-cheatsheet.md))
records every verified live query body, response shape, and the
Aito-API gotchas we hit during the build (multi-field `goal`
semantics, hyphen tokenisation, single-hop link traversal, the
`_evaluate` body shape, and more).

---

## EU hosted · No PII stored

`customer_id` is anonymous (`CUST-NNNNN`). The Aito DB lives in
the EU. Public-demo deployments run with `PUBLIC_DEMO=1` which
locks down CORS, returns 404 from `/api/schema`, and disables the
write side of the cache so a read-only API key is sufficient.

---

## Learn more

- [Aito.ai docs](https://aito.ai/docs/)
- [Cross-demo framework reference](aito-demo-framework.md)
- Sister-demo source:
  [aito-accounting-demo](https://github.com/AitoDotAI/aito-accounting-demo)
  ·
  [aito-erp-demo](https://github.com/AitoDotAI/aito-erp-demo)
  ·
  [aito-demo](https://github.com/AitoDotAI/aito-demo) (the original
  grocery reference).
