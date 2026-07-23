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

## Segment merge — `POST /data/<table>/optimize`

**Verified live, 2026-07-23.** Each `POST /data/<table>/batch` lands as
its own **segment**, and every read touches all of them — a 125 935-row
table loaded in 1 000-row batches is ~126 segments. `optimize` rewrites
the table as a single segment for faster reads.

```json
POST /api/v1/data/impressions/optimize
{}
```

Response: `{}` (HTTP 200). Data-preserving and idempotent — safe to
re-run. `src/data_loader.run()` calls it for every table after upload
(so `./do reset-data` optimizes automatically); `./do optimize`
re-runs it by hand on an already-loaded instance.

### Gotchas

- **Optimize invalidates the warm working set.** Rewriting the table
  drops the per-slice structures the engine built, so the first reads
  after an optimize are cold again (measured: `_recommend` warm read
  ~110–150 ms server-side, but ~2.5–3.5 s for ~1 min right after a
  full-instance optimize while it re-warms). Optimize during a
  maintenance window, not mid-demo.
- **Not a fix for cold-slice latency.** Segment-merge lowers the
  *baseline* read cost but does **not** address the working-set
  eviction that makes the first `_recommend` to an idle slice cost
  5–9 s (see `docs/notes/aito-perf-findings.md` finding #2). Different
  mechanism.

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

### `basedOn` — curate which features feed prior-feature inference

By default `_recommend` ranks candidates by
`P(goal | candidate) × prior` where `prior` factors in *every*
feature of the recommend-target table — including high-cardinality
text (name tokens) and numerics (price_eur, weight_kg) that mostly
add noise for a `customer_segment` goal. `basedOn` curates that
prior set to the features that actually carry signal:

```json
POST /api/v1/_recommend
{
  "from": "order_lines",
  "where": { "product_sku.name": { "$match": "food" }, "customer_pet_size": "small" },
  "recommend": "product_sku",
  "goal":     { "customer_segment": "dog_owner" },
  "basedOn":  ["pet_type", "brand", "dietary", "category"],
  "limit":    10
}
```

**Field names in `basedOn` are relative to the recommend target.**
For `recommend: "product_sku"`, write `["category", "brand"]` — not
`["product_sku.category"]`. The latter expands to
`product_sku.product_sku.category` and 400s.

**`basedOn: []` skips prior-feature inference entirely.** Useful
when the where + goal already give a saturated ranking and any
prior is pure overhead.

What we measured on this demo's smart-search query (median of 8
runs each, server-side response time via `x-aitoai-response-time`):

| basedOn variant                              | median server time |
|---|---|
| no-basedOn (uses ALL features)               | 158 ms             |
| `[]`                                          | 121 ms             |
| `["pet_type"]`                                | 122 ms             |
| `["pet_type", "brand", "dietary"]`            | 139 ms             |
| `["pet_type", "brand", "dietary", "category"]`| 138 ms             |

Curating to four categorical features carrying segment signal drops
latency 13 % vs the all-features default. The priors are running
either way — `basedOn` just restricts which features the prior
computation visits.

### When do priors actually move the ranking?

On this demo's broad personas (`maija = cat_owner`,
`saara = dog_owner + large`), the top-50 SKUs come back **byte-
identical** across `basedOn` variants — but that's a property of
**slice density**, not of Aito ignoring the parameter. Direct
`P(customer_segment | product_sku=X)` already has dense signal
across 600 SKUs × ~37 k order lines, so a coarser-grained prior
(category / brand / pet_type) is informationally redundant — it's a
rolled-up summary of the same signal already in the candidate
identity.

Priors *do* contribute when the direct lookup is sparse or noisy.
That happens in two situations:

- **Cold candidates** — a new SKU with few or zero rows in
  `order_lines`. Direct `P(seg | sku)` collapses to baseP; the
  category / brand prior is the only thing differentiating that SKU
  from any other unobserved one. This is the canonical "let's
  showcase priors" demo shape: stage a brand-new product, query for
  it, compare ranking with vs without `basedOn:[category, brand]`.
- **Rare context slices** — segments of the conditioning space with
  few examples. **Olli/food is exactly this case**: `dog_owner +
  customer_pet_size=small` is a thin slice. Within it, direct
  `P(seg | sku, pet_size=small)` is noisy and priors carry real
  weight. The `$why` lifts on olli/food (`tax_class:food-reduced
  0.585, name:food 0.599, pet_type:dog 0.695`) sit sub-1 only
  because those features correlate *negatively* with the goal on
  that thin slice — on Maija's or Saara's thicker slices the same
  features would have lift ≈ 1.

**Generalising to other Aito workloads**: "does `basedOn` matter for
my recommend?" collapses to "is the direct candidate-identity signal
sparse?". Long-tail catalogs (millions of SKUs, most rarely sold) ⇒
priors are important. Curated catalog with broad sales (600 SKUs ×
broad order coverage, like ours) ⇒ mostly redundant for thick
personas, decisive for thin slices and cold SKUs. Worth keeping that
lens when explaining `basedOn` to users.

