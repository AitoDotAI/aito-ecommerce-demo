# Aito query cheatsheet — `aito-ecommerce-demo`

Verified Aito query patterns used in this demo. **No new pattern lands
in `src/` without first appearing here.** That rule keeps Claude (and
any other contributor) from inventing query shapes — every entry below
has been run against the live PetNord data and the response shape
confirmed.

When a pattern is also documented in the cross-demo cheatsheets in
`aito-accounting-demo` and `aito-erp-demo`, link rather than duplicate.

**Performance and operational gotchas** — TLS handshake costs,
working-set eviction on the shared instance, `basedOn` schema
constraints, and other things that surfaced while making the demo
fast — live in `docs/notes/aito-perf-findings.md`. The query-shape
patterns below remain the same regardless.

---

## Index

| View | Endpoint | Notes |
|---|---|---|
| _(schema bring-up)_ | `PUT /schema/<table>` | Idempotent. Replaces the table definition; rejects column-type changes against existing rows. |
| _(schema bring-up)_ | `POST /data/<table>/batch` | Append-only. The loader uses batches of 1 000. |

Per-view sections are added with each view in TASK.md's build order.

---

## Schema upload — `PUT /schema/<table>`

Used by `src/data_loader.py` on `./do load-data`.

```json
PUT /api/v1/schema/products
{
  "type": "table",
  "columns": {
    "sku":        { "type": "String",  "nullable": false },
    "name":       { "type": "Text",    "nullable": false },
    "category":   { "type": "String",  "nullable": false },
    "pet_type":   { "type": "String",  "nullable": false },
    "brand":      { "type": "String",  "nullable": false },
    "price_eur":  { "type": "Decimal", "nullable": false },
    "weight_kg":  { "type": "Decimal", "nullable": true },
    "dietary":    { "type": "String",  "nullable": true },
    "tax_class":  { "type": "String",  "nullable": true }
  }
}
```

Response: `{ "ok": true }` (HTTP 200/201).

### Links

`order_lines` declares two links:

```json
{
  "order_id":    { "type": "String", "nullable": false, "link": "orders.order_id" },
  "product_sku": { "type": "String", "nullable": false, "link": "products.sku" }
}
```

With these in place, `_recommend product_sku from order_lines where {"orders.customer_id": "..."}`
reaches through `order_lines.order_id → orders.customer_id` without
us hand-rolling joins.

### Gotchas

- **String vs Text.** `"category"` is `String`, not `Text`. If it
  were Text, Aito would tokenise `"dry-food"` into `dry` + `food`,
  which exactly defeats the categorical-conditional probabilities
  Bought Together depends on.
- **`name` is `Text`** so `_search { "name": "food" }` matches
  "Royal Canin Salmon Cat Food 2kg" via the `food` token. Don't
  flip `name` to `String` — the rank flip in Smart Search depends
  on token-overlap scoring.
- **Nullable for Filling pile.** `weight_kg`, `dietary`, and
  `tax_class` are nullable because the Product Filling demo's
  input pile lives in the ~5 % of products that have those
  fields nulled. The non-null products are the *training* set
  Aito learns from.

---

## Data upload — `POST /data/<table>/batch`

```json
POST /api/v1/data/products/batch
[
  { "sku": "SKU-PT-0001", "name": "Royal Canin Chicken Dog Food 4kg",
    "category": "dry-food", "pet_type": "dog", "brand": "Royal Canin",
    "price_eur": 28.4, "weight_kg": 4, "dietary": "puppy",
    "tax_class": "food-reduced" },
  ...
]
```

Append-only. Re-running `./do load-data` without `--reset` duplicates
rows. `./do reset-data` is the right verb when you need clean state.

Batch size: 1 000 rows. The whole PetNord dataset (~52 k rows across
four tables) lands in ~60 s including network round-trip.

---

## Free-text matching on a `Text` column — `_search` with `$match`

**Verified live, 2026-05-10**, against
`shared.aito.ai/db/aito-ecommerce-demo`.

```json
POST /api/v1/_search
{
  "from": "products",
  "where": { "name": { "$match": "food" } },
  "limit": 10
}
```

Response: `{ "hits": [...], "offset": 0, "total": 385 }`.

### Gotcha — `$match` is required for token matching

`where: { "name": "food" }` (plain-string form) returns
`total = 0` even when 385 rows contain the token. Aito's plain-
string equality on a `Text` column is whole-string equality, not
tokenised matching. **Use `{ "$match": "..." }` for token search.**

