# ADR 0011: Purchase Analytics + Pattern Explorer

**Status:** Accepted
**Date:** 2026-05-11
**Deciders:** Demo team

## Context

The last two views from `TASK.md`'s eight-view list:

- **Purchase Analytics**: month-over-month bars, top products,
  category breakdown, AOV by segment. The "show the data behind
  them" half of the framework's three-task pattern.
- **Pattern Explorer**: ad-hoc `_relate` query builder. Pick a
  field + value, see which other attributes correlate (both
  positively and protectively).

Both reuse mechanics from earlier ADRs — they don't unlock new
Aito query shapes. So one combined ADR keeps the
documentation small.

## Aito usage

### Purchase Analytics

No new query patterns. Composes:

- **`_search limit=0`** for counts (orders/lines per month,
  totals per segment) — same as Dashboard.
- **`_search` with a small sample limit** + Python
  aggregation for averages (AOV per segment). Aito's
  `_search` doesn't natively expose SUM/AVG; pulling a
  representative sample and averaging client-side is the
  pragmatic shape and works fine on the demo's data volume.

The view is **read-heavy + cached aggressively** (30 min).

### Pattern Explorer

Reuses **ADR 0008's live `_relate` over `orders.line_categories`**.
The only difference vs. Bought Together: this view shows the
*full* lift band (positive + neutral + protective), not just
the top 4 positive entries. The user can pivot on any
`<pet>_<category>` token.

```json
POST /api/v1/_relate
{
  "from": "orders",
  "where": { "line_categories": { "$match": "<anchor>" } },
  "relate": "line_categories",
  "limit": 30
}
```

The `LiftHint` primitive's three-band rendering (green ≥ 1.5×,
grey 0.7–1.5×, red < 0.7×) does the heavy visual lifting —
protective patterns (cross-pet anti-correlation) read as red
chips, the demo's "not just what's bought together, also what
*isn't*" story.

## Decision

### `/api/purchase-analytics` response

```ts
interface AnalyticsResponse {
  monthly: Array<{ month: string; orders: number; revenue_eur: number }>;
  top_products: Array<{
    sku: string; name: string; pet_type: string; category: string;
    line_count: number;
  }>;
  segments: Array<{
    segment: string;
    label: string;
    customers: number;
    orders: number;
    revenue_eur: number;
    avg_basket_eur: number;
  }>;
  category_mix_by_segment: Array<{
    segment: string;
    label: string;
    top_categories: Array<{ pet_type: string; category: string; count: number; share_pct: number }>;
  }>;
  last_query: { endpoint: string; body: object };
  last_response_ms: number;
}
```

### `/api/pattern-explorer` response

```ts
interface PatternResponse {
  anchor: { id: string; display: string };
  patterns: Array<{
    label: string;
    token: string;
    lift: number;
    support: { f: number; f_on_condition: number };
    p_given: number;       // P(target | anchor)
    p_overall: number;     // P(target)
    band: "positive" | "neutral" | "protective";
  }>;
  available_anchors: Array<{ id: string; display: string }>;
  last_query: { endpoint: string; body: object };
  last_response_ms: number;
}
```

The `band` field is **derived server-side** so the frontend's
LiftHint primitive doesn't have to re-tier. Bands are:

- `positive`: lift ≥ 1.5
- `neutral`: 0.7 ≤ lift < 1.5
- `protective`: lift < 0.7

### UI structure

**Purchase Analytics** uses four cards:

```
┌── KPI strip (4) ─ Orders · Revenue · AOV · Customers active ───┐
├── Orders / Revenue per month ─ hbar list  ─ 24 months ──────────┤
├── Top 10 products by line count ─ tabular ─────────────────────┤
├── Avg basket by segment ─ hbar list ──┬── Category mix ─ hbar list │
└────────────────────────────────────────┴────────────────────────────┘
```

**Pattern Explorer** is a discovery surface:

```
┌── Anchor: [Dog dry-food ▾]    Latency 12ms · cached ────────────┐
├── Full lift table — patterns sorted by |lift − 1| descending ────┤
│  ↑↑ Dog dental-treats    × 2.72   2 953 / 3 137 baskets          │
│  ↑↑ Cat litter           × 2.14     245 /   360 baskets          │
│  · · Dog wet-food        × 1.54   2 362 / 4 424 baskets          │
│  ↓↓ Cat wet-food         × 0.27     324 / 3 494 baskets          │
│  ↓↓ Cat dry-food         × 0.25     280 / 3 243 baskets          │
└─────────────────────────────────────────────────────────────────┘
```

Aito panel updates `last_query` on each anchor change.

## Acceptance criteria

- [ ] `./do dev` renders `/purchase-analytics` with all four
      blocks + plausible numbers (orders ≈ 12 k, AOV per
      segment within €40–€120).
- [ ] `/pattern-explorer` shows the same 4 anchors as Bought
      Together's picker but reports **both** positive and
      protective patterns. `dog_dryfood` anchor surfaces
      `cat_wetfood` and `cat_dryfood` as protective (lift
      < 0.3) — that's the "not just what's bought together"
      moment.
- [ ] No regression in existing tests; pytest still 20/20.

## Demo impact

These are framework-doc task #2 ("show the data behind them").
After this commit, **all 8 views** in `TASK.md` are wired live
and the sidebar resolves end-to-end.

## Out of scope

- **Date-range picker** on Purchase Analytics. Fixed-window
  for the demo.
- **Custom field/value combos** in Pattern Explorer beyond the
  `line_categories` anchor. Future iteration could let the
  user pivot on `customer_segment` × `category` etc. — but
  requires a richer denormalisation pattern (covered by ADR
  0008's notes).

## Consequences

**Good:**
- Two views, one ADR, ~600 LoC of service code total. No new
  Aito mechanics to lock down — just composing what's already
  in the cheatsheet.
- Pattern Explorer is the natural drill-down from Bought
  Together: same query, wider view of the results. The
  demo-script can chain "Bought Together → click into
  Pattern Explorer" as a single narrative beat.

**Bad:**
- Purchase Analytics' Python aggregation pulls up to ~2 k
  rows per query for AOV calculation. Pragmatic for the demo;
  a production version would use Aito's `_aggregate` (when
  it surfaces) or a precomputed materialised view.
- We don't show *time-binned* lift trends in Pattern Explorer
  (e.g. "this co-occurrence is strengthening in 2025-Q4"). A
  cool advanced narrative we leave on the table.