### When updating fixtures or adding personas — re-validate

The 4-of-5 empirical equivalence between `basedOn` variants here
depends on slice depth. If you refresh the fixture or add a thin-
slice persona, the equivalence may break for that persona. Recipe
to re-check:

```python
# For each (persona, query), fetch top-N with and without basedOn:
# - basedOn = the curated set
# - basedOn = None (Aito default)
# Compare top-50 SKU lists + their $p. If they diverge for a new
# persona, that persona lives on a thin slice and the priors are
# moving the ranking.
```

The fixture also engineers segment ↔ brand and segment ↔ dietary
correlations within pet_type (see `BRAND_AFFINITY_BY_SEGMENT` /
`DIETARY_AFFINITY_BY_SEGMENT` in `data/generate_fixtures.py`).
That's there so when a thin-slice query *does* lean on priors, the
priors point in a sensible direction (premium brands for `dog_owner`,
mass brands for `multi_pet`). On the thick personas the priors are
still redundant, but the engineering doesn't hurt anything.

### Two query-shape gotchas around `_evaluate basedOn`

- **`_evaluate recommend` requires `group`.** The body is an
  `EvaluateGroupedQuery`, which has `group` as a required field
  alongside `evaluate`. Without it Aito returns 400
  `"field 'evaluate' must be of type 'EvaluateOperation'"`
  even though the inner body looks valid — because Aito is
  falling back to the non-grouped `EvaluateQuery` shape, which
  rejects `recommend`.

- **`_evaluate recommend` does NOT accept `basedOn`.**
  `EvaluateRecommend` properties (per `coreapi.yaml`):
  `from, where, recommend, goal, select, offset, limit`. Same at
  the outer `EvaluateGroupedQuery`. To A/B-test `basedOn` quality
  you have to either (a) use `_evaluate predict` on the same
  conditional machinery (basedOn IS accepted on `EvaluatePredict`)
  or (b) measure hit-rate client-side against held-out rows.

- **`$get` inside `$match`.** For columns with `$match`, the
  `$get` reference goes *inside* the operator:
  `"name": {"$match": {"$get": "name"}}` — not
  `"name": {"$get": "name"}` (returns 400). Plain equality `where`
  columns use the unwrapped form.

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

**Response keys mirror the field spec.** The result key is the full
`"<column>.<stat>"` string you asked for, plus sub-stats — e.g.
`"total_eur.$mean"`, `"total_eur.$mean.samples"` (the row count),
`"total_eur.$mean.variance"`, `"total_eur.$mean.standardDeviation"`.
There is **no** bare `mean` key. `$mean.samples` doubles as a free row
count for the filtered set.

**Aggregate on the table that owns the column — a link filter is a
per-row join.** `_aggregate` accepts single-hop link paths in `where`
(`{from: orders, where: {customer_id.segment: "dog_owner"},
aggregate: ["total_eur.$mean"]}` works), but Aito joins `orders →
customers` for every row: **~2.9 s** server-side here. When the same
answer can be read off a table that carries the column natively, do
that instead. The dashboard's per-segment average basket is
`mean(total_spent_eur) / mean(total_orders)` aggregated on `customers`
(which has `segment` directly) — algebraically identical (`Σspend /
Σorders`), **~20 ms** vs 2.9 s. See ADR 0024.

---

## `_batch` — many queries, one round-trip

`POST /_batch` takes a **JSON array of query bodies** and returns an
array of results **in the same order**. The win is network latency, not
server time: on the shared instance a small query is ~2 ms of work but
~100 ms on the wire, so a sequential fan-out of N reads costs N × RTT.
Collapse them:

```json
POST /_batch
[
  {"from": "customers", "where": {"segment": "dog_owner"}, "limit": 0},
  {"from": "customers", "where": {"segment": "cat_owner"}, "limit": 0}
]
// → [{"total": 1263}, {"total": 894}]   (search items return full
//    {offset, total, hits}; count items via limit:0 carry total)
```

**Gotcha — batch items are the unified query grammar, not endpoint
bodies.** A batch item accepts `from / where / search / get / predict /
recommend / relate / goal / basedOn / orderBy / select / limit / …` but
**not** `aggregate` — `{... "aggregate": [...]}` in a batch returns
`400 unexpected field 'aggregate'`. Keep `_aggregate` calls separate;
batch the plain reads (`_search`, `_relate`, `_predict`, …).

**Don't batch what's already parallel.** `_batch` runs its queries
**in order, server-side**, so batching 6 independent `_relate` calls is
*slower* than firing them through a `ThreadPoolExecutor`. Use `_batch`
to replace *sequential* round-trips (an N+1 loop), not an existing
parallel fan-out.

This killed the dashboard's two N+1 loops (per-segment counts;
per-recent-order line lookups). See ADR 0024.

---

