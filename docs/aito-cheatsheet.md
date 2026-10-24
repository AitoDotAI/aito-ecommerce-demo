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
The current schema holds only what a shop observes (ADR 0033): older
sections that show `customer_*` trait columns are dated history; start
from "Recommendation by conversion KPI" and "Only what a shop observes"
for the shapes the views send today.

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

`$match` requires EVERY query token in the field (AND). Smart Search
used it until ADR 0026 and returned nothing for 70 % of a judged query
set ("food for an old dog", misspellings, Finnish/Swedish). For search,
rank instead of filter: see the next section.

---

## Ranking by text, and by text × prediction — `$similarity`, `$multiply`

**Verified live, 2026-09-27**, API v2, `shared.aito.ai` (v2.10.3).
Used by Smart Search (`src/search_service.py`, ADR 0026).

**Text relevance (BM25), no filter:**

```json
POST /_search
{ "from": "products",
  "orderBy": { "$similarity": { "name": "food for an old dog" } },
  "select": ["sku", "name", "$score"], "limit": 10 }
```

- `$score` is the lift `exp(θ·bm25)`, θ 0.33 by default. **Exactly 1.0
  means no query word matched.**
- **Gotcha: ties come back in table order.** For a query matching
  nothing, every row ties at 1.0 and you get the first rows of the
  table. Here that's dog dry food, which looked like a perfect answer
  to "hundmat". Drop `$score == 1.0` rows.
- `$similarity` is valid in `orderBy`, not in `select` (400).

**Text × purchase probability, in one query:**

```json
POST /_search
{ "from": "impressions",
  "get": "product_sku",
  "where": { "context.customer": "CUST-00001" },
  "orderBy": { "$multiply": [
    { "$p": { "$context": { "purchased": true } } },
    { "$similarity": { "name": "food" }, "theta": 4.0 } ] },
  "select": ["sku", "name"], "limit": 10 }
```

- `get` ranks the rows a link points to (products) while `where` and
  `$p` read the `from` table (impressions). Every product is a
  candidate: `total` is the catalogue size.
