# ADR 0002: Data model + deterministic fixtures

**Status:** Accepted
**Date:** 2026-05-10
**Deciders:** Demo team

## Context

The demo's credibility rests on Aito producing visible, quotable
results — the **five demo moments** in `TASK.md`:

1. Smart Search re-ranks "food" so cat food drops from rank 1 to
   rank 6 for a large-breed dog owner.
2. For You's grid flips when the customer-switcher pill flips
   (Maija → Olli → Saara).
3. Bought Together shows dog-food → dental-treats lift ≈ 3×.
4. Product Filling fills five missing fields with confidence chips.
5. Evaluation honestly fails one model on its threshold.

None of those land if the fixtures don't carry the engineered
signal. This ADR locks the schema, the volumes, the categorical
vocabulary, and — most importantly — the *target ranges* the
generator's signal must hit before downstream code touches it.

The volume rule from `TASK.md`: enough that `_relate` produces
visibly different lift scores per segment (~0.5×–3.5×), small
enough for the Aito free tier.

## Aito usage

- **`products.name`** is `Text` — drives free-text `_search` and
  `_match` for the Smart Search view's tokeniser.
- **`products.{category, pet_type, brand, dietary, tax_class}`**
  are `String` (categorical) — drive `_predict` (catalog enrichment),
  `_relate` (Pattern Explorer / Bought Together), and `_search`
  `where`-biasing.
- **`customers.{segment, pet_size, region}`** are `String` — drive
  `_search`'s `where` context for the rank-flip in Smart Search and
  `_recommend`'s context for For You.
- **Links** (these are the load-bearing join paths for `_recommend`
  and `_relate`):
  - `order_lines.order_id` → `orders.order_id`
  - `order_lines.product_sku` → `products.sku`
  - `orders.customer_id` → `customers.customer_id`

  With those links Aito can answer e.g.
  `_recommend products.sku from order_lines where {"orders.customer_id": "CUST-00123"}`
  end-to-end without us hand-rolling joins.

## Decision

### Tables

The four tables in `TASK.md`. Columns and types kept verbatim.

```
products      ~700 rows
customers   ~3 000 rows
orders     ~14 000 rows over 24 months (2024-05 .. 2026-04)
order_lines ~36 000 rows  (avg 2.6 lines per order)
```

A single `data/generate_fixtures.py` produces all four JSON files
deterministically from `RNG_SEED = 42`. Same seed → byte-identical
output across runs and machines.

### Categorical vocabularies

```
pet_type:     dog, cat, small_animal, bird, aquarium
category:     dry-food, wet-food, treats, dental-treats, litter,
              accessories, health, grooming, toys, aquarium
brand:        Royal Canin, Hill's Science Plan, Eukanuba, Acana,
              Orijen, Whiskas, Felix, Sheba, Whimzees, Kong,
              JBL, Tetra, PetNord (own brand), Beaphar, Trixie
dietary:      grain-free, senior, puppy, large-breed, sensitive,
              indoor, weight-control          (nullable, drives Filling)
tax_class:    food-reduced, standard, pharma  (nullable, drives Filling)
segment:      dog_owner, cat_owner, multi_pet, small_animal_owner,
              aquarium_owner
pet_size:     small, medium, large            (dog_owner only)
region:       helsinki, espoo, tampere, oulu, turku, jyvaskyla
```

### Engineered signal — target ranges

These are the assertions `tests/test_fixtures.py` runs against the
generated JSON. The generator iterates seeded RNG draws until each
range is satisfied; if it can't converge, the whole demo is broken
and the test fails loudly.

| # | What | Target range | Demo moment it powers |
|---|---|---|---|
| 1 | `P(line.product_sku.pet_type == "cat" \| customer.segment == "dog_owner" AND customer.pet_size == "large")` | `< 0.01` | Smart Search rank flip |
| 2 | `P(category == "dental-treats" \| order contains category == "dry-food" AND any line.product.pet_type == "dog")` ÷ `P(category == "dental-treats")` (lift) | `≥ 2.5×` | Bought Together |
| 3 | Top-5 `(pet_type, category)` pairs of Maija's historical orders ∩ top-5 of Olli's | `≤ 1` shared pair | For You differential |
| 4 | Products with ≥ 2 of `{weight_kg, dietary, tax_class}` null | `4–6 %` of `products` | Product Filling input pile |
| 5 | `order_lines.returned == true` share | `2.5–3.5 %` | Evaluation honest-failure case (return-risk model is at the edge of Aito's predictive ability with this signal) |

### Persona customers

Three named customers exist by id so the For You customer-switcher
hits stable rows:

```
CUST-00001  "Maija"  cat_owner            helsinki  tenure 18mo
CUST-00002  "Olli"   multi_pet (sm. dog)  tampere   tenure  9mo
CUST-00003  "Saara"  dog_owner / large    espoo     tenure 26mo
```

Each gets 8–14 deterministically-seeded historical orders so their
For You grids are demonstrably different.

### File layout

```
data/
  generate_fixtures.py  # Single source of truth — re-runs idempotent
  products.json
  customers.json
  orders.json
  order_lines.json
```

JSON files are committed to the repo so the demo is reproducible
without re-running the generator (and so a developer skimming the
repo can see the data directly).

## Acceptance criteria

- [ ] `./do generate-fixtures` produces four JSON files in `data/`
      with row counts inside the volume bands above.
- [ ] Re-running with no arg changes is a byte-identical no-op
      (verified via `git diff` after a regen).
- [ ] `tests/test_fixtures.py` confirms each of the five engineered
      ranges; failures are loud and name the violated invariant.
- [ ] Maija / Olli / Saara have stable customer ids and disjoint
      top-5 categories.

## Demo impact

This ADR doesn't ship a view but it underwrites every one of the
five demo moments. If the fixture signal is wrong, every later
demo-moment assertion is wallpaper. We test the data first, then
the views.

## Out of scope

- Aito schema upload (`src/data_loader.py`) — ADR 0003.
- Cache warming / precomputation — ADR 0003.
- Per-view DTOs and the actual `_predict` / `_recommend` / `_relate`
  / `_search` queries — ADRs 0005 onward.

## Consequences

**Good:**
- The five demo moments are *engineered into the data*, not into
  view code or panel copy. A reader of `data/generate_fixtures.py`
  can see the signal directly.
- Deterministic seed means screenshots / booktest snapshots stay
  stable across regens until someone deliberately bumps the seed
  or changes a target range.
- One generator file → easy to reason about. No ETL pipeline, no
  hidden coupling.

**Bad:**
- Writing a generator that hits all five target ranges
  simultaneously is finicky. A naïve "draw segments uniformly"
  approach will break either #1 or #2. The generator's structure
  has to bake in the segment → category preference matrix from the
  start.
- Committing 36 000-line JSON to git inflates the repo by ~3 MB.
  Acceptable: it's flat, gzip-friendly, and *readable*. A reader
  who wants to understand "what's actually in this Aito DB" can
  jump straight to `data/order_lines.json` instead of reverse-
  engineering the generator.

## Notes

- If a future view (e.g. an honest Return-Risk extension) needs a
  *different* signal target, it gets its own ADR + a generator
  update; never edit the existing target ranges silently.
- The `tax_class` vocabulary stays small (3 values) so the
  Filling demo's confidence chips read high — five three-way
  predictions can comfortably hit p ≥ 0.85 each, which is what
  sells the moment.
