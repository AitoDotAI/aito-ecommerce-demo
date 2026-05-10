# ADR 0003: Aito schema, data loader, and query-method surface

**Status:** Accepted
**Date:** 2026-05-10
**Deciders:** Demo team

## Context

ADR 0002 produced four JSON files. To make them queryable from
`_predict` / `_recommend` / `_relate` / `_search` we need:

1. The Aito **schema** for the four tables, with the column types
   and link declarations that let those endpoints work end-to-end.
2. A **loader** (`src/data_loader.py`) that pushes schema + rows to
   the configured Aito DB, idempotently for "first bring-up" and
   destructively-then-replay for "reset".
3. The **query methods** on `AitoClient` that the view services
   will call. The scaffold-step client only had `get_schema()`;
   the rest are added now so the *next* view can land without
   touching `aito_client.py`.

The framework doc (`aito-demo-framework.md §3.1`) locks the
client's shape; this ADR records the type choices that are
specific to PetNord.

## Aito usage

### Column type choices, with the why

| Column | Aito type | Why |
|---|---|---|
| `products.sku` | `String`, non-null | Primary key + link target. |
| `products.name` | **`Text`** | Drives free-text `_search` and `_match`. Aito tokenises Text values so `_search { "name": "food" }` matches "Royal Canin Salmon Cat Food 2kg" because the tokeniser sees `food` as a distinct token. |
| `products.category`, `pet_type`, `brand` | `String` | Categorical — drives `_predict` (multi-field for Filling), `_relate` (Pattern Explorer / Bought Together), and `_search`'s `where`-biasing. `String` keeps a single value as one feature; `Text` would tokenise `"dry-food"` into `dry` + `food`, which is exactly the noise we don't want here. |
| `products.dietary`, `tax_class` | `String`, nullable | Nullable on purpose — drives the Product Filling demo. Aito can predict `tax_class` even when the row's other categoricals are present, because it learns from the populated 95 %. |
| `products.weight_kg` | `Decimal`, nullable | Same nullability story. |
| `products.price_eur` | `Decimal`, non-null | |
| `customers.customer_id` | `String`, non-null | PK + link target. |
| `customers.segment`, `region`, `pet_size` | `String` | `pet_size` is nullable (only dog owners + multi_pet have one). |
| `customers.tenure_months` | `Int` | |
| `orders.order_id` | `String`, non-null | PK + link target. |
| `orders.customer_id` | `String`, non-null, **link → `customers.customer_id`** | Lets `_predict` / `_relate` over `orders` reach into customer attributes via `$context.customer_id.<field>`. |
| `orders.month` | `String` | `YYYY-MM`. Kept String so `_relate` treats it categorically per month, which surfaces seasonality patterns directly. |
| `orders.total_eur` | `Decimal` | |
| `order_lines.line_id` | `String`, non-null | PK. |
| `order_lines.order_id` | `String`, non-null, **link → `orders.order_id`** | Lines join up to their order, then up to the customer (chained). |
| `order_lines.product_sku` | `String`, non-null, **link → `products.sku`** | Lines join down to their product. |
| `order_lines.qty` | `Int`, non-null | |
| `order_lines.returned` | `Boolean`, non-null | ~3 % `true`. Drives the optional Return-Risk extension and the Evaluation honest-failure case. |

The chained links (`order_lines` → `orders` → `customers` and
`order_lines` → `products`) are the join paths the For You,
Bought Together, and Pattern Explorer views all rely on.

### Query methods (`AitoClient`)

Each method maps to one Aito endpoint and takes the relevant
keyword arguments straight from the JSON body shape:

```python
class AitoClient:
    def predict(self, table, where, predict_field, *, limit=10) -> dict: ...
    def recommend(self, table, where, recommend_field, goal,
                  *, select=None, limit=8) -> dict: ...
    def relate(self, table, where, relate_field,
               *, threshold=None, limit=20) -> dict: ...
    def search(self, table, *, where=None, order_by=None,
               limit=10, offset=0, select=None) -> dict: ...
    def match(self, table, where, match_field,
              *, select=None, limit=10) -> dict: ...
    def evaluate(self, table, where, predict_field) -> dict: ...
```

`AitoError` raises on non-2xx. Methods do **not** swallow errors
or return empty results on failure (CLAUDE.md prime directive #2).

## Decision

### Loader behaviour

`./do load-data`:
- Creates schemas via `PUT /schema/<table>` (idempotent).
- Uploads rows via `POST /data/<table>/batch` in **batches of
  1 000** (the row count fits comfortably under Aito's free-tier
  per-call limit and finishes the 38 k order_lines in ~40 batches).
- Logs progress per table.

`./do reset-data`:
- Deletes tables in reverse link order (`order_lines`, `orders`,
  `customers`, `products`, `prediction_cache`).
- Then runs the same load.

Load order (links first → linkers last):
1. `products`
2. `customers`
3. `orders` (links into `customers`)
4. `order_lines` (links into `orders` and `products`)

This order matters: Aito rejects link writes whose target row
hasn't been created yet. Reverse for reset.

### Idempotency

- Re-running `./do load-data` without `--reset` **duplicates rows**
  (Aito's `/data/batch` is append-only). The loader warns the
  first time it sees a non-empty table.
- `./do reset-data` is the right verb when you want clean state.
- `prediction_cache` is dropped on reset because its keys hash the
  query body — a schema change invalidates them all.

## Acceptance criteria

- [ ] `./do reset-data` returns success against the live PetNord
      DB (`https://shared.aito.ai/db/aito-ecommerce-demo`).
- [ ] After load, `/api/schema` lists `products`, `customers`,
      `orders`, `order_lines`, and `prediction_cache`.
- [ ] A `_search` on `order_lines` returns
      `total ≈ 37 508` (= the row count from ADR 0002).
- [ ] `tests/test_scaffold.py` plus `tests/test_fixtures.py`
      still green; new `tests/test_aito_methods.py` adds
      offline-only tests for the query-method shape.

## Demo impact

This ADR doesn't ship a view but it underwrites every later one.
After this commit, every view in TASK.md can call
`predict_service.predict(...)` / `recommend_service.recommend(...)`
without any of them having to know about Aito's URL, link
declarations, or batch behaviour.

## Out of scope

- The view services themselves (Dashboard, Smart Search, …) —
  separate ADRs, one per view.
- `aito_check` query sanity assertions — added with each view in
  the same PR that introduces a new query pattern.

## Consequences

**Good:**
- One file (`src/data_loader.py`) is the table-of-contents for
  the Aito DB. An outside reader who wants "what's actually in
  Aito" can read it top-to-bottom in two minutes.
- The chained links (lines → orders → customers + lines → products)
  match how `_recommend` and `_relate` already think about
  co-purchase data. We don't have to denormalise.

**Bad:**
- Append-only `/data/batch` means a typo in fixtures requires
  `./do reset-data` to clean up. We pay a 30 s round trip each
  time. Cheaper than carrying our own dedup logic in `data_loader.py`.
- Aito's free tier rate-limits batch writes; the loader is
  serialised across tables. ~60 s end-to-end for the full PetNord
  set. Acceptable for a once-per-fixture-regen operation.

## Notes

- The `match` method exists in the client for the Smart Search
  view, but `_match` and `_search` overlap heavily. Smart Search
  will likely settle on `_search` with `where`-biasing — once
  it's built we'll know whether `_match` ever earns its line
  count.
- Schema updates are non-trivial (`PUT /schema` validates against
  existing rows). Any column addition lands in this ADR's table +
  the schema dict in the same PR, never silently in the loader.
