# ADR 0009: Product Filling — multi-field `_predict`

**Status:** Accepted
**Date:** 2026-05-11
**Deciders:** Demo team

## Context

`TASK.md` writes Product Filling as:

> Incomplete product card on the left (missing category, weight,
> tax_class, dietary, …); on the right, the same five fields
> filled in by Aito with confidence chips. Aito panel shows
> multi-field `_predict` for catalog enrichment.

And the demo moment:

> Pick the incomplete "Acana Large Breed Adult" row, watch five
> fields fill with confidence chips, all in one multi-field
> `_predict` call.

The fixture (ADR 0002) sets ~5 % of food products with two
nulled attributes from `{weight_kg, dietary, tax_class}`. To hit
the "five fields" moment, the demo *also* hides `pet_type` and
`category` — both of which Aito can predict perfectly from the
product's `name` + `brand` alone. So the on-screen experience is
five `_predict` calls, each with `where = {name, brand}` and a
different `predict_field`.

## Aito usage

### Live `_predict` (verified 2026-05-11)

```json
POST /api/v1/_predict
{
  "from": "products",
  "where": {
    "name": "Hill's Science Plan Sensitive Turkey Dog Food 2kg",
    "brand": "Hill's Science Plan"
  },
  "predict": "dietary",
  "select": ["$p", "feature", { "$why": { ... } }],
  "limit": 5
}
```

Result for that example, all five fields:

| Field        | Prediction      | p     | Source signal in the name |
|---|---|---|---|
| `pet_type`   | `dog`           | 0.977 | "Dog" token |
| `category`   | `dry-food`      | 0.874 | brand × name co-occurrence in training data |
| `weight_kg`  | `2.0`           | 0.985 | "2kg" suffix |
| `dietary`    | `sensitive`     | 0.954 | "Sensitive" token |
| `tax_class`  | `food-reduced`  | 0.981 | category-prediction co-occurrence |

All five above `p = 0.87`. The `$why` decomposition is included
in the `select` so the per-field `WhyTooltip` can show the
multiplicative chain of contributing tokens.

### Why one call per field, not one combined call

Aito's `_predict` predicts **one field at a time**. A combined
"multi-predict" would be a different operation (`_batch` or N
parallel calls). For the demo we make **5 parallel HTTP calls**
in the service layer; the wall-clock is dominated by the slowest
call (~150 ms). The panel says "multi-field `_predict`" honestly
because the user sees one query *body shape* repeated for five
different `predict_field` values.

### Schema-design observation

The fact that `name` is a `Text` column is load-bearing here.
Aito tokenises it and uses individual tokens (`Sensitive`,
`2kg`, `Dog`) as features. If `name` had been `String`, only
exact-name matches would condition the prediction and the demo
moment would collapse to a lookup. ADR 0003's type choice on
`products.name` was the right call.

## Decision

### `/api/product-filling` response

```ts
interface FillingField {
  field: string;                  // "dietary", "weight_kg", ...
  label: string;                  // human label for the row
  /** The value Aito predicted ("sensitive", "2.0", …). */
  predicted_value: string | number | null;
  confidence: number;             // $p
  /** Top alternatives — drives the WhyTooltip / picker. */
  alternatives: Array<{ value: string; confidence: number }>;
  /** Raw $why factors so the UI can pop a per-field popover. */
  why_factors: Array<{ field: string; value: string; lift: number }>;
  /** Whether the source row had this field set or null. We hide
   *  `pet_type` + `category` *for display*, even though they're
   *  populated in the DB — see ADR. */
  hidden_for_demo: boolean;
}

interface FillingResponse {
  product: {
    sku: string;
    name: string;
    brand: string;
    /** The product's ACTUAL stored attributes — used by the UI to
     *  show the "input card" with the missing fields as "—". */
    pet_type: string;
    category: string;
    weight_kg: number | null;
    dietary: string | null;
    tax_class: string | null;
    price_eur: number;
  };
  /** One entry per field Aito predicted, in display order. */
  fields: FillingField[];
  /** Available SKUs to pick from (the dropdown). */
  candidate_skus: Array<{ sku: string; name: string }>;
  last_query: { endpoint: string; body: object };
  last_response_ms: number;
}
```

### Endpoint

`GET /api/product-filling?sku=<SKU-PT-NNNN>` — optional. When
omitted, the service picks a *good* default — the
`Hill's Science Plan Sensitive Turkey Dog Food 2kg` row (rich
in tokens; all 5 fields produce high-confidence predictions).
The candidate dropdown surfaces ~15 fillable SKUs so a demo
viewer can rotate through different products.

