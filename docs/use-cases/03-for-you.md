# For You — personalised tile grid with live persona switching

![For You](../../screenshots/03-for-you.png)

*Personalised product grid for the active persona. Click any pill
in the persona bar above (Maija / Olli / Saara) and the entire
12-tile grid re-ranks in <300 ms — same query body, different
`where` + `goal`, completely different recommendations.*

## Overview

For You is the "what should this customer see on the home page"
view. It reuses Smart Search's `_recommend` query shape — same
table, same `goal` semantics — but drops the `name $match` filter
so the result spans every category the persona-segment buys.

The demo's second-strongest moment lives here. After Smart Search
demonstrates the rank-flip for a specific query, For You shows the
same effect across the whole catalog: Maija (cat owner) gets cat
food + litter + cat accessories; Saara (large breed dog owner)
gets dog dry-food + dental treats + large-breed accessories; Olli
(multi-pet small dog) gets the dog-side of a small-pet household.

## How it works

### The query

```python
# src/recommend_service.py — get_for_you()
where = {}
if persona.pet_size is not None:
    where["customer_pet_size"] = persona.pet_size
goal = {"customer_segment": persona.segment}

client.recommend(
    table="order_lines",
    where=where,
    recommend_field="product_sku",
    goal=goal,
    limit=12,
)
```

Same shape as Smart Search minus the name-match clause. For Maija
the `where` is `{}` (no pet_size constraint); for Olli and Saara
the `where` carries `{customer_pet_size: small | large}` and the
`goal` carries the matching segment.

The frontend issues one call per persona switch — there's no batch
trick. The 300 ms latency is end-to-end (Aito call + 6 ms cache
overhead) on a warm cache; first-call cold latency is ~1 s.

### The "Olli divergence"

Olli's customer record is `multi_pet` per the fixture (ADR 0002).
But the *segment-level* conditioning treats `multi_pet` as the
whole multi-pet population — which leans cat in our fixture
because cat-owners-with-a-dog outnumber dog-owners-with-a-cat.

That makes Olli's "multi-pet" goal indistinguishable from Maija's
"cat-owner" goal, which breaks the demo's "the grid flips per
persona" moment.

The fix: For You overrides Olli's goal to `dog_owner + small` —
the segment + size that matches his hand-curated 85% dog history.
The UI label stays "multi-pet, small dog" so the persona names
read as TASK.md specifies; the Aito panel honestly shows the live
goal body that ran. This is "persona labelling", not per-customer
personalisation. ADR 0007 §"Olli divergence" has the full
rationale.

```python
PERSONAS = {
    "maija": Persona("maija", "CUST-00001", "Maija — cat owner",
                     segment="cat_owner", pet_size=None),
    "olli":  Persona("olli",  "CUST-00002", "Olli — multi-pet (small dog)",
                     segment="dog_owner", pet_size="small"),
    "saara": Persona("saara", "CUST-00003", "Saara — large breed dog owner",
                     segment="dog_owner", pet_size="large"),
}
```

### Score on each tile

Each tile renders the `$p` from Aito as a small confidence number
(0.0–1.0). That's P(this persona-segment | product = X), not
P(persona-X-clicks-product). The label on the tile says "match
score" because the conditional is the right intuition for the
shopper-facing demo, even if the technical meaning is conditional
probability.

```python
tiles.append(Tile(
    sku=hit.get("sku", ""),
    # ... other fields ...
    score=round(float(hit.get("$p", 0)), 3),
))
```

## Key features

### 1. Same query body as Smart Search

For You is Smart Search without the `name $match`. Reusing the
query shape means the Aito panel description, the cache structure,
and the "what's a recommendation" mental model are all consistent
across the two views.

### 2. The grid flips entirely between personas

Maija's top tile is cat food. Olli's is small dog food. Saara's is
large breed dog food. There's no overlap in the first three tiles
across the three personas in the warm-cache demo state. That's the
"predictive context drives the catalog presentation" effect made
visible.

### 3. Goal-overrides documented honestly

When the customer record's segment is overridden at query time
(Olli), the Aito panel shows the goal that actually ran, not the
customer record's nominal segment. CLAUDE.md prime directive #2:
never silently transform. If the persona label and the goal differ,
the panel exposes the difference.

## Data schema

For You reads from `order_lines` with the denormalised customer
context columns:

```json
{
  "order_lines": {
    "type": "table",
    "columns": {
      "product_sku":       { "type": "String", "link": "products.sku" },
      "customer_segment":  { "type": "String" },
      "customer_pet_size": { "type": "String" }
    }
  }
}
```

`customer_segment` and `customer_pet_size` are denormalised at
fixture-gen — copied from the parent customer row onto every
order line. Aito's `_recommend` requires the conditioning columns
to be on the table being scanned, and two-hop traversal
(`order_lines → orders → customers`) returns 400 in our experience.

## Tradeoffs and gotchas

- **Per-customer (`customer_id`) recommendations under-fit on
  3,000 customers**. Most customers have <20 orders; conditioning
  on `customer_id` alone gives `_recommend` no signal to work
  with. Segment + size is the right granularity for this fixture.
- **The grid doesn't update on add-to-cart**. A real product would
  re-run `_recommend` after each cart event to surface "since you
  added X, you might also like…" tiles. Demo refreshes per persona
  switch only.
- **The first tile-row dominates the visual diff**. We display 12
  tiles in a 4×3 grid; the row that most cleanly shows the
  persona effect is the top row. Tradeoff: bigger personas hide
  the long-tail differences. Pattern Explorer is the right
  surface for those.
- **`$p` rendered as "match score" is intentionally informal**.
  The technical value is P(segment | product). Production would
  rename it on the tile (e.g. "fit") or omit it entirely and
  rely on rank-order.

## What this demo abstracts away

- **A real recommendation engine** would blend multiple signals
  (collaborative + content + recency + diversity) and learn from
  click-throughs. We do segment conditioning only.
- **Cold-start behaviour**. For new customers without a segment,
  the demo defaults to Maija (cat owner). A real product would
  fall back to popularity or do a quick onboarding quiz.
- **Catalog freshness**. The fixtures are deterministic — products
  don't go out of stock, prices don't change. Production wants
  out-of-stock and price-tier filters layered on top of the
  `_recommend` result.

## Try it live

[**Open For You**](http://localhost:8500/recommendations/) and
click the persona pills above the grid. The entire grid re-renders
in <300 ms — watch the Aito panel on the right show the live
`_recommend` body that ran for the active persona.

```bash
./do dev
# → http://localhost:8500/recommendations/
```
