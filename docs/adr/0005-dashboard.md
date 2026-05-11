# ADR 0005: Dashboard view + overview_service

**Status:** Accepted
**Date:** 2026-05-11
**Deciders:** Demo team

## Context

The Dashboard is the first page every visitor sees and the only
view that *summarises* across the whole demo. It must show real
PetNord numbers (not the mock's placeholder figures) so the
read-the-numbers-and-trust-the-rest reflex kicks in.

`TASK.md` specifies four blocks (mock lines 564–719):

1. **KPI grid** — products, orders (12 mo), customers, avg basket.
2. **Top purchase patterns** — co-purchase lift bars per
   `(pet_type, category) → category` pattern (e.g. dog dry-food
   → dental treats ≈ 3.1×).
3. **Customer segments** — emoji + share + avg basket + descriptor
   per segment (dog/cat/small animal/aquarium).
4. **Insight + Recent orders** — a one-line discovery and a 6-row
   table of recent orders.

## Aito usage

### What runs live against Aito

- `_search` with `limit=0` for every KPI **count** (one call per
  table; `total` is read off the response). Range-filtered with
  `where: { month: { "$gte": <YYYY-MM> } }` for the 12-month
  count.
- `_search` with `where: { segment: <id> }` per segment for the
  customer-segments block — 5 small calls, ~10 ms each.
- `_search` over `orders` with `orderBy: month` desc for the
  recent-orders table. No `_recommend` per row in this view —
  the predicted-next-purchase column is a placeholder in the MVP
  (it's the For You / Bought Together moment, not the dashboard).

### What is computed locally (from the JSON fixtures)

- **Top purchase patterns** — `(category_a, category_b)` co-
  purchase lift per order. This is an *order-level* co-occurrence
  pattern; Aito's `_relate` over `order_lines` gives a *line-level*
  same-row relation, which isn't the same thing. Doing it correctly
  via Aito requires a reverse-link `_relate` shape we haven't pinned
  (live probe in step 3 returned 400 for the obvious forms; see
  the cheatsheet). The Bought Together view (ADR 0008) is where
  we'll properly engineer the live shape; the dashboard summary
  computes the same numbers in Python from `data/*.json` so the
  demo's headline patterns are correct.

- **Avg basket** — sum of `total_eur` / order count. Could be done
  via `_search` aggregations if Aito's `where: { … }` exposes a
  sum; pinning that is for the Purchase Analytics ADR.

### Cache strategy

`overview_service.get_dashboard(client, ...)` hits seven `_search`
endpoints + one local Python pass. Cached under `dashboard:summary`
with a 10-minute TTL. The persistent-cache layer (Aito-backed)
survives backend restarts. Cold-cache populate is ~150 ms total
(measured end-to-end against the live PetNord DB).

## Decision

### `/api/dashboard` response shape

```ts
interface DashboardResponse {
  kpis: {
    products: { value: number; delta_label: string | null };
    orders_12mo: { value: number; delta_label: string | null };
    customers: { value: number; delta_label: string | null };
    avg_basket_eur: { value: number; delta_label: string | null };
  };
  top_patterns: Array<{
    label: string;       // "Dog dry-food → Dental treats"
    lift: number;        // e.g. 2.68
    bar_pct: number;     // 0-100, derived from lift for the bar width
  }>;
  segments: Array<{
    id: string;          // "dog_owner"
    emoji: string;
    label: string;       // "Dog owners"
    share_pct: number;   // 0-100
    avg_basket_eur: number;
    note: string;        // "monthly reorder" etc.
    pill: { text: string; tone: "orange"|"blue"|"grey"|"purple" };
  }>;
  insight: { headline: string; body: string };   // derived once at build
  recent_orders: Array<{
    order_id: string;
    customer_short: string;   // first name only for anonymity
    month: string;
    line_summary: string;     // "Royal Canin Dog Food 4kg + 2 more"
    total_eur: number;
  }>;
  last_query: { endpoint: string; body: object };
  last_response_ms: number;
}
```

The frontend's `usePagePanel(...)` sets the per-page panel config;
the page also calls `setPanel(...)` after the fetch resolves so the
panel's `last_query` reflects what actually ran.

### Computation rules

- **`delta_label`** is `null` in the MVP — historical comparison
  (last-12mo vs prior-12mo) is a Purchase Analytics concern, not
  the dashboard's. The frontend renders the KPI card without the
  delta line when `delta_label` is null.
- **`bar_pct`** = `min(1, lift / 3.5) * 100` — bars peg at 100 %
  for lifts ≥ 3.5×. Matches the mock's visual scaling.
- **`pill.tone`** is fixed per segment (dog → orange = highest LTV,
  cat → blue = high frequency, small_animal → grey = growing,
  aquarium → purple = high AOV). Keeps the dashboard's narrative
  consistent.

### Top-patterns Python computation

```python
def _top_patterns(orders, lines, products, k=6):
    """For each category_a, find the top category_b with highest
    order-level lift. Then take the top-k pairs by lift."""
    # 1. Build sku→category map.
    # 2. For each order, collect set of categories present.
    # 3. For each (a, b) pair, count co-occurrence and compute lift.
    # 4. Return top-k sorted by lift desc.
```

The same `_dog_food_dental_lift` helper from
`data/generate_fixtures.py` is the validator; we generalise it
here to all `(a, b)` pairs.

## Acceptance criteria

- [ ] `./do dev` renders the Dashboard at `/` with **live** KPI
      numbers matching `_search limit=0` totals against the
      PetNord DB (products = 658, customers = 3000, orders ≈
      11 970, avg basket within ±€2 of `sum(total_eur)/count`).
- [ ] Top Purchase Patterns shows ≥ 6 rows; the top entry includes
      `(dog dry-food → dental treats)` with lift ≥ 2.5× (matches
      ADR 0002 signal #2).
- [ ] Customer Segments shows 4 cards (dog / cat / small animal /
      aquarium) with shares summing to ~95 % of customers (the
      missing 5 % is `multi_pet`, displayed in a 5th row or merged
      into dog).
- [ ] Recent Orders shows 6 rows ordered by `month` desc.
- [ ] Aito panel's query block reflects the actual `_search` body
      that drove the latest fetch — `last_query` is set after the
      `/api/dashboard` response lands.

## Demo impact

The Dashboard is the visitor's first impression. Getting the
numbers right here makes every later view's prediction read as
trustworthy. The 2.7× lift quoted in the panel description (set
in step 4) now also appears in the Top Patterns bar, which is
the cross-page consistency check.

## Out of scope

- Predicted-next-purchase column in Recent Orders — that's a
  per-customer `_recommend` call; lands with the For You ADR.
- KPI deltas (orange `↑ 18 % YoY` text). Adds without earning the
  complexity of historical windowing.
- `_relate`-based dashboard insights (live tip-box discovery).
  Pattern Explorer ADR (0009) is the right home for that.

## Consequences

**Good:**
- The Dashboard ships **today** with the real numbers. Visitors
  see a working demo immediately; we don't block on the perfect
  `_relate` shape.
- The Python lift function is shared with `tests/test_fixtures.py`
  — both depend on the same logic, so a regression in either
  surfaces in the other.

**Bad:**
- Top Patterns is the only block on the demo that doesn't quote
  a live Aito call. The Aito panel makes this honest: the query
  body shown is the *intended* live shape, captioned with "see
  Bought Together for the live drill-down". Sales conversations
  will need to clarify that the dashboard summary is a one-shot
  aggregation, not a per-impression call. Worth the trade.
