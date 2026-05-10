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