- `where` conditions `$p`: the same query flips from cat to dog products
  between customers (`context.customer` is two links from `impressions`,
  ADR 0033). `./do aito-check` pins it. A `where` on the linked table's
  fields does **not** filter what `get` returns (see "Why a product, and
  search, in the Shop" below).
- **The θ on `$similarity` sets how much the words count against the
  prediction.** At the default 0.33 the prediction drowned the text (a
  cat owner's "dog food" returned cat food). Measure it on a judged set;
  4.0 here, chosen out of sample.
- **Gotcha: the selected `$p` is the whole product**, not a probability
  (values ≫ 1). Don't display it as a percentage.
- When no word matches, every `$similarity` is 1.0 and the ranking is
  `$p` alone. Detect it (e.g. the BM25 query above returned nothing)
  and say so in the UI.

## Predictive re-ranking — `_recommend` with `goal: { segment }`

**Verified live, 2026-05-11**, against
`shared.aito.ai/db/aito-ecommerce-demo`.

> **History (ADR 0033).** The `customer_*` columns below were copies of
> the data generator's hidden traits on `order_lines` and `impressions`.
> ADR 0033 removed them: tables hold only what a shop observes, and a
> query reaches the customer through two links (`context.customer.*`,
> `order_id.customer_id.*`; see "Only what a shop observes" below). No
> view sends these shapes now; they are kept for the `goal` and
> `basedOn` gotchas, which still hold.


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
- **Single-hop link traversal only (v1, 2026-05).** From `order_lines`,
  Aito reached `order_id.<orders col>` and `product_sku.<products col>`,
  but `order_id.customer_id.<customers col>` returned 400, so the
  attribute was denormalised onto the line. **On v2 two links work**
  (see "Only what a shop observes" below); the copies are gone.
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

### Hard candidate filter vs. context — Smart Search's shape until ADR 0026

Superseded: Smart Search now ranks with `$multiply` and no filter (see
"Ranking by text, and by text × prediction" above), and ADR 0033 removed
`customer_segment` and moved `search_query` to `contexts`. This shape is
kept because the filter/context split still applies to `_recommend`
elsewhere: the Shop's grid filters on `product_sku.pet_type` and
conditions on `context.*`.

The Smart Search path of ADR 0021 recommended over `impressions`
with `goal: {purchased: true}`, and separates two roles the query text
plays:

```json
POST /api/v1/_recommend
{
  "from": "impressions",
  "where": {
    "product_sku.name": { "$match": "dog food" },
    "search_query": "dog food",
    "customer_segment": "dog_owner"
  },
  "recommend": "product_sku",
  "goal": { "purchased": true },
  "basedOn": ["pet_type", "brand", "dietary", "category"],
  "limit": 10
}
```

- **`product_sku.name: {$match: query}` is a hard filter**, not a ranking
  hint. It bounds the *candidate set* to products whose name matches the
  query tokens, so a thin funnel slice (e.g. `dog_owner + small`, where
  priors dominate) can never surface a cross-pet product. The ranking
  only reorders what survives the filter. Without it, a broad query like
  "food" leaks cat products into a dog persona's list.
- **`search_query: query` is plain context evidence** — the exact value,
  no `$match`. The token work is already done by the name filter, so this
  stays an exact-match signal on the impressions column. In **API v2**
  drop the `$match` on the candidate filter and use v2's native search
  filter instead (ADR 0025); `search_query` stays a plain value on both.
- Guarded by `test_smart_search_name_filter_excludes_cross_pet_products`
  in `test_aito_check.py`: *every* hit must be on-pet, not just the top
  few.

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

(The fixture's `BRAND_AFFINITY_BY_SEGMENT` / `DIETARY_AFFINITY_BY_SEGMENT`
tables, mentioned here before, were never used and ADR 0032 deleted
them.)

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

### Choosing the held-out rows: `test` and `train`

- **Random rows:** `"test": {"$sample": {"n": 200, "seed": 0}}`. Never
  `testSource.limit`, which takes the HEAD of the table. Ordered
  tables make the head unrepresentative (here it turned a working
  model into "accuracy 0.06, baseline 0.0").
- **Time series:** hold out the latest period and train on the rest.
  Otherwise the model learns from a SKU's later months while predicting
  an earlier one:

  ```json
  {"train": {"month": {"$not": "2026-04"}},
   "test":  {"month": "2026-04"},
   "evaluate": {"from": "monthly_sales", "where": {…}, "predict": "units_bucket"},
   "select": ["accuracy", "baseAccuracy", "n"]}
  ```

  `train` is honoured: training on one old month changes the score
  on the same test rows (`tests/test_aito_check.py` pins it). Leave
  the time column itself out of `where`. The test month is a value no
  training row has, so it carries no evidence.
- **Numeric targets:** the API spec documents `_evaluate` over
  `estimate` (`select: ["mae", "rmse", "r2"]`), but v2.10.3 rejects it
  on `/api/v1` and `/api/v2` alike with 400 "missing
  'evaluate.predict'". Until it lands, bucket the number into ranges
  and `predict` the range. Don't score `_estimate` against rows
  still in the table: `_estimate` has no train filter, so a
  held-out row informs its own forecast.

---

## Reading a `_relate` hit — one shape on v1 and v2

**Verified live, 2026-09-29**, API v2, `shared.aito.ai` (v2.10.3).

The value a hit is about lives in `related`, and its shape differs by
version and column type:

| | v1 | v2, Text column | v2, String column |
|:--|:--|:--|:--|
| `related` | `{"f": {"$has": v}}` | `{"f": {"$has": v}}` | `{"f": v}` (bare) |

`src/aito_compat.py` wraps the bare form, and `related_value(hit, f)` reads
the value and **raises** on anything else. Don't parse `related` by hand
with a silent `continue`: when v2 returned bare values, readers doing that
kept 0 rows, and three panels (Churn drivers, Demand seasonality, Price
sweet spots) went empty with no error.

Each hit's `fs` carries the counts behind its lift (`fOnCondition`,
`fCondition`, `f`, `n`). Use them before calling a lift a finding: a
large lift on a handful of rows is noise. `src/price_bands.py`
`lift_interval` gives a 95 % interval from those counts (log relative
risk).

---

## Field-form `_relate` through a link, on a Boolean, and on Text

**Verified live, 2026-10-13**, API v2, test env `shoppers` on
`shared.aito.ai` (2.11.4). The Shop analytics view (ADR 0031).

```json
POST /_relate
{"from": "impressions", "where": {"purchased": true},
 "relate": ["product_sku.rating_band"], "limit": 50}
```

| `relate` | column type | a hit's `related` | example |
|:--|:--|:--|:--|
| `product_sku.rating_band` (through the link) | String on `products` | `{"product_sku.rating_band": {"$has": "1-2"}}` | 0.789×, `fOnCondition` 923 of `fCondition` 12,135; `f` 11,525 of `n` 115,690 |
| `product_category` (denormalised copy) | String | `{"product_category": {"$has": "dry-food"}}` | identical hits and counts to `product_sku.category` |
| `just_bought` | Boolean | `{"just_bought": {"$has": true}}`, and a second hit for `false` | 0.483× on 40 of 12,135 |
| `customer_diet_rule` (removed by ADR 0033; now `context.customer.diet`) | nullable String | one hit per non-null value; no hit for null | 4 hits (grain-free, sensitive, senior, puppy) |
| `search_query` (now `context.search_query`) | Text, whitespace | `{"search_query": {"$has": "food"}}`, one hit per word | 99 words on search impressions |

So the link form works on v2, and on every column type the hit reads as
`related.<field>.$has` once `normalize_response` has wrapped the bare
String form; `related_value` reads all of them. Over `order_lines`, a
season is `order_id.month: {"$or": [months]}` (see Demand) and the
product's dietary line is `product_sku.dietary`: grain-free households'
lines are 3.08× grain-free (1,171 of 2,003).

The interval comes from the four counts (`lift_interval` in
`src/price_bands.py`). These counts are rows, and one customer's rows
are not independent, so Shop analytics divides them by a design effect
before use (see "Rows per customer" below). It also tests a section's
lifts at a Bonferroni level (`src/lift_rows.py`).

---

## A sub-population's lift: two `_relate`s, divided

**Verified live, 2026-10-13**, test env `shoppers`. Shop analytics'
search words.

`_relate`'s lift always compares against the whole table. Restricting
the `where` to a sub-population (`surface: "search"`) changes the
numerator, not the baseline:

```json
{"from": "impressions", "where": {"surface": "search", "purchased": true},
 "relate": ["search_query"], "limit": 500}
```

Every word comes out about 2.5× ("food" 2.76×, `f` 17,087 of `n`
115,690), because only search impressions carry a query: a `_search`
for `search_query: {$match: "food"}` counts 17,087 with or without
`surface: "search"`. "food" actually converts at 11.2 % against the
search average of 11.7 %.

A nested `from` would set the population, but `_relate` answers 501 to it
on 2.11.4 (see `docs/verification/shoppers-data-prereg.md`). So send the
same `_relate` without `purchased` too, and divide the counts:

```
bought = where {surface: search, purchased: true}  → fOnCondition_w, fCondition = search purchases (4,697)
shown  = where {surface: search}                   → fOnCondition_w, fCondition = search impressions (40,278)

lift_w = (bought_w / 4,697) / (shown_w / 40,278)
```

`lift_interval(lift_w, bought_w, 4697, shown_w, 40278)` gives its
interval, before the clustering and multiple-test corrections below.
"food": 0.96×; "cheese": 2.24× (71 of 272); "whitefish": 0.62× (78 of
1,078). Every word bought from search must also be in `shown`, or
`src/search_words.py` raises. Use `limit` above the vocabulary and treat
a full page as an error.

Words with identical counts may be one phrase. A `_search` with `$and`
of `$match`es on the same Text column counts the searches holding all of
them, and `select` returns one to read the word order from:

```json
{"from": "impressions", "limit": 1, "select": ["search_query"],
 "where": {"$and": [{"surface": "search"},
                    {"search_query": {"$match": "algae"}},
                    {"search_query": {"$match": "wafers"}}]}}
```

"algae" 154, "wafers" 154, both 154: one phrase. "blend" and "budgie"
(20 each) share no search.

---

## Rows per customer, for a design effect — `_relate` on the customer column

**Verified live, 2026-10-13**, test env `shoppers`. Shop analytics'
intervals (`src/design_effect.py`).

A `_relate` hit counts rows, and rows of one customer are not
independent. To widen an interval by the design effect, each section
needs, per customer, their rows and their rows meeting the condition.
Relating the customer column gives both:

```json
{"from": "impressions", "where": {"purchased": true},
 "relate": ["customer_id"], "limit": 10000}
```

Since ADR 0033 impressions reach the customer through the context, and
`src/design_effect.py` relates `context.customer` (and
`order_id.customer_id` on `order_lines`, `customer_id` on `orders`):

```json
{"from": "impressions", "where": {"purchased": true},
 "relate": "context.customer", "limit": 10000}
```

The observations below were measured on the one-link form (2026-10-13).

| observation | value |
|:--|:--|
| one hit per customer with **at least one** row meeting the `where` | 2,657 of 3,000 customers; no hit has `fOnCondition` 0 |
| a hit's `fOnCondition` | that customer's rows meeting the `where` |
| a hit's `f` | that customer's rows in the whole table |
| `"where": {}` | **no hits at all** |
| on `order_lines`, `relate: "customer_id"` | 400 "relate field(s) not found"; use the link `order_id.customer_id` |
| time | 0.3–1.9 s for 2,500–3,000 hits |

Because customers with no matching row are left out, a second `_relate`
whose `where` selects every row gives the population:
`{"month": {"$or": [every month of the data window]}}` on `impressions`
and `orders`, `{"order_id.month": {"$or": …}}` on `order_lines`. Check
that its `fOnCondition`s sum to `n` (they do: 115,690 impressions,
38,906 lines, 11,919 orders). From the two, the one-way ANOVA estimator
gives the intra-customer correlation ρ of the condition. For purchases
it is 0.021, with 48.5 impressions per customer (size-weighted), so the
design effect is 1 + 47.5 · 0.021 ≈ 2.0.

---

## A number's bands can't be related on v2 — count them

**Verified live, 2026-10-03**, API v2, `shared.aito.ai`. The Churn
drivers' tenure bands (ADR 0013 amendment).

`_relate` answers "how much more common is this value among the
churners?" for each value of a field. For a number you usually want
bands (tenure under 6 months, 18 months or more), and v2 has no way to
relate one:

| Request | Result |
|:--|:--|
| `"relate": {"tenure_months": {"$gte": 18}}` | 400: "`tenure_months.$gte(18)` is a combinator" |
| `"relate": [{"tenure_months": {"$gte": 18}}]` | 200, but answers another question: `related` is `{"$on": [band, where]}` and the hits are *other* fields that predict it |
| `"relate": ["tenure_months"]`, hits summed per band | Undercounts: values no churner has are left out, so under 6 months came out 0.44× instead of 0.23× |

Count the band instead, with four `_search limit=0` calls (band, band
among churners, everyone, churners). The lift is the same ratio
`_relate` reports:

```
lift = (churners in band / churners) / (customers in band / customers)
```

Reported to Aito core as td-20261003142449808722. Switch back to `_relate`
when it can relate a band.

See `src/churn_drivers.py`. When counting, a band with two bounds is an
`$and` (`{"$and": [{"tenure_months": {"$gte": 6}}, {"tenure_months":
{"$lt": 18}}]}`), and "band among churners" wraps both:
`{"$and": [{"churned": true}, band]}`.

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
small. (ADR 0006 once copied customer traits onto `order_lines` the
same way; ADR 0033 removed those copies.)

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

`"month": "2026-05"` above is a month no training row has, so it is no
evidence: the estimate falls back to the SKU's all-time average. The
forecasts condition on `units_last_month` instead (ADR 0014,
`src/demand_forecast.py`).

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
- `why` is a `weightedAverage` of `neighborContext` nodes (K-NN, 8
  neighbours on `monthly_sales`). Each neighbour's `adjustments` is the
  regression model's tree (below) plus that neighbour's own
  `input.residual`, and its `value` is exactly that tree evaluated.
- **The field terms are the query's, identical in every neighbour**
  (verified on env `observable`, 2026-10-24); only the residual differs.
  So the average splits exactly into `mean` + one term per field + the
  neighbours' average residual ("similar past months"). On data with
  zero-sale months the tree is a plain `sum`, so **every term is in
  units, not logs**: SKU-PT-0206 has `mean` 3.30, `units_last_month: 30`
  +15.39, `product_sku` +6.66, average residual +3.91 → 27.47.
  Reading those as log deltas printed "↑ 483987665%" in the popover.
- **The estimate is not always the `why`'s average.** `estimate` 27.53
  against `why.value` 27.47 (SKU-PT-0206), 8.08 against 10.36
  (SKU-PT-0155). Neither the `hitScore`-weighted mean, the median, nor
  clipping neighbours at 0 explains it. Show the gap as its own row
  (`src/estimate_why.py:explain_estimate`, the Inventory and Demand
  popovers).

**`model: "regression"` variant** swaps K-NN for a linear-
regression model with cleaner per-field contribution explanations
(no nested per-neighbor scaffold). Less neighbor-style "this is
like that case", more "field X shifts the estimate by Y%".

Its `why` is exactly `exp(sum(terms))` (verified on shared, 2.11.4):

```json
{ "type": "exponent", "base": { "type": "constant", "value": 2.718… },
  "power": { "type": "sum", "terms": [
    { "type": "input", "name": "residual", "value": 0.0 },
    { "type": "regression", "proposition": { "price_eur": 4.68 }, "value": -0.728 },
    …,
    { "type": "mean centering", "name": "mean", "value": 1.0995 } ] } }
```

**Its form depends on the data.** On data where every row sold
something, the why is `exp(sum(terms))`, as above. On data with
zero-sale months (ADR 0027's lifecycle fixtures, test env `shoppers`,
2026-10-12) it is a plain `{"type": "sum", "terms": [...]}`: the model is
linear, `mean + Σ terms` in units, and an estimate can go below zero.
Parse both, and check whichever one you got chains to the estimate.

In the exponent form, `e^mean × Π e^value` equals the estimate, and each term is a
multiplier: a waterfall from "a typical month" to the estimate that adds
up (`src/price_what_if.py:waterfall`, ADR 0029). The k-NN default can't
give that: it averages ~8 neighbours, each with its own terms. Gotcha: a
column added in place with v2 `PUT /schema/{table}/{column}` reports type
`Unknown` and is modelled as *categorical* even when it holds Ints
(`units_last_month`; core ticket td-20261012085637124211).

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
  "from": "product_states",
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
per-row join.** `_aggregate` accepts single-hop link paths in `where`,
but Aito joins `orders → customers` for every row: **~2.9 s**
server-side (measured for ADR 0024 on a customer field through
`customer_id`). When the same answer can be read off a table that
carries the column natively, do that instead. The dashboard's average
basket per household is `mean(total_spent_eur) / mean(total_orders)`
aggregated on `customers`, which holds the declared `pets` directly —
algebraically identical (`Σspend / Σorders`), **~20 ms** vs 2.9 s:

```json
{"from": "customers", "where": {"pets": "dog"},
 "aggregate": ["total_spent_eur.$mean", "total_orders.$mean"]}
```

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
  {"from": "customers", "where": {"pets": "dog"}, "limit": 0},
  {"from": "customers", "where": {"pets": "cat"}, "limit": 0}
]
// → one result per item, in order: {offset, total, hits}; a
//    limit:0 count reads `total`. (`pets` is Text: a bare value
//    compares the whole value, so "dog" counts dog-only households.)
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

