# Bought Together — order-level co-purchase via `_relate`

![Bought Together](../../screenshots/04-bought-together.png)

*Anchor product + 4 cross-sell tiles with live lift scores. Dog
dry-food → dental treats runs at 2.72× baseline — Aito's strongest
co-purchase signal in the demo dataset, the math visible on the
right panel.*

## Overview

Bought Together is the "if you liked X, here's what people who
buy X also buy" surface. The lift number on each tile is the
key data: lift > 1 means "bought together more often than chance";
lift < 1 means "bought together less often than chance" (which
Pattern Explorer surfaces; this view filters to positive lifts
only).

Aito's `_relate` operator computes lift natively. Given a `where`
clause that defines the conditioning set, `_relate` over a chosen
field returns:

```
lift = P(field=value | where) / P(field=value)
```

— the conditional probability of the field's value, given the
conditioning set, divided by its baseline probability across all
rows. Lift > 1 means "this co-occurs more than randomly".

## How it works

### The query

```python
# src/bought_together_service.py — get_bought_together()
body = {
    "from": "orders",
    "where": {"line_categories": {"$match": anchor_id}},
    "relate": "line_categories",
    "limit": 12,
}

client.relate(
    table="orders",
    where=body["where"],
    relate_field="line_categories",
    limit=12,
)
```

`anchor_id` is a token like `"dog_dryfood"` or `"cat_wetfood"`.
The `where` selects orders that contain that token in their
`line_categories` field; `relate: line_categories` asks Aito to
report which *other* tokens in `line_categories` appear unusually
often in those orders.

### Why `orders.line_categories` instead of `order_lines.category`

Aito's `_relate` is within-row — given a `where` over column A,
it tells you which values of column B in *the same row* are
over-represented. That's the natural shape for "items bought
together in the same order".

But our base data has each line as its own row in `order_lines`,
not as part of a list on `orders`. We denormalise at fixture-gen:
for each order, we build a space-separated string of
`<pet>_<category>` tokens across all its lines and store it as
a Text column (`line_categories`) on `orders`:

```
order_id   line_categories
ORD-001    dog_dryfood dog_dentaltreats dog_accessories
ORD-002    cat_wetfood cat_litter
```

With `analyzer: "whitespace"`, Aito treats each token as a
distinct value. `where: {line_categories: {$match: "dog_dryfood"}}`
selects orders where that token appears; `relate: line_categories`
returns the other tokens in those orders.

### Why hyphens get stripped from the tokens

The Text analyzer splits on hyphens. `dry-food` would index as
`dry` + `food` — two unrelated tokens. We strip hyphens at
fixture-gen (`dryfood`) so the category survives as a single
token. The lookup map in `bought_together_service.py` decodes
back to the hyphenated form for display:

```python
_CLEAN_TO_HYPHENATED = {
    cat.replace("-", ""): cat
    for cat in ("dry-food", "wet-food", "treats", "dental-treats",
                "litter", "accessories", "health", "grooming",
                "toys", "aquarium")
}
```

### Reading the lift number

For dog dry-food → dental treats at lift 2.72×, the math is:

```
P(dental_treats appears in order | dog_dryfood appears in order)  ≈  19.3%
                                /
P(dental_treats appears in order)                                 ≈   7.1%
                                =
                                                                      2.72×
```

19.3% / 7.1% = 2.72. Customers who buy dog dry-food are 2.72× more
likely to also buy dental treats than the average customer.

The chip on each tile shows `lift × support` — lift as the headline
and support (`f_on_condition` from Aito's response) as the
"out of N orders" denominator.

## Key features

### 1. Positive-only filter (lift ≥ 1.2)

```python
if lift < 1.2:
    continue   # filter neutral + protective patterns
```

Bought Together is a cross-sell surface, not a discovery surface.
"Customers who bought X *also bought* Y" is the right frame —
"customers who bought X *did NOT buy* Y" belongs in Pattern
Explorer.

### 2. Sample SKUs on every tile

Each cross-sell row carries 3 sample SKUs from the matching
`(pet_type, category)`. The tile renders one with brand + price;
hovering reveals the others. The samples are stable across cache
windows (sorted by name) so the demo doesn't churn between
loads.

### 3. Self-anchor filtered

Aito's `_relate` returns the anchor token itself (with lift 1.0).
We skip it explicitly:

```python
if not token or token == anchor_id:
    continue   # skip self
```

## Data schema

The denormalised `orders.line_categories` column is the load-
bearing piece:

```json
{
  "orders": {
    "type": "table",
    "columns": {
      "order_id":        { "type": "String" },
      "customer_id":     { "type": "String", "link": "customers.customer_id" },
      "month":           { "type": "String" },
      "total_eur":       { "type": "Decimal" },
      "line_categories": { "type": "Text", "analyzer": "whitespace" }
    }
  }
}
```

`order_lines` keeps its own canonical row-per-line structure for
Smart Search and For You. The denormalised Text column on `orders`
is a *parallel* representation for `_relate` to operate on — same
data, different shape.

## Tradeoffs and gotchas

- **Within-row vs. cross-row co-occurrence**. Aito's `_relate` is
  fundamentally within-row. The denormalisation moves "items
  bought together" from "rows in `order_lines` that share an
  `order_id`" (cross-row) to "tokens in a `line_categories`
  Text value" (within-row). Cost: an extra column at load time
  and a token-string lookup table at the service layer.
- **Lift's small-denominator inflation**. Aquarium → aquarium-
  health hits ~17× live because aquarium is a closed niche
  (low base rate, small denominator). Mathematically correct,
  visually misleading. Bought Together caps the tile chip
  rendering at 5× for readability; Pattern Explorer renders the
  raw number.
- **Anchor token vs. display label**. `dog_dryfood` (token) →
  "Dog dry-food" (display). We keep both, decoded via the
  `_CLEAN_TO_HYPHENATED` map. Confusing in code; necessary at
  the data layer.
- **Order-level lift isn't basket-position lift**. We say
  "bought together" but technically it's "appear in the same
  order". A real basket-analytics view would also model order
  sequence ("after they put X in cart, what did they add
  next?") — that needs event-level data the fixture doesn't
  generate.

## What this demo abstracts away

- **Personalised cross-sell**. The lift numbers here are
  population-wide. A real product would condition on the active
  customer's segment ("among large-dog-owners specifically,
  what's the dry-food → dental-treats lift?") — same `_relate`
  shape with an extra `where` clause.
- **Time-windowed lift**. Holiday season shifts cross-sell
  patterns. Production would slice on `month` ranges.
- **SKU-level pairs**. We anchor and target on `<pet>_<category>`
  pairs because the SKU-level matrix is sparse on a ~700-product
  catalog. Larger catalogs (and longer histories) make SKU-pair
  `_relate` viable.

## Try it live

[**Open Bought Together**](http://localhost:8500/bought-together/)
and pick an anchor from the row above. The four tiles re-render
in ~200 ms with fresh lift numbers; the Aito panel on the right
shows the `_relate` body that produced them.

```bash
./do dev
# → http://localhost:8500/bought-together/
```