This is the load-bearing syntax behind the Smart Search baseline
("food" → 10 results across cat/dog/aquarium food). The customer-
context re-rank (the rank-flip demo moment) needs a `$context` form
that we have NOT yet pinned — first attempt with
`order_lines.{orders.customers.segment}` returned 400. The Smart
Search view ADR will record the verified shape when we build it.

---

## Predictive re-ranking — `_recommend` with `goal: { segment }`

**Verified live, 2026-05-11**, against
`shared.aito.ai/db/aito-ecommerce-demo`.

```json
POST /api/v1/_recommend
{
  "from": "order_lines",
  "where": {
    "product_sku.name": { "$match": "food" }
  },
  "recommend": "product_sku",
  "goal": {
    "customer_segment": "dog_owner",
    "customer_pet_size": "large"
  },
  "limit": 10
}
```

### Why this shape

Ranks products matching the query string by
**P(this customer-segment | a line containing this product)**. Products
that the target segment has historically bought float to the top because
their conditional probability under the segment is high.

### Gotchas

- **`goal: {returned: False}` washes out the customer-context signal.**
  `returned` is uniform at ~3 % across all products, so the resulting
  ranking is essentially baseline. Use a goal that *uses* the
  customer context (`customer_segment`, `customer_pet_size`).
- **Single-hop link traversal only.** From `order_lines`, Aito reaches
  `order_id.<orders col>` and `product_sku.<products col>` — but
  `order_id.customer_id.<customers col>` returns 400. The fix is
  schema-level: denormalise the cross-table attribute down to the
  line ( `customer_segment` / `customer_pet_size` on `order_lines`).
- **Per-customer (`order_id.customer_id`) conditioning under-fits**
  with our 3 000-customer dataset — single-row priors are too thin.
  Segment-level conditioning gets the visible flip.
- **Multi-field `goal` does NOT behave like an AND.** A
  `goal: {customer_segment: "dog_owner", customer_pet_size: "small"}`
  returns the same cat-heavy result as `goal: {customer_pet_size:
  "small"}` alone, because `pet_size=small` is shared with multi-pet
  households (which lean cat in our fixture) and Aito's combined-goal
  ranking collapses onto the dominant signal. The reliable shape is
  to **split the constraints**: pet_size in `where`, segment in `goal`.

```json
POST /api/v1/_recommend
{
  "from": "order_lines",
  "where": { "customer_pet_size": "small" },
  "recommend": "product_sku",
  "goal":  { "customer_segment": "dog_owner" },
  "limit": 10
}
```

With this split, Olli (dog_owner+small) returns all-dog accessories /
grooming / health products instead of being mis-grouped with the
multi-pet+small cat-heavy pool.

### Live numbers (Smart Search demo path)

| Persona              | Top-3 pet × category | Note |
|---|---|---|
| Maija (cat_owner)    | cat × dry-food × 3   | p ≈ 0.91 — strongly cat |
| Saara (dog_owner+large) | dog × dry-food × 3 | p ≈ 0.51 — narrow pet_size constraint reduces absolute p |
| Aquarium owner       | cat × dry-food × 3   | p ≈ 0.05 — aquarium customers rarely buy "food"-named products; ranking is noise |

### `basedOn: []` — skip prior-feature inference

By default `_recommend` ranks candidates by
`P(goal | candidate) × prior` where `prior` factors in every feature
of the recommend-target table. When the `where` clause already
narrows the candidate pool tightly, that prior is noise we don't
want — it muddies the ranking *and* makes the request slower.

Pass `basedOn: []` to skip prior-feature inference entirely:

```json
POST /api/v1/_recommend
{
  "from": "order_lines",
  "where": { "product_sku.name": { "$match": "food" }, "customer_pet_size": "small" },
  "recommend": "product_sku",
  "goal":     { "customer_segment": "dog_owner" },
  "basedOn":  [],
  "limit":    10
}
```

**Field names in `basedOn` are relative to the recommend target.**
For `recommend: "product_sku"`, write `["category", "brand"]` — not
`["product_sku.category"]`. The latter expands to
`product_sku.product_sku.category` and 400s.

When to use:
- The `where` already restricts the candidate pool meaningfully
  (a `$match` on a name column, a category equality, etc.).
- The story you're telling is "rank by `P(goal | candidate)`" and
  not "rank by `P(goal | candidate)` weighted by how typical the
  candidate is in the dataset".