This killed the dashboard's two N+1 loops (per-household counts;
per-recent-order line lookups). See ADR 0024.

---

## Recommendation by conversion KPI — `_recommend` over `impressions`

**Verified live, 2026-06-23**; the current shapes below since ADR 0033
(env `observable`, Aito 2.11.8). The recommendation backbone (For You,
the Shop). See ADR 0021.

The `impressions` table records one product shown in a `context` (a
visit: customer, month, surface, basket, search query), with the funnel
outcome (`clicked` → `added_to_cart` → `purchased`). That gives
`_recommend` a real conversion KPI to rank on:

```json
POST /_recommend
{
  "from": "impressions",
  "where": { "context.customer": "CUST-00001" },
  "recommend": "product_sku",
  "goal":      { "purchased": true },
  "limit":     12
}
```

Ranks products by **P(purchased = true | shown to this customer)**: For
You (`src/recommend_service.py`). The customer goes in `where` (two
links: `impressions → contexts → customers`), the KPI in `goal`. Aito
learns the customer from their own rows; `./do aito-check` asserts that
Maija's top three are cat products and Saara's dog products.

The Shop's "Picked for you" (`src/shop_context.py`) conditions on what
the household declared and the visit instead of the id:

```json
"where": { "context.customer.pets": { "$and": [{ "$match": "small_animal" }] },
           "context.month": "2026-04",
           "context.basket_categories": { "$and": [{ "$match": "small_animal_accessories" },
                                                   { "$match": "small_animal_cage" }] },
           "just_bought": false,
           "product_sku": { "$not": { "$or": ["SKU-PT-0555"] } },
           "product_sku.pet_type": { "$or": ["small_animal"] } }
```

