# Evaluation — honest pass/fail with `_evaluate`

![Evaluation](../../screenshots/08-evaluation.png)

*Four prediction models, four `_evaluate` runs, three pass and
**one honest failure**. The "Return Risk" model deliberately
fails its threshold — Aito has no signal in the data to beat the
3% baseline, and the view shows that as a red row instead of
fudging the threshold.*

## Overview

Most predictive-product demos hide their failures. Ours doesn't.
The Evaluation view runs four `_evaluate` calls — one per model
that the rest of the demo uses — against held-out test sets, and
reports pass/fail against a fixed threshold (10 percentage points
of accuracy gain over the always-predict-majority baseline).

Three of the four models pass. The fourth — predicting whether
an order line will be returned — fails because the fixture only
has 3% returned lines and Aito honestly reports `accuracy_gain ≈
0`. There's no feature in the training data that beats the prior.

Showing that as a red row is the demo's most important moment.
It's the answer to "does Aito just make up answers when it
doesn't know" — no, it tells you the gain over baseline is zero
and the view renders that as failure.

## How it works

### The query

```python
# src/eval_service.py — _evaluate_one()
body = {
    "testSource": {"from": model.table, "limit": 200},
    "evaluate": {
        "from":    model.table,
        "where":   model.where,
        "predict": model.predict,
    },
    "select": ["accuracy", "baseAccuracy", "n"],
}

res = client.evaluate(
    model.table,
    model.where,
    model.predict,
    test_limit=200,
)
```

`_evaluate` is Aito's cross-validation endpoint. The body has
two top-level keys:

- `testSource` — the row set Aito holds out as the test sample
  (200 rows from the table).
- `evaluate` — the prediction call to run for each test row. The
  `where` clause references the test row's values via
  `{"$get": "<field>"}`.

`$get` is the key gotcha — without it, `where` would be the same
fixed dict every time and `_evaluate` would predict on identical
input over and over. The `$get` syntax tells Aito "read this
field from the current test row".

### The four models

```python
MODELS = [
    ModelSpec(
        id="pet_type_from_name",
        label="Pet type from product name",
        table="products",
        where={"name": {"$get": "name"}, "brand": {"$get": "brand"}},
        predict="pet_type",
    ),
    ModelSpec(
        id="dietary_from_name",
        label="Dietary tag from product attributes",
        table="products",
        where={
            "name":     {"$get": "name"},
            "brand":    {"$get": "brand"},
            "category": {"$get": "category"},
            "pet_type": {"$get": "pet_type"},
        },
        predict="dietary",
    ),
    ModelSpec(
        id="segment_from_product",
        label="Customer segment from product attributes",
        table="order_lines",
        where={
            "product_sku.pet_type": {"$get": "product_sku.pet_type"},
            "product_sku.category": {"$get": "product_sku.category"},
        },
        predict="customer_segment",
    ),
    ModelSpec(
        id="return_risk",
        label="Return risk (deliberate honest-failure case)",
        table="order_lines",
        where={
            "product_sku.category": {"$get": "product_sku.category"},
            "product_sku.pet_type": {"$get": "product_sku.pet_type"},
            "customer_segment":     {"$get": "customer_segment"},
        },
        predict="returned",
    ),
]
```