## Recommendation by conversion KPI — `_recommend` over `impressions`

**Verified live, 2026-06-23.** The recommendation backbone (Smart
Search, For You). See ADR 0021.

The `impressions` table records one product shown to a customer in a
browsing context, with the funnel outcome (`clicked` → `added_to_cart`
→ `purchased`). That gives `_recommend` a real conversion KPI to rank
on, instead of the segment-affinity proxy the views used before:

```json
POST /api/v1/_recommend
{
  "from": "impressions",
  "where": {
    "search_query": { "$match": "food" },
    "customer_segment": "cat_owner"
  },
  "recommend": "product_sku",
  "goal":      { "purchased": true },
  "basedOn":   ["pet_type", "brand", "dietary", "category"],
  "limit":     10
}
```

Ranks products by **P(purchased = true | this customer searched this
query)**. The persona signal lives in `where` (context to condition
on), the KPI in `goal`. Live top-3 (pet × category × $p):

| Persona | Query | Top-3 | Note |
|---|---|---|---|
| Maija (cat_owner) | food | cat × wet-food × 3, p ≈ 0.61 | flips to cat |
| Saara (dog_owner + large) | food | dog × wet/dry-food × 3, p ≈ 0.46 | flips to dog |

**For You** drops the `search_query` constraint and conditions on the
persona profile alone (`where: {customer_segment, [customer_pet_size]}`),
same `goal: {purchased: true}`.

### Goal flip — engagement vs conversion

Swapping the goal field re-ranks by a different funnel stage. On
`where: {customer_segment: "cat_owner"}`:

- `goal: {purchased: true}` → cat treats + wet-food mix
- `goal: {clicked: true}`   → cat treats dominate (attention-bait:
  cheap / fun categories over-click but convert less)

The two rankings are **not** identical — that divergence is its own
demo beat (rank for revenue, not clicks).

### Calibrated rate — `_predict` the funnel field

`_recommend`'s `$p` is normalised against goal-positives; for the
absolute funnel rate use `_predict`:

```json
POST /api/v1/_predict
{
  "from": "impressions",
  "where": { "customer_segment": "cat_owner",
             "product_pet_type": "cat", "product_category": "wet-food" },
  "predict": "purchased"
}
```

Returns both classes — `false ≈ 0.784`, `true ≈ 0.216` — summing to 1.

### Gotchas

- **`where` conditions, it does not restrict the candidate set.** A
  `where: {search_query: {$match: "food"}}` makes "the customer searched
  food" the *context*; `_recommend` still ranks the whole `product_sku`
  domain, surfacing cold candidates (SKUs with no food-search rows) via
  the `basedOn` priors. Counting impressions with that filter returns a
  different set than the recommend candidates — by design.
- **`search_query` is `Text`, nullable.** Token-match with
  `{"$match": "food"}`; it's absent (null) on non-search surfaces.
- **`position` is descriptive only** — never put it in `basedOn`, or
  Aito learns "position predicts click" over content.
- **Funnel monotonicity** (`purchased ⇒ added_to_cart ⇒ clicked`) is a
  generation invariant, asserted in `./do aito-check`. Live counts:
  clicked 25 375 → cart 16 254 → purchased 10 761 (of 125 935 rows).

---

## Association-rule mining — sweep `_relate` per anchor

**Verified live, 2026-06-24.** The Basket Rules view (ADR 0022). Mines
`A → B` rules with support/confidence/lift by running the order-level
co-occurrence `_relate` (same shape as Bought Together) once per anchor
token, then ranking by lift.

```json
POST /api/v1/_relate
{
  "from": "orders",
  "where":  { "line_categories": { "$match": "dog_dryfood" } },
  "relate": "line_categories",
  "limit":  12
}
```

Read the rule metrics straight off each hit's `fs`:

- **confidence** = `fOnCondition / fCondition` = P(B in order | A in order)
- **support**    = `fOnCondition / fs.n`  (`fs.n` = total orders, 12 215)
- **lift**       = `lift`

Filter to **`lift > 1` AND `confidence ≥ 0.3` AND `fOnCondition ≥ 50`**.
The absolute-count gate is load-bearing — a thin anchor otherwise emits
spurious 100%-confidence/n=2 "rules". Rules are **directional**:
`dog dry-food → dental-treats` is 72% confident, but
`dental-treats → dog dry-food` is 94% — same lift (~2.6), different
confidence.

### Gotcha — link-traversal `_relate` does NOT condition per anchor

The tempting shape `from order_lines where {product_sku.category: …}
relate "order_id.line_categories"` returns hits, but its `fs` are
**identical across different anchors** (cat-litter and cat-treats both
report `fCondition: 12886, n: 38013`): the stats are the related
token's *global, line-granular* frequencies, not P(B | this anchor).
`n` is the order-**lines** count, so support comes out > 100%. Use the
order-bag relate above for category↔category rules; reserve link
traversal for a SKU-token bag (`orders.line_skus`, a future field).

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