The `product_sku.*` keys filter the candidates; the `context.*` keys and
`just_bought` condition.

### Goal flip — engagement vs conversion

Swapping the goal field re-ranks by a different funnel stage. On
`where: {"context.customer": "CUST-00001"}`, `goal: {purchased: true}`
and `goal: {clicked: true}` return different top 10s
(`test_recommend_clicks_and_purchases_goals_differ`). On 2026-06-23
(then with the segment as context) the click goal favoured treats:
cheap, fun categories over-click but convert less. That divergence is
its own demo beat (rank for revenue, not clicks).

### Calibrated rate — `_predict` the funnel field

`_recommend`'s `$p` is normalised against goal-positives; for the
absolute funnel rate use `_predict`. The Shop re-asks a product from the
shopper's last order this way, with the grid's context plus the product
and `just_bought: true` (`src/shop_ranking.py`, in one `_batch`):

```json
{
  "from": "impressions",
  "where": { "context.customer.pets": { "$and": [{ "$match": "small_animal" }] },
             "context.month": "2026-04",
             "product_sku": "SKU-PT-0534",
             "just_bought": true },
  "predict": "purchased"
}
```

Returns both classes, summing to 1; read the `true` hit's `$p`.

### Gotchas

- **`where` conditions, it does not restrict the candidate set** —
  unless the key is on the candidate's own fields (`product_sku.*`,
  or `product_sku` itself). `context.search_query: {$match: "food"}`
  makes "the customer searched food" the *context*; `_recommend` still
  ranks the whole `product_sku` domain.
