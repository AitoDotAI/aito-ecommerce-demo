# Predictive E-commerce — Aito demo

> **Status: scaffold.** `./do dev` boots the shell. Real views land
> per the build order in `TASK.md`. This README is filled out as the
> demo grows; the structure below is the target.

This is what an e-commerce platform looks like when predictions are
native — search, recommendations, catalog enrichment, pattern
discovery, evaluation. No model training. No retraining schedule. No
MLOps. The Aito side panel makes the prediction layer visible on
every screen.

Powered by [Aito.ai](https://aito.ai)'s predictive database. Sister
demos: [accounting.aito.ai](https://accounting.aito.ai) ·
[erp.aito.ai](https://erp.aito.ai). This one is at
**ecommerce.aito.ai** (in progress).

---

## See it in action

_(Screenshot / GIF lands once the layout shell is up — build-order
step 4.)_

---

## Try it now

_(One-curl-to-Aito snippet lands with the Dashboard view.)_

---

## Quick start

```bash
git clone <this repo>
cd aito-ecommerce-demo

# 1. Drop your Aito credentials into .env
cp .env.example .env
$EDITOR .env

# 2. Install deps
./do setup

# 3. Run
./do dev
# → http://localhost:8500
```

Step 2 currently only wires the scaffold. Once `data/generate_fixtures.py`
lands (build-order step 2), `./do generate-fixtures && ./do load-data`
will populate Aito with the PetNord dataset.

---

## Project structure

```
src/                Python FastAPI backend (one service per view)
frontend/           Next.js 16 (App Router) — locked Aito panel + per-view pages
data/               Deterministic JSON fixtures
tests/              pytest
docs/
  adr/              Architecture Decision Records — read these first
  aito-cheatsheet.md  Verified Aito query patterns
  demo-script.md    Two-minute live walkthrough (lands with the views)
  notes/            Durable self-notes
  sessions/         Session logs
  verification/     Adversary verification reports
do                  Task runner — `./do help`
```

Ports: Next.js on **8500**, FastAPI on **8501**.

---

## ADRs

| # | Title | Status |
|---|---|---|
| 0001 | [Scaffold + stack mirrored from `aito-erp-demo`](docs/adr/0001-scaffold-and-stack.md) | Accepted |
| 0002 | [Data model + deterministic fixtures](docs/adr/0002-data-model-and-fixtures.md) | Accepted |

---

## Learn more

- [Aito.ai docs](https://aito.ai/docs/)
- [Cross-demo framework reference](aito-demo-framework.md)
- Sister demo source: [aito-erp-demo](https://github.com/AitoDotAI/aito-erp-demo)