The first three are predictions the rest of the demo's views
actually run (Product Filling's pet_type / dietary, Smart Search /
For You's segment). Evaluating them on `_evaluate` proves the
predictions hold up on held-out data, not just the trained set.

The fourth is the honest-failure case. `returned` is a Boolean
that's true ~3% of the time, and none of the conditioning columns
(product category, pet type, customer segment) carry signal that
beats the 97% always-false baseline.

### Pass / fail threshold

```python
PASS_THRESHOLD_PP = 10.0
gain = float(res.get("accuracyGain", accuracy - base) or 0)
verdict = "pass" if (gain * 100) >= PASS_THRESHOLD_PP else "fail"
```

A model passes if its accuracy exceeds the baseline accuracy by
at least 10 percentage points. That's a high bar — for the
pet-type model the baseline is "always guess dog" at ~50%,
and Aito hits >95% by reading the name; gain is ~+45pp.

Return Risk's baseline is 97% (always guess "not returned");
the best Aito can do is also ~97% (it can't find any pattern in
the data); gain is ~0pp; fail.

### Parallel execution

Each `_evaluate` call is 5–15 seconds live (the test sample +
the four-model fanout). Serial would be 40+ seconds — too slow
for the demo. We parallelise:

```python
with ThreadPoolExecutor(max_workers=len(MODELS)) as pool:
    results = list(pool.map(lambda m: _evaluate_one(client, m), MODELS))
```

Wall-clock = the slowest, typically ~15 seconds on a cold run.
Cached for an hour after that.

### httpx timeout bump

Aito's `_evaluate` for the return-risk model takes 25–28 s
because the result set is large (~1,100 returned lines vs 35,000
non-returned). The default httpx client timeout is 30 s, which
flakes. We bumped the client to 90 s:

```python
# src/aito_client.py
self._client = httpx.AsyncClient(timeout=90.0)
```

## Key features

### 1. Real `_evaluate`, real held-out sample

Nothing precomputed. Each page load runs the four `_evaluate`
calls live against Aito. The `last_run` timestamp on the page is
the actual UTC time the calls completed.

### 2. One red row, deliberately

The return-risk model is engineered to fail. The fixture's 3%
return rate has no recoverable pattern; Aito reports zero gain;
the view renders red. CLAUDE.md prime directive #2 — never
silently transform — applies here too. We could pick a different
predict field that always passes. We don't.

### 3. Three pass rows quote the actual baseline

The view doesn't just say "model: pass". It shows the accuracy,
the baseline accuracy, and the gain in percentage points. For
the segment-from-product model, the line reads "84.7% (baseline
36.1%, +48.6pp)". The reviewer sees that 48.6pp of accuracy is
genuinely Aito-driven, not baseline-driven.

## Data schema

Evaluation reads the same tables the live views read:

- `products` — for the pet-type-from-name and dietary models
- `order_lines` — for the segment-from-product and return-risk
  models

No new tables, no special evaluation set. The held-out sample is
a random 200-row slice that Aito carves at evaluation time via
`testSource.limit`.

## Tradeoffs and gotchas

- **`_evaluate` requires both `testSource` AND `evaluate`**. The
  initial implementation tried `{"evaluate": {...}}` alone and
  got a 400 from Aito. The full shape needs `testSource` to
  carve the held-out set + `evaluate` for the per-row call +
  `select` for the metrics to return.
- **`$get` is mandatory in `where`**. Without `{"$get": "<field>"}`,
  Aito would substitute the literal value of `where` for every
  row in the test sample — predicting the same thing 200 times.
  `$get` tells it "read this column from the current test row".
- **The 10pp threshold is fixture-tuned**. On a real customer
  dataset with stronger signal, 10pp is the floor; on weaker
  data 5pp might be the right number. We picked 10pp because
  three of our four models clear it by 30+ pp, and the
  return-risk failure is unambiguous.
- **`accuracyGain` field is sometimes missing**. Some Aito
  versions return `accuracy + baseAccuracy` and expect the
  client to subtract; newer versions return `accuracyGain`
  directly. We fall back: `gain = res.get("accuracyGain",
  accuracy - base)`.

## What this demo abstracts away

- **Per-fold cross-validation**. `_evaluate` with `limit=200`
  runs one held-out fold. Production would want k-fold (Aito
  supports it — just run k separate `_evaluate` calls with
  different `testSource` filters).
- **Confusion matrices**. The view shows accuracy + baseline
  only. A real evaluation surface would show per-class
  precision/recall + a confusion matrix (clickable cells →
  the false-positive examples).
- **Drift detection**. Run `_evaluate` weekly, plot accuracy
  over time, alert on regressions. Our `last_run` timestamp
  is point-in-time only.
- **A/B-style model comparison**. "Model with feature X vs.
  model without" — same `_evaluate` shape, two calls, render
  the delta. The mechanics are easy; the UI isn't built.

## Try it live

[**Open Evaluation**](http://localhost:8500/evaluation/). Cold
load is ~15 s (four parallel `_evaluate` calls); cache for
an hour after. Watch for the red row — that's the demo's
honest-failure moment.

```bash
./do dev
# → http://localhost:8500/evaluation/
```
