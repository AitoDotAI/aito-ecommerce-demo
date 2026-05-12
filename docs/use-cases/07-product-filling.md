# Product Filling — multi-field `_predict` for catalog enrichment

![Product Filling](../../screenshots/07-product-filling.png)

*Five product attributes — pet_type, category, weight_kg, dietary,
tax_class — predicted in parallel from a single product's name +
brand. Five `_predict` calls in one round-trip, confidence chip
on each field, top-N alternatives in the dropdown.*

## Overview

The catalog manager's job that nobody wants to do: filling in
the missing fields on a new SKU. Weight, dietary tag, tax class,
sometimes even category — partial data ships from the supplier,
and somebody has to look up or guess the rest before the SKU goes
live.

Product Filling treats this as five `_predict` calls. Given the
product's name and brand (which arrive populated), Aito predicts
each missing field by finding similar products in the catalog and
returning the most-probable value with a confidence score. The UI
renders each as a "predicted, click to accept" card with a
top-3 alternatives dropdown.

## How it works

### The five-call fanout

```python
# src/filling_service.py — get_filling()
where = {"name": product["name"], "brand": product.get("brand", "")}

# Predict the same `where` for 5 different target fields, in parallel.
PREDICT_FIELDS = [
    ("pet_type",  "Pet type"),
    ("category",  "Category"),
    ("weight_kg", "Weight (kg)"),
    ("dietary",   "Dietary"),
    ("tax_class", "Tax class"),
]

with ThreadPoolExecutor(max_workers=5) as pool:
    futures = [
        pool.submit(
            _predict_field,
            client,
            where,
            predict_field,
            label,
            predict_field in _ALWAYS_STORED,
        )
        for predict_field, label in PREDICT_FIELDS
    ]
    fields = [f.result() for f in futures]
```

Wall-clock = the slowest of the five — typically ~480 ms warm,
~1.5 s cold. Five calls in parallel because there's no shared
state and each call is independent.

### Per-field `_predict`

```python
# src/filling_service.py — _predict_field()
res = client.predict("products", where=where, predict_field="dietary", limit=5)
hits = res.get("hits", [])
top = hits[0]
predicted_value = top.get("feature")
confidence = float(top.get("$p", 0))
alternatives = [
    Alternative(value=str(h.get("feature", "")), confidence=float(h.get("$p", 0)))
    for h in hits[1:4]
]
why_factors = _parse_why(top.get("$why"))
```

`limit=5` returns five candidate values per field; the top one
becomes the predicted_value, the next three become the
alternatives dropdown. The `$why` payload feeds the
"why this prediction" tooltip per field.

### Pet type + category — always stored, still predicted

```python
_ALWAYS_STORED = {"pet_type", "category"}
```

Two of the five fields are *always* populated in the DB. The
demo shows them with a 🔒 tag in the input card so the user can
see we aren't claiming they were null. We still run the
`_predict` on them — and Aito gets them right at 99%+ confidence,
every time — to fill the "five fields predicted" visual.

This is a real e-commerce gotcha: the catalog manager *trusts* the
supplier-shipped data on some fields and not others. Showing
which is which keeps the demo honest.

### `$why` factor extraction

Aito's `$why` returns a tree of `$mul` / `$prob` nodes. The
WhyTooltip just needs the leaf factors that contribute a lift +
human-readable value:

```python
def _parse_why(raw_why):
    out = []
    def walk(node):
        if not isinstance(node, dict):
            return
        if "lift" in node and "value" in node:
            value = node.get("value")
            # value may be {"<field>": {"$has": <token>}}
            field_name = next(iter(value.keys()), "") if isinstance(value, dict) else ""
            inner = next(iter(value.values()), None) if isinstance(value, dict) else value
            prop = inner.get("$has") or inner.get("$is") if isinstance(inner, dict) else inner
            out.append(WhyFactor(
                field=field_name,
                value=str(prop) if prop is not None else "",
                lift=float(node.get("lift", 0)),
            ))
            return
        for v in node.values():
            if isinstance(v, dict):
                walk(v)
            elif isinstance(v, list):
                for item in v:
                    walk(item)
    walk(raw_why)
    out.sort(key=lambda f: abs(f.lift - 1.0), reverse=True)
    return out[:4]
```