When *not* to use: For-You style queries where the prior is the
product itself ("things people like you bought that didn't get
returned") — there the implicit feature priors *are* the signal.

Empirical impact on Smart Search (3 runs per cell, median):
- Top-10 hit-set Jaccard vs the no-`basedOn` baseline:
  1.00 for narrow queries (toy/collar/treat), 0.54 for `food/olli`
  (a benign top-3 reshuffle).
- Cold latency: 10–30 % faster, larger swing on a cold Aito.

### Does `basedOn: []` cost accuracy? Two evaluation shapes

A reasonable concern: if `basedOn: []` were strictly free, the
default would already be `[]`. Empirically, it isn't costing us
accuracy — but verifying that takes two different shapes because
**Aito's `_evaluate` does not accept `basedOn` on
`_recommend`**.

`EvaluateRecommend` properties (per `coreapi.yaml`):
`from, where, recommend, goal, select, offset, limit`. No
`basedOn`. Same at the outer `EvaluateGroupedQuery` level. So
the comparison has to happen by another route.

**Path 1 — `_evaluate predict` as a proxy.** `_evaluate predict`
*does* accept `basedOn`, and predicting `product_sku` from the
same `where` columns exercises the same conditional probability
machinery `_recommend` uses internally:

```json
{
  "testSource": {"from": "order_lines", "limit": 500},
  "evaluate": {
    "from": "order_lines",
    "where": {
      "product_sku.name":  {"$match": {"$get": "product_sku.name"}},
      "customer_pet_size": {"$get": "customer_pet_size"}
    },
    "predict": "product_sku",
    "basedOn": []
  }
}
```

Live numbers (`shared.aito.ai/db/aito-ecommerce-demo`, n=500):

| variant            | accuracy | baseAcc | gain    | meanRank | rankGain | latency |
|---|---|---|---|---|---|---|
| no-basedOn         | 0.7920   | 0.0000  | +0.7920 | 0.25     | 623.79   | 31 s    |
| basedOn: []        | 0.7920   | 0.0000  | +0.7920 | 0.25     | 623.79   | 23 s    |
| basedOn: [cat,pet] | 0.0060*  | 0.0000  | +0.0060 | 596.57   | 27.46    | 52 s    |

*\*Without `$match` — included to show that naming features in
`basedOn` can actively hurt when they aren't the strongest signal.*

**Path 2 — direct hit-rate on `_recommend`.** Because `_evaluate`
can't toggle `basedOn` on the actual recommend shape, run it
client-side: sample held-out lines, run both variants of
`_recommend`, count how often the truth lands in top-K.

```python
sample = client._request("POST", "/_search", json={
    "from": "order_lines",
    "where": {"$index": {"$mod": [40, 0]}},
    "select": ["product_sku", "product_sku.name",
               "customer_pet_size", "customer_segment"],
    "limit": 150,
}).get("hits", [])

def rank_of_actual(based_on, row):
    body = {
        "from": "order_lines",
        "where": {
            "product_sku.name": {"$match": row["product_sku.name"]},
            "customer_pet_size": row["customer_pet_size"],
        },
        "recommend": "product_sku",
        "goal": {"customer_segment": row["customer_segment"]},
        "limit": 50,
    }
    if based_on is not None:
        body["basedOn"] = based_on
    res = client._request("POST", "/_recommend", json=body)
    for i, h in enumerate(res.get("hits", [])):
        if h.get("sku") == row["product_sku"]:
            return i + 1
    return None
```

Live numbers (n=150, recommend limit=50):

| variant      | hit@1  | hit@5  | hit@10 | median rank | mean rank | total time |
|---|---|---|---|---|---|---|
| no-basedOn   | 0.840  | 1.000  | 1.000  | 1.0         | 1.19      | 15.0 s     |
| basedOn: []  | 0.833  | 1.000  | 1.000  | 1.0         | 1.20      | 13.3 s     |

The 0.7 pp difference on hit@1 is one row out of 150 — a single
tie-break flipping at rank 1 vs 2. Hit@5, hit@10, and mean rank
are indistinguishable. Both evaluation paths agree: on this
dataset, `basedOn: []` is genuinely free.

If the smart-search query shape changes (different `where`
columns, looser candidate pool, different goal), re-run both
paths — `_evaluate predict` to check the conditional machinery,
and the client-side hit-rate to verify the actual `_recommend`
ranking quality.

**Two query-shape gotchas surfaced along the way:**

- `$get` inside `$match`. For columns with `$match`, the
  `$get` reference goes *inside* the operator:
  `"name": {"$match": {"$get": "name"}}` — not
  `"name": {"$get": "name"}` (returns 400). Plain equality `where`
  columns use the unwrapped form.

- `_evaluate recommend` requires `group`. The body is an
  `EvaluateGroupedQuery`, which has `group` as a required field
  alongside `evaluate`. Without it, you get 400
  `"field 'evaluate' must be of type 'EvaluateOperation'"`
  even though the inner body looks valid — because Aito is
  falling back to the non-grouped `EvaluateQuery` shape, which
  rejects `recommend`.

---

## Order-level co-occurrence — denormalised Text + `_relate`

**Verified live, 2026-05-11.** The Bought Together pattern.

```json
POST /api/v1/_relate
{
  "from": "orders",
  "where": { "line_categories": { "$match": "dog_dryfood" } },
  "relate": "line_categories",
  "limit": 12
}
```

Returns hits with `condition`, `related`, `lift`, `fs`
(`f`, `fOnCondition`), `ps`. The most useful read:

| `related.line_categories.$has` | `lift` | Reading |
|---|---|---|
| `dog_dryfood`        | 2.88× | self — same token appears in same row |
| `dog_dentaltreats`   | 2.72× | strong positive cross-sell |
| `cat_wetfood`        | 0.27× | strong protective (anti-correlated) |

### How it works

`orders.line_categories` is a denormalised Text column listing
each order's lines as `<pet>_<category>` tokens, hyphens
stripped. Aito tokenises Text on whitespace, so each
underscored pair is one feature. `_relate` over a Text field
returns lift of token co-occurrence within the row.

### Why denormalise

Aito's `_relate` over `order_lines` does **line-level**
(within-row) relation. The natural "order-level co-occurrence"
shape needs a reverse-link from `orders` back into
`order_lines` — every form we tried returned 400:

- `order_id.order_lines.product_sku.category` ❌
- `$context: {order_id: {order_lines: {...}}}` ❌
- `order_id.product_sku.category` ❌

Denormalising the aggregate (a Text field on `orders` listing
all its lines' tokens) keeps the `_relate` simple and the data
small. Same trick used elsewhere: ADR 0006 for
`customer_segment` / `customer_pet_size`.

### Hyphen gotcha

Aito tokenises Text on whitespace **and on hyphens**. Plain
`<pet>__<category>` returns `dog__dry` / `food` as separate
tokens for `dry-food`. Strip hyphens at fixture-gen time so
each pair stays one indivisible token:

```python
clean_cat = product.category.replace("-", "")
token = f"{product.pet_type}_{clean_cat}"
```

---

## `$why` highlight — full sentence with marked tokens

To surface **which tokens of a Text column drove the prediction**,
add a `highlight` block to `$why` in the `_predict` select. Aito
returns the **full source string** with sentinel tags around the
matched spans — drop straight into the WhyPopover as "the sentence,
with the predicting feature emphasised":

```python
# src/aito_client.py — `predict()` sets all four sentinels
"select": [
    "$p", "feature",
    {"$why": {
        "highlight": {
            "posPreTag":  "«",   # lift > 1 spans  (drives prediction)
            "posPostTag": "»",
            "negPreTag":  "‹",   # lift < 1 spans  (protective)
            "negPostTag": "›",
        }
    }},
]
```

The response carries highlights **per factor** (one entry per
`relatedPropositionLift` node), not in a top-level `highlights`
array:

```json
{
  "type": "relatedPropositionLift",
  "proposition": { "$and": [
    {"text": {"$has": "Package"}}, {"text": {"$has": "arrived"}}
  ]},
  "value": 5.28,
  "highlight": [
    {
      "score": 4.80,
      "field": "$context.text",
      "highlight": "«Package» «arrived» late. The seal was broken."
    }
  ]
}
```

Rendering rules (mirrors `aito-accounting-demo`'s
`04-why-highlight-shape.md`):

- Strip the `$context.` prefix when displaying the field name.
- The `highlight` string is **the full source text** with the
  matched tokens wrapped — render it verbatim with the sentinels
  split into emphasised spans (`renderMarkedText` in
  `WhyPopover.tsx`).
- Highlights are per-field; for compound `$and` propositions the
  list may contain one entry per matched column. Pick the
  top-`score` entry.
- Numeric / String / Decimal columns have **no highlight** —
  fall back to "When field is value" rendering.

**Gotcha**: `highlight` is expensive — Aito has to mark every
candidate. With `limit: 20` and long text it can run > 30 s.
Keep `limit ≤ 5` for highlighted predicts unless you're behind a
cache.

---

## `_estimate` vs `_predict` — when to use which

`_predict` returns ranked discrete hits with `$p` per hit — right
for classification or "what's the most-probable specific value".
`_estimate` returns the **expected value** of a numeric field
given the `where` context — right for continuous regression
("what's the mean / typical units, price, revenue").

For `units_sold` on the `monthly_sales` panel:

```json
{
  "from": "monthly_sales",
  "where": {
    "product_sku": "SKU-PT-0042",
    "month": "2026-05",
    "pet_type": "dog",
    "category": "dry-food",
    "season": "spring"
  },
  "estimate": "units_sold",
  "select": ["estimate", "why"]
}
```

Response:

```json
{
  "estimate": 3.76,
  "why": {
    "type": "weightedAverage",
    "components": [
      { "weight": 1.0, "value": { ...neighborContext tree... } }
    ]
  }
}
```

**Key shape differences vs `_predict`:**
- No `hits` list, no `$p` per hit — `estimate` is a single number.
- `why` is a `weightedAverage` of `neighborContext` nodes (K-NN);
  each neighbor has its own per-feature `regression` shifts +
  `mean centering` + `input.residual`. ~20-30 neighbors typical.
- For popover rendering, **walk only the top-weighted neighbor's
  subtree** — otherwise the popover collects N × leaves and reads
  noisy. See `src/why_processor.py:process_estimate_why`.

**`model: "regression"` variant** swaps K-NN for a linear-
regression model with cleaner per-field contribution explanations
(no nested per-neighbor scaffold). Less neighbor-style "this is
like that case", more "field X shifts the estimate by Y%".

**Caching is important** — K-NN `_estimate` scans the whole table
per call. For our Demand view (25 SKUs × ~80 ms each warm =
~2 s) the 30-min cache is essential. Cold-load batches without
caching would saturate Aito's rate limit fast.

---

## `_aggregate` — server-side mean / min / max / std

For per-row stats (e.g., price band per SKU) Aito has
`_aggregate` — same `from / where` body but with an `aggregate`
list of `<field>.<stat>` keywords.

```json
{
  "from": "price_history",
  "where": {"product_sku": "SKU-PT-0001"},
  "aggregate": [
    "price_eur.$mean",
    "price_eur.$min",
    "price_eur.$max"
  ]
}
```

Response:

```json
{
  "mean": 5.92,
  "min":  4.48,
  "max":  6.61,
  "mean.samples":           19,
  "mean.variance":          0.49,
  "mean.standardDeviation": 0.70,
  "mean.standardError":     0.16
}
```

**Gotcha**: `$standardDeviation` is **not** a separate keyword —
requesting `"price_eur.$standardDeviation"` returns a 400. Aito's
`$mean` already returns `mean.variance` and `mean.standardDeviation`
in the same response. Same for `$min` / `$max` (no `samples`,
just the value).

**Rate-limit caveat**: fan-out of N parallel `_aggregate` calls
(one per SKU) trips Aito's rate limiter at high N. For the
Price Intelligence view we settled on a hybrid: bulk
`_search` fetch + Python aggregation for the catalog-wide
outlier scan, plus one `_aggregate` call for the per-SKU
drilldown displayed in the Aito panel. See ADR 0016.

---

## `AitoClient` method ↔ endpoint cheat reference

| Method | Endpoint | First view that uses it |
|---|---|---|
| `predict(table, where, predict_field)` | `POST /_predict` | _(Dashboard / Product Filling)_ |
| `recommend(table, where, recommend_field, goal)` | `POST /_recommend` | _(For You)_ |
| `relate(table, where, relate_field)` | `POST /_relate` | _(Bought Together / Pattern Explorer)_ |
| `search(table, where, …)` | `POST /_search` | _(Smart Search)_ |
| `match(table, where, match_field)` | `POST /_match` | _(may not earn its line count; see ADR 0003)_ |
| `evaluate(table, where, predict_field)` | `POST /_evaluate` | _(Evaluation)_ |
| `estimate(table, where, estimate_field)` | `POST /_estimate` | _(Demand / Inventory — continuous regression)_ |
| `aggregate(table, where, aggregate_fields)` | `POST /_aggregate` | _(Price — per-SKU stats)_ |

Each method's body shape is asserted offline in
`tests/test_aito_methods.py`. The first time a view consumes a
method against the live data, the call lands here as a worked
example with the actual response shape pasted in.

---

## Reference

- API docs: <https://aito.ai/docs/api/>
- Query language: <https://aito.ai/docs/api/query-language>
- Sister cheatsheets:
  - `aito-accounting-demo/docs/aito-cheatsheet.md`
  - `aito-erp-demo/docs/aito-cheatsheet.md`
