# Aito query cheatsheet — `aito-ecommerce-demo`

Verified Aito query patterns used in this demo. **No new pattern lands
in `src/` without first appearing here.** That rule keeps Claude (and
any other contributor) from inventing query shapes — every entry below
has been run against the live PetNord data and the response shape
confirmed.

When a pattern is also documented in the cross-demo cheatsheets in
`aito-accounting-demo` and `aito-erp-demo`, link rather than duplicate.

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

## `AitoClient` method ↔ endpoint cheat reference

| Method | Endpoint | First view that uses it |
|---|---|---|
| `predict(table, where, predict_field)` | `POST /_predict` | _(Dashboard / Product Filling)_ |
| `recommend(table, where, recommend_field, goal)` | `POST /_recommend` | _(For You)_ |
| `relate(table, where, relate_field)` | `POST /_relate` | _(Bought Together / Pattern Explorer)_ |
| `search(table, where, …)` | `POST /_search` | _(Smart Search)_ |
| `match(table, where, match_field)` | `POST /_match` | _(may not earn its line count; see ADR 0003)_ |
| `evaluate(table, where, predict_field)` | `POST /_evaluate` | _(Evaluation)_ |

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