The tooltip surfaces the top 4 factors by deviation from 1.0 —
the patterns that most-strongly drove the prediction.

## Key features

### 1. Confidence-aware UI

Each field card shows the confidence as a 0.0–1.0 chip. The
PredictionBadge component reads the confidence and tones
accordingly (green ≥ 0.85, yellow 0.5–0.85, red < 0.5).
Hill's Sensitive Adult lands every field at ≥ 0.87 — a "trust
the prediction" case. Other SKUs with thinner data show lower
confidence; the alternatives dropdown is the user's escape
hatch.

### 2. Top-3 alternatives per field

The dropdown isn't just "the prediction or the user's input" —
it's "the prediction, three alternatives Aito ranked next, or
the user's input". For weight_kg the alternatives might be
`2.0, 2.5, 3.0` — values Aito considers plausible but ranked
lower. The user can pick from the dropdown without typing.

### 3. `$why` per field

Clicking the question mark next to any field opens a tooltip
showing the top factors that drove the prediction. For
"dietary = grain-free", the factors might be:
"name has 'Sensitive': lift 8.2×",
"brand = Hill's: lift 3.1×".
The tooltip makes the prediction auditable.

## Data schema

Product Filling queries the `products` table. The Aito schema
keeps each predictable field as the type that best matches its
semantics:

```json
{
  "products": {
    "type": "table",
    "columns": {
      "sku":       { "type": "String" },
      "name":      { "type": "Text", "analyzer": "whitespace" },
      "brand":     { "type": "String" },
      "pet_type":  { "type": "String" },
      "category":  { "type": "String" },
      "weight_kg": { "type": "Decimal" },
      "dietary":   { "type": "String" },
      "tax_class": { "type": "String" }
    }
  }
}
```

`name` is Text so the tokeniser can match individual words
("Sensitive", "Adult", "Turkey"). The other fields are String —
exact-match conditioning, no analyzer.

## Tradeoffs and gotchas

- **The five fields are hardcoded**. Production would derive them
  from the schema (any column that's non-null in ≥ X% of rows
  becomes a fill candidate). We list them in `PREDICT_FIELDS`
  because the demo wants the same five every load.
- **`weight_kg` as a Decimal is fragile**. Aito's `_predict` over
  a Decimal returns discrete values that appeared in training,
  not interpolated. If your weights are quantised
  (2.0, 2.5, 3.0, 5.0), the predictions land cleanly. If they're
  continuous (2.0, 2.13, 2.27, ...) the prediction quality
  degrades. Categorical numeric fields (small / medium / large)
  side-step this.
- **No bulk-fill view**. The page shows one SKU at a time. A real
  catalog-enrichment tool needs a "fill all 47 incomplete SKUs"
  workflow. The mechanics are the same — for each SKU,
  five `_predict` calls — but the UI is different.
- **Caching is per-SKU**. Cache key is `filling:{sku}`. If the
  same `(name, brand)` repeats across SKUs (rare but possible),
  the second call doesn't hit cache. A name-keyed cache would
  fix that.

## What this demo abstracts away

- **Persisting accepted predictions back to the catalog**. The
  demo renders predictions; it doesn't write them to the
  `products` table. Production wires the "Accept" button to a
  catalog-update endpoint.
- **Override-as-training-signal**. When the user rejects a
  prediction and types a different value, that's the strongest
  signal Aito could get. Production would log
  `(sku, field, predicted, accepted)` to a training table that
  feeds back into the next prediction.
- **Schema introspection**. The demo doesn't ask Aito "what
  fields exist on this table" — it hardcodes the five. Aito
  exposes the schema via the API; production should walk it.

## Try it live

[**Open Product Filling**](http://localhost:8500/product-filling/) —
the default SKU (Hill's Sensitive Adult, dog dry-food) hits ≥
0.87 confidence on every field. Pick a different SKU from the
dropdown to see lower-confidence cases.

```bash
./do dev
# → http://localhost:8500/product-filling/
```
