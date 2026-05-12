# Dashboard — KPIs, patterns, segments, live insight

![Dashboard](../../screenshots/01-dashboard.png)

*Four blocks driven by live Aito calls: KPI grid (`_search limit=0`
counts), top purchase patterns (`_relate` × 6 in parallel over the
denormalised `orders.line_categories` Text column), segment cards
(`_search` per segment), and the demo's headline insight quoted
from the strongest co-purchase pair.*

## Overview

A predictive e-commerce dashboard isn't a static reporting view —
the numbers on every block come from queries you can read off the
screen. The KPIs are `_search limit=0` counts; the top-patterns
bar chart is six parallel `_relate` calls; the recent-orders table
is a paged `_search`. Nothing is precomputed at build time.

The dashboard's purpose in this demo is to anchor every later view:
the "Dog dry-food → Dental treats" pair surfaces here first as a
2.72× lift bar, then drives the headline tip-box ("Aito flags this
as the demo's headline cross-sell signal"), then powers Bought
Together's anchor view. One signal, three independent surfaces,
same query body.

## How it works

### KPI grid — four `_search limit=0` calls

`_search` with `limit=0` returns just the row count — no payload,
no parsing, ~20 ms server-side. The same call shape gives
"products", "customers", "orders in the last 12 months", and the
average basket (read off a 2,000-row sample of recent orders).

```python
# src/overview_service.py — _kpi_counts()
products_total  = client.search("products",  limit=0)["total"]
customers_total = client.search("customers", limit=0)["total"]

cutoff = _month_minus(today_yyyymm, 12)     # "2025-05"
orders_12mo = client.search(
    "orders",
    where={"month": {"$gte": cutoff}},
    limit=0,
)["total"]

# Avg basket — pull a window, average locally
sample = client.search(
    "orders",
    where={"month": {"$gte": cutoff}},
    limit=2000,
)
avg_basket = sum(o["total_eur"] for o in sample["hits"]) / len(sample["hits"])
```

`month` is stored as `"YYYY-MM"` and sorts lexicographically, so
`$gte` works directly without date parsing — Aito doesn't need a
date type to do month-window cutoffs.

### Top patterns — six parallel `_relate` calls

The six bars on the dashboard are the same `_relate` body Bought
Together runs per anchor — just six anchors fanned out in a thread
pool, with the target lift read off each response.

```python
# src/overview_service.py — _compute_top_patterns()
def _lift_for(anchor_token: str, target_token: str) -> float | None:
    res = client.relate(
        table="orders",
        where={"line_categories": {"$match": anchor_token}},
        relate_field="line_categories",
        limit=20,
    )
    for hit in res.get("hits", []):
        rel = hit.get("related", {}).get("line_categories", {})
        token = rel.get("$has") if isinstance(rel, dict) else None
        if token == target_token:
            return float(hit.get("lift", 0))
    return None

# Six (anchor, target) pairs run in parallel
with ThreadPoolExecutor(max_workers=6) as pool:
    lifts = list(pool.map(lambda t: _lift_for(t[0], t[1]), anchors_targets))
```

The anchor tokens are `<pet>_<category-with-hyphens-stripped>`
(e.g. `dog_dryfood`, `cat_wetfood`). The hyphen-strip is required
because Aito's Text-column tokeniser splits on hyphens — `dry-food`
would index as two separate tokens `dry` and `food`. See
`docs/aito-cheatsheet.md` for the full set of denormalisation
gotchas.

### The insight tip-box

The insight body always cites the **dog dry-food → dental treats**
pattern — not the highest-lift one. Aquarium → aquarium-health
hits ~17× (small denominator), which is mathematically correct
but visually overpowers the narrative anchor that every later
view builds on. The dashboard surfaces every pattern in the table;
the tip-box leads with the load-bearing one.

```python
_INSIGHT_ANCHOR_LABEL = "Dog dry-food → Dental treats"
# Pick the narrative anchor; fall back to the highest-lift pattern only
# if the dog → dental signal is missing for some reason (fixture regen).
anchor = next(
    (p for p in patterns if p.label == _INSIGHT_ANCHOR_LABEL),
    patterns[0],
)
```

### Segment cards — `_search where {segment} limit=0`

Five segments (dog / cat / multi-pet / small animal / aquarium),
each rendered with `{count, share %, avg basket, descriptor}`.
Count comes from a `_search limit=0` per segment; avg basket
comes from a small customer sample + their orders. Five segments
× ~2 calls each = ~10 round-trips, cached at the dashboard level
for 10 minutes.

## Key features

### 1. No pre-aggregated tables

There's no "dashboard_kpis" table that some pipeline populates
nightly. Every number on the screen reads off Aito directly.
Add a new order and the next dashboard load reflects it (after
the 10-minute cache window, which is there to keep the demo
snappy, not because the data is slow to compute).

### 2. Same query body across views

The top-patterns row uses the *exact* `_relate` body that Bought
Together runs per anchor. Click into Bought Together for the
"Dog dry-food" anchor and you get the same 2.72× number, the
same `fOnCondition` support count, the same `pOnCondition`
conditional probability — because it's the same query.

### 3. Recent orders with deterministic anonymisation

The recent-orders table shows customer IDs as `Mikko T.`,
`Sari L.` — Finnish first names with a last-initial — generated
deterministically by hashing the `customer_id`. The same anonymous
customer always gets the same display name; the real `customer_id`
never leaves the backend.

```python
def _short_customer_name(customer_id: str) -> str:
    h = sum(ord(c) for c in customer_id)
    first = _FIRST_NAMES[h % len(_FIRST_NAMES)]
    initial = chr(ord("A") + ((h // 7) % 26))
    return f"{first} {initial}."
```

This is per CLAUDE.md's "no PII leaks" rule — `CUST-NNNNN` is
anonymous in the DB, and the UI rendering doesn't undo that.

## Data schema

The dashboard reads four tables — products, customers, orders,
order_lines — and one denormalised column: `orders.line_categories`.

```json
{
  "orders": {
    "type": "table",
    "columns": {
      "order_id":       { "type": "String" },
      "customer_id":    { "type": "String", "link": "customers.customer_id" },
      "month":          { "type": "String" },
      "total_eur":      { "type": "Decimal" },
      "line_categories":{ "type": "Text", "analyzer": "whitespace" }
    }
  }
}
```

`line_categories` is the space-separated set of `<pet>_<category>`
tokens for every line in the order — denormalised at fixture-gen
time so `_relate` can do single-hop co-occurrence over the Text
column. See ADR 0008 for the rationale (Aito's `_relate` is
within-row; cross-row co-occurrence is what `line_categories`
unlocks).

## Tradeoffs and gotchas

- **The 10-minute cache window** is what makes the dashboard feel
  instant on the demo. Production would want shorter — the
  underlying queries are fast enough (~250 ms for the whole block)
  that you could refresh on every load.
- **`_search limit=0` is the count-only shape**. Don't use
  `limit=1` and read `total` — `limit=1` still asks Aito to rank
  and serialize the top hit, which is wasted work for a pure
  count.
- **The pattern bar widths cap at 3.5×**. Aquarium →
  aquarium-health hits ~17× live but renders at 100% width; we
  document this in the bar's hover tooltip rather than auto-
  scaling, because auto-scale would shrink the dog → dental bar
  to a sliver and break the narrative emphasis.
- **Segment counts are computed per-segment, not via `_relate`**.
  `_relate from customers relate segment` would return the same
  numbers, but the cards' `{count, share %, avg basket, ...}`
  shape doesn't map cleanly to `_relate`'s row format. Five
  parallel `_search` calls beat one parsing-heavy `_relate`
  response.

## What this demo abstracts away

- **A real Insight engine** would pick the headline pattern
  automatically — confidence-weighted by support, ranked by
  unusualness, deduplicated against last week's insight. Ours
  hardcodes the narrative anchor.
- **Time-range pickers**. The dashboard is fixed to a 12-month
  window ending at the frozen demo "today" (2026-04). A real
  product would let the user slice arbitrary ranges.
- **Drill-down from KPI cards**. Clicking "10,156 orders" doesn't
  open a filtered order list — KPIs are read-only here. Pattern
  Explorer is the closest thing to a drill-down surface.

## Try it live

[**Open Dashboard**](http://localhost:8500/) (the default route).

```bash
./do dev
# → http://localhost:8500
```

The Aito panel on the right shows the `_relate` body that
generated the top-patterns row — same body Bought Together uses
when you drill into any pattern there.