- **`search_query` is `Text`, nullable, on `contexts`.** Token-match
  with `{"context.search_query": {"$match": "food"}}`; it's null on
  non-search surfaces.
- **`position` is descriptive only** — never put it in `basedOn`, or
  Aito learns "position predicts click" over content.
- **Funnel monotonicity** (`purchased ⇒ added_to_cart ⇒ clicked`) is a
  generation invariant, asserted in `./do aito-check`.

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

## The Shop's query shapes (ADR 0031), probed on 2.11.4

Each was run on the test env `shoppers` (2026-10-13) before a view used it,
on the data before ADR 0033 (`product_category` and the `customer_*`
traits were then columns on `impressions`). The current Shop queries are
in "Only what a shop observes" below.

- **A filter on the candidates of `_recommend`** goes on the linked
  table's fields: `"product_sku.category": "dry-food"` filters;
  `"product_category": "dry-food"` (the impression's own copy) does not,
  it is only context. An `$or` over candidate fields works:
  `{"$or": [{"product_sku.category": {"$not": {"$or": [...]}}},
  {"product_sku.name": {"$match": "Grain"}}]}` keeps non-food, and food
  whose name says grain-free.
- **A Text column of SKUs** (`orders.skus`, whitespace analyzer) works for
  co-occurrence: `_relate` from `orders` where `skus: {"$match": SKU}`,
  related to `skus`. Hits come back as `{"skus": {"$has": "SKU-…"}}`.
- **One probability per item from one person's history**:
  `_predict` with `"predict": "skus.$feature"` and
  `"from": {"from": "orders", "where": {"customer_id": …}}`. The plain
  `"predict": "skus"` returns whole past baskets at p 0.1 each.
- **Nested `from` with `_relate` is unsupported** on 2.11.4: 501,
  `"nested from (population restriction) is not supported with relate
  yet"`. Use `_search` over the person's rows, and say it is history.
- **A Boolean on the row as a what-if**: `_predict purchased` with
  `"just_bought": true` added to the `where` gives the probability as if
  just bought (0.085 → 0.022 for one product).

### Why a product, and search, in the Shop (probed 2026-10-17 on master)

- **A product's reasons are in its own `$why`.** On a `_recommend` hit
  (no `basedOn`), the factor `{"type": "hitPropositionLift",
  "proposition": {"product_sku": {"$has": SKU}}}` carries nested
  `relatedPropositionLift`s: how much each part of the `where` lifts
  *this* product (then `customer_treat_affinity: high` ×1.49, `month`
  ×1.32, the cart's `basket_*` propositions ×2.4; since ADR 0033 the
  keys are `context.month`, `context.customer.pets`,
  `context.basket_categories`). The other `hitPropositionLift`s
  are `$not` other products and aren't this product's reasons. A product
  with few impressions of its own has no such factor, only
  `hitLinkPropositionLift` (its features' prior). `src/shop_reasons.py`.
- **`basedOn` adds per-feature lifts but moves `$p`.** With `basedOn:
  ["rating_band", "dietary", "category", "tags", "brand"]`, `$why` gains
  a lift per product feature (grain-free ×1.28), but `$p` roughly
  doubled (0.46 → 0.87 for one product and shopper) and the top 12
  became one category. The Shop doesn't use it.
- **`_search` with `get` doesn't filter on the linked table's fields.**
  `from: impressions, get: product_sku` with `where` on `product_sku.*`
  (a category, or the rule's `$or`) still returned all 658 products: the
  `where` only conditions `$p`. A `where` on `product_sku` itself
  (`{"$or": [SKUs]}`) does narrow it. An empty `$or` matches everything.
  The Shop's search ranks name matches through `_recommend` instead,
  which does apply the filter (`src/shop_search.py`).

## Only what a shop observes (ADR 0033), probed on 2.11.8

Probed 2026-10-20 and 2026-10-21 on the test env `observable`
(`shared.aito.ai`, Aito 2.11.8), unless a line says otherwise. Sources:
`docs/verification/observable-data-prereg.md`,
`docs/notes/aito-core-findings-2026-10-18.md` and ADR 0033's amendments.

- **Two-link `where` and field-form `_relate` work on v2.** A `where` on
  `product_state.product_sku.category` (and the diet rule's `$or` through
  two links) filters `_recommend` candidates, and `_relate` over
  `product_state.product_sku.category` answers with sane counts
  (env `states`, 2.11.4, 2026-10-18). On `observable` (2.11.8,
  2026-10-21), `_relate` over `context.customer.dog_size` from
  `impressions` gives exactly `_search`'s counts for every size (e.g.
  small: 1,986 purchased of 19,234 shown, both ways). The Shop's sweep
  conditioned `_recommend` on `context.customer.pets` and
  `context.customer` through two links (variants G, K, L). The views
  relate `context.customer.pets` / `.diet` (Shop analytics) and
  `order_id.customer_id.pets` / `.dog_size` / `.diet` / `.region`
  (Product Insights) the same way.
- **`$match` on a Text set means "contains", and carries no absence.**
  `"context.owned": {"$and": [{"$match": "small_animal_cage"},
  {"$match": "small_animal_water_bottle"}]}` also matches households that
  own a hideout too, so a hideout's lift for "owns cage and bottle" was
  diluted to ×1.6. `_recommend` doesn't infer "lacks a hideout" from it.
  State an absence explicitly: `{"$not": {"$match": "small_animal_hideout"}}`
  (in the probe, the wheel moved #9 → #3, the hideout #24 → #10;
  `scripts/kit_absence_probe.py`). A whole value (`{"pets": "dog"}`)
  filters as "exactly this value" in `_search` (the dashboard counts
  dog-only households so), but conditions like its tokens in
  `_recommend`. Widening absence evidence is Aito core
  td-20261020203235895741.
- **`_search … get` conditions `$p` but doesn't filter on the linked
  table's fields.** See "Why a product, and search, in the Shop" above
  (probed 2026-10-17 on master). The Shop's search filters through
  `_recommend` instead.
- **`basedOn` improves thin-data ranking but inflates `$p` toward 1.**
  On the held-out sweep, `basedOn: ["pet_type"]` ranked better than the
  same query without it (hit@12 +0.017 [+0.010, +0.025], n = 1,900) but
  had the worst calibration (Brier 0.203 against 0.196;
  td-20261020211932494271). Rank with it only if you re-query `$p`
  without it for anything you show as a probability.
- **An exact cart SKU next to other context can veto a candidate on
  near-zero evidence.** The cart's SKUs next to the owned kit made a
  joint condition no row matches, and the kit's lift disappeared
  (td-20261020210945109481). The Shop states the cart as category words
  (`context.basket_categories`, e.g. `small_animal_cage`) and uses the
  SKUs only to exclude the cart's own items:
  `"product_sku": {"$not": {"$or": [cart SKUs]}}`.
- **Evaluating query variants needs more sessions than you think.** On
  this data, hit@12 differences between variants did not resolve at
  n = 150 held-out sessions: three of three "wins" dissolved on the full
  pool and one tie became a win. About 1,400 or more sessions were
  needed. The Brier score of `$p` resolves at small n (n = 400 here; each
  session averages about 9 squared errors). The harness, with each
  session left out of its own query
  (`from: {from: impressions, where: {"$not": {"context": session}}}`),
  is `scripts/shop_query_sweep.py`.

## A discount band as a what-if — `_predict purchased` with `product_state.*`

Probed 2026-10-24 on env `observable` (Aito 2.11.8), read-only. The
Price view's discount what-if (ADR 0032, `src/discount_what_if.py`).
The band goes in `where` through the impression's `product_state` link
(one link), next to the product:

```json
POST /_predict
{
  "from": "impressions",
  "where": { "product_sku": "SKU-PT-0143", "product_state.discount_band": "20+" },
  "predict": "purchased",
  "select": ["$p", "feature", "$why"]
}
```

Both classes come back; the `true` hit's `$why` (abridged):

```json
{ "$p": 0.2756, "feature": true, "$why": { "type": "product", "factors": [
  { "type": "baseP", "value": 0.1241, "proposition": { "purchased": { "$has": true } } },
  { "type": "product", "factors": [
    { "type": "normalizer", "name": "exclusiveness", "value": 0.9662 },
    { "type": "normalizer", "name": "trueFalseExclusiveness", "value": 1.0 } ] },
  { "type": "relatedPropositionLift", "proposition": { "product_state.discount_band": "20+" }, "value": 1.5877 },
  { "type": "relatedPropositionLift", "proposition": { "product_sku": "SKU-PT-0143" }, "value": 1.4477 } ] } }
```

- **The band is a lift of its own** (v2 returns the String value bare),
  and the chain multiplies out to `$p` exactly: 0.1241 × 0.9662 ×
  1.5877 × 1.4477 = 0.2756. The band's lift is the same for every
  product (10-15 ×1.573, 15-20 ×1.645, 20+ ×1.588, none ×0.875 on all
  658): with two facts as evidence Aito multiplies their lifts.
- **A band the product never had works**: SKU-PT-0158 was never shown
  at 20+ and gets 0.245 (0.139 at none). That is the what-if.
- **When the band is implied by the product, its lift is left out.**
  For the 9 products only ever shown undiscounted, `none` has no band
  factor in `$why`: its `$p` equals the product-only `$p`.
- **Aito can leave the product's own lift out.** In 68 products'
  answers the `product_sku` lift is missing from `$why` in some bands
  (17 products: in all four); the estimate is then the base rate × the
  band's lift × the normaliser, the band's across all products. Where
  the same products keep it in other bands it is 0.94–1.52, so it isn't
  only near-1 lifts that go. The view shows "not in $why" and says so.
- **A product that is rarely bought is held at a floor.** 71 products
  (0–6 purchases in 32–291 impressions) get `$p` = 0.01923 (1/52) at
  `none`, and `$why` gains `{"type": "calibration", "name": "rowCap"}`
  inside the normaliser product (×1.24 for SKU-PT-0495), which lifts the
  chain up to it. For 10 of them every band stays at the floor; for the
  others a discount lifts `$p` to at most 0.043. The band's lift is still
  listed when it doesn't move `$p`. Show the factor; don't present the
  band as moving such a product.
- **`context.surface` conditions too**: SKU-PT-0143 at 20+ is 0.245 on
  `category`, 0.297 on `search`, 0.313 on `bought_together` (0.139,
  0.173, 0.184 at none). The view doesn't use it.
- **Calibration against the data.** Observed purchase rate per band over
  all 117,026 impressions: none 10.85 %, 10-15 19.54 %, 15-20 20.43 %,
  20+ 19.72 %. Predicted, weighted by each product's impressions in the
  band: 10.72 %, 21.55 %, 22.12 %, 20.96 % (in-sample, −1 % to +10 %
  relative). Held out (the query's population excludes Jan–Apr 2026,
  `from: {from: impressions, where: {"$not": {"context.month": {"$or":
  [...]}}}}`, scored on those months' 56,005 impressions): −6 %, −4 %,
  −0.4 %, −5 %. So `$p` is shown as a rate here.
- **Counting** the observed rate per band works with the link in
  `where`: `_search` `{"product_sku": …, "product_state.discount_band":
  …, "purchased": true}` with `limit: 0` gave exactly the counts of the
  joined rows (317 shown / 54 bought at none for SKU-PT-0143). One
  `_batch` carries the four predicts and the eight counts. v2's `_batch`
  answers `{"kind": "batch", "data": [...]}`.

## Business reorders on UCI Online Retail II, env `uci` (ADR 0034)

**Not yet run by this demo.** The `_predict` is Aito core's benchmark
query (byte-stable across the v2.11.9 candidates, dev3, 2026-10-21); the
`_relate` mirrors the pet shop's "A Text column of SKUs" above. Probe
both on env `uci` before merge, then replace this note with what came
back. `./do uci-check` runs both.

**The draft order.** `lines.code` is a plain String (not a link), and
the buyer is reached through `lines.invoice → invoices.customer_id`:

```json
POST /_predict
{"from": "lines", "where": {"invoice.customer_id": "12357"},
 "predict": "code", "limit": 10, "select": ["$p", "$value"]}
```

Expected hits: `{"$p": 0.03, "$value": "85123A"}`; the code reads from
`$value` because the query selects that name.
`src/uci_reorder_service.py` raises on a hit without it.

**Bought together.** `baskets.codes` holds each invoice's StockCodes,
whitespace analyzer. "BANK CHARGES" is stored as `BANK_CHARGES` so it
stays one token:

```json
POST /_relate
{"from": "baskets", "where": {"codes": {"$match": "85123A"}},
 "relate": ["codes"], "limit": 50}
```

To probe: hits read `related.codes.$has` with the code's case kept
(`85123A`, not `85123a`); the chosen code is among the 50 hits
(`src/uci_bought_together.py` raises if not); and which 50 of the
~4,400 codes come back (if they are not ordered by lift, the view's
top 10 by lift is a top 10 of the wrong 50).

## The reorder backtest's `$why`, env `uci` (ADR 0036)

**Not yet run by this demo.** The backtest measures the draft order's
`_predict` above, byte for byte. For its ten example buyers it asks once
more, for the top code's reasons, combining `$value` (above) with the
`_predict` `{"$why": {}}` select documented in "`$why` highlight":

```json
POST /_predict
{"from": "lines", "where": {"invoice.customer_id": "12357"},
 "predict": "code", "limit": 1, "select": ["$p", "$value", {"$why": {}}]}
```

It is a separate query so the measured one never changes. To probe on
`uci` (`./do uci-check` runs it): the top `$value` equals the measured
query's top code (`src/backtest_aito.py` raises if not), and the tree
parses with `src/why_processor.py` to a baseP and lifts whose conditions
are named (expected: `invoice.customer_id` for a buyer with history).

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