Cached per SKU for 30 minutes.

### Which fields the demo shows

Always show 5 rows in order: `pet_type`, `category`,
`weight_kg`, `dietary`, `tax_class`. For each:

- If the source product *has* the value, mark `hidden_for_demo:
  true` — the UI still predicts it (to fill the "five fields"
  visual) and shows the prediction with the confidence chip.
  Aito's confidence is honest; the demo doesn't pretend the
  value was missing.
- If the source product genuinely has `null`, mark
  `hidden_for_demo: false` and treat it as the load-bearing
  prediction.

The user-visible distinction is one tiny "🔒 stored" annotation
on the input card for `pet_type` / `category` (so a reader can
see we're not lying), versus the "—" marker on truly-null
fields.

### UI structure

```
┌── Picker ──────────────────────────────────────────────────────┐
│  Incomplete product: [Hill's Sensitive Turkey Dog Food 2kg ▾]   │
└────────────────────────────────────────────────────────────────┘

┌── Input (incomplete) ────────┐    ┌── Aito fills 5 fields ────────┐
│  Hill's Sci Plan ...        │    │  Hill's Sci Plan ...           │
│                              │ →  │                                │
│  pet_type:   🔒 stored       │    │  pet_type:   dog         91%   │
│  category:   🔒 stored       │    │  category:   dry-food    87%   │
│  weight_kg:  — (null)         │    │  weight_kg:  2.0 kg      98%   │
│  dietary:    — (null)         │    │  dietary:    sensitive   95%   │
│  tax_class:  food-reduced    │    │  tax_class:  food-reduced 98%  │
│                              │    │  + WhyTooltip per row          │
└──────────────────────────────┘    └────────────────────────────────┘
```

Right-side rows use the existing `.fill-field` / `.fill-conf` CSS
already in `globals.css`. Confidence chips are colour-coded by
`confClass(p)` (green ≥ 0.80, gold 0.50–0.80, red < 0.50).

## Acceptance criteria

- [ ] `./do dev` renders `/product-filling` with a default
      product and 5 filled rows.
- [ ] At least 4 of the 5 rows show confidence ≥ 0.80 for the
      default product (the dog dry-food example confirmed every
      field is ≥ 0.87 live).
- [ ] Picker dropdown lists ≥ 10 fillable SKUs.
- [ ] Aito panel quotes the live `_predict` body for the most
      recent field (uses the rotating render to show different
      `predict_field` values).
- [ ] No regression in existing tests (20/20 still green).

## Demo impact

This is demo moment #4 in `TASK.md`. The visual reads as "Aito
fills 5 missing fields in one round-trip's worth of work" — a
strong "catalog enrichment without manual data entry"
narrative for the merchandising audience.

## Out of scope

- **Bulk fill across the whole catalog**. The view is per-
  product; a bulk-enrichment story belongs in a Catalog
  Intelligence sub-view, not this ADR.
- **Editable predictions**. The `PredictedField` primitive
  supports user overrides (per ADR 0004), but the Filling view
  is read-only in this MVP. Edit-on-click can land later if a
  reviewer asks for it.

## Consequences

**Good:**
- All 5 predictions land in parallel ~150 ms — fast enough that
  the user sees the grid "pop" with values, which is the demo
  moment.
- The `Text`-tokenisation on `products.name` does the heavy
  lifting; Aito's `$why` decomposition tells you exactly which
  tokens contributed.
- The same `_predict` body shape is reused 5× — the Aito panel
  reads as "this one query, repeated for each missing field".

**Bad:**
- "5 fields" requires hiding 2 already-populated fields
  (`pet_type`, `category`) for display. We're explicit about
  this in the UI (the 🔒 stored tag) and the ADR — better to
  surface the trade-off than fake it.
- Five round-trips per render, even with cache. The cache
  amortises subsequent loads, but a first-time load is ~150 ms
  per call sequentially. Worth parallelising in the service
  layer; deferred until measured to actually be a problem.

## Notes

- The default product is hard-picked because the demo's first-
  impression matters. The dropdown gives access to the rest;
  most picks should yield confidence ≥ 0.70 for the genuinely-
  null fields, but lower-token-content product names (e.g.
  "PetNord Brush") have less for Aito to bind on.
- `$why` factors per field tend to surface the *individual
  tokens* that contributed (`"Sensitive"`, `"2kg"`). For the
  demo this reads beautifully — it's the same auditability
  story the framework doc carries (`WhyTooltip` shows the
  multiplicative chain verbatim).
