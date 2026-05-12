# Churn — the killer Understand view

![Churn](../../screenshots/10-churn.png)

*N parallel `_predict churned` calls rank active customers by
risk. Three parallel `_relate` calls surface the drivers. One
`_evaluate` reports honest held-out accuracy — with the timestamp
held out so Aito predicts churn from who they are, not from when
they last ordered.*

## Overview

Churn prediction is the single most economically-relevant model
an e-commerce shop can run. Most shops do this with a rule-of-
thumb table ("anyone who hasn't ordered in 90 days is at risk")
exported nightly to the email tool. That's not prediction;
that's a calendar.

Real churn prediction asks: *given a customer's segment, region,
tenure, basket size, total spend — who's about to stop buying
even though they were active recently?* Aito's `_predict
churned` answers that per row, without the analyst writing any
feature-engineering pipeline.

This view is the demo's strongest "Aito gives you something a
SQL query can't" moment. Four blocks: KPI strip, at-risk
leaderboard, drivers, evaluation.

## How it works

### Block 1: KPI counts

Three `_search limit=0` calls:

```python
total    = client.search("customers", limit=0)["total"]
churned  = client.search("customers", where={"churned": True}, limit=0)["total"]
active   = total - churned
```

Total / Active / Churned / churn-rate render as four cards
across the top. Cheap — ~30 ms total.

### Block 2: At-risk leaderboard

For each of N active customers (sample of 100), one `_predict
churned`:

```python
# src/churn_service.py — _predict_churn_for()
res = client.predict(
    table="customers",
    where={
        "segment":        customer["segment"],
        "pet_size":       customer.get("pet_size"),   # nullable
        "region":         customer["region"],
        "tenure_months":  customer["tenure_months"],
        "total_orders":   customer["total_orders"],
        "total_spent_eur": customer["total_spent_eur"],
    },
    predict_field="churned",
    limit=2,
)
for hit in res.get("hits", []):
    if hit.get("feature") is True:
        return float(hit.get("$p", 0))
```

The 100 calls run in a thread pool (8 workers). Sort by
P(churned=true) descending, take the top 20.

**Critical**: `last_order_month` is *not* in the `where`. The
churn label is deterministically derived from that column —
including it would leak the answer and Aito would "predict"
at 100% accuracy.

### Block 3: Drivers — three parallel `_relate` calls

```python
# src/churn_service.py — _drivers()
relate_fields = ["segment", "region", "pet_size"]

def fetch(field):
    return field, client.relate(
        table="customers",
        where={"churned": True},
        relate_field=field,
        limit=10,
    )

with ThreadPoolExecutor(max_workers=3) as pool:
    results = list(pool.map(fetch, relate_fields))
```

Each `_relate` returns lift per value of that field. For example:

```
segment=small_animal_owner → lift 2.3× (32% churn vs 14% baseline, 78 customers)
region=oulu                → lift 1.8× (25% churn vs 14% baseline, 184 customers)
pet_size=large             → lift 0.65× (9% churn vs 14% baseline, 612 customers)
```

The page filters out neutral lifts (`|lift - 1| < 0.15`) and
shows the top 8 by absolute lift. Red chips for `lift > 1`
("drives churn"), green for `lift < 1` ("protective").

### Block 4: Honest accuracy via `_evaluate`

```python
# src/churn_service.py — _evaluate_churn()
where = {
    "segment":         {"$get": "segment"},
    "region":          {"$get": "region"},
    "tenure_months":   {"$get": "tenure_months"},
    "total_orders":    {"$get": "total_orders"},
    "total_spent_eur": {"$get": "total_spent_eur"},
}
client.evaluate(
    table="customers",
    where=where,
    predict_field="churned",
    test_limit=200,
)
```

`$get` reads each held-out customer's value at evaluation time —
without it `_evaluate` would predict the same fixed input 200
times. Returns accuracy + baseAccuracy + n; the view computes
`accuracy_gain_pp = (accuracy - baseAccuracy) × 100` and
renders pass/fail.

Same `where` shape as the per-customer predict (no
`last_order_month` for the same reason).

## Key features

### 1. The timestamp held out, deliberately

The churn label is `last_order_month ≤ 2026-01`. If `_predict`
sees `last_order_month` it reads the label off the same column.
The view excludes it from `where` so Aito predicts from "who
they are" not "when they last bought".

This is the technique to use any time the label is derived from
a column the row carries — exclude the source from the
conditioning, predict from the everything-else.

### 2. Parallel scoring across N customers

100 parallel `_predict` calls in a 8-worker thread pool. Wall-
time ~2 s warm. The right pattern for "score every row in a
table" — production with 2,000 active customers would precompute
once a day rather than per page-load.

### 3. Same `where` shape across predict + evaluate

The features in the leaderboard's `_predict` are byte-identical
to the features in `_evaluate`. That's by design: the accuracy
number you see on the right is the accuracy of the left-side
ranking.

### 4. Drivers + accuracy together

The drivers section answers "why" — which segments / regions /
pet sizes correlate with churn. The accuracy section answers
"how well does Aito predict on held-out data". A reviewer
reading both together gets the full picture: *Aito predicts
at X% accuracy, and the dominant features are these.*

## Data schema

Four new columns on `customers`:

```json
{
  "customers": {
    "type": "table",
    "columns": {
      "customer_id":      { "type": "String" },
      "segment":          { "type": "String" },
      "pet_size":         { "type": "String", "nullable": true },
      "region":           { "type": "String" },
      "tenure_months":    { "type": "Int" },
      "total_orders":     { "type": "Int" },
      "total_spent_eur":  { "type": "Decimal" },
      "last_order_month": { "type": "String", "nullable": true },
      "churned":          { "type": "Boolean" }
    }
  }
}
```

`total_orders`, `total_spent_eur`, `last_order_month` are
backfilled by `data/generate_fixtures.py` from the orders fixture
in a post-pass. `churned` is the deterministic label:
`last_order_month ≤ 2026-01`.

The churn signal is engineered into the order-month distribution
at fixture-gen time, with `_churn_propensity(customer, n_orders)`
giving each non-persona customer a feature-driven probability of
being "churning" (=  having no orders in the last 5 months).
Personas are never churned — they drive the For You demo and
have to stay active.

## Tradeoffs and gotchas

- **`last_order_month` is the strongest possible feature, and we
  don't use it**. Including it makes `_predict` trivial (100%
  accuracy). Excluding it forces Aito to learn from the structural
  features, which is the genuinely-useful prediction. A real
  product would offer both: "predict churn from features alone"
  (proactive scoring) and "predict churn from features + recency"
  (validation).
- **`_predict` of a Boolean returns true / false as hits**. The
  service walks the hit list looking for `feature: true` and
  reads its `$p`. Don't assume the first hit is the answer —
  Aito may return `false` first if the baseline favours it.
- **`pet_size` is nullable**. cat_owner and aquarium_owner rows
  don't have a pet_size. `_predict` errors on `where:
  {pet_size: null}`, so the service drops the key when the
  value is null.
- **100 parallel `_predict` calls is the costliest page**.
  Mitigated by the 30-minute cache. Production scoring should
  precompute once per night rather than per-page-load.
- **`_relate` over `pet_size` only covers the segments that have
  one**. The result is "of pet_size=large customers, what's the
  churn rate", which is over-indexed on dog_owner + multi_pet.
  This is the right shape for the demo — the alternative would
  be three separate calls per (segment, pet_size) combination.

## What this demo abstracts away

- **Per-customer retention recommendation**. "Offer this
  customer 20% off cat food." That's `_recommend` from the
  per-customer feature row with `goal: {churned: false}`. A
  natural follow-up; not in this PR.
- **Cohort retention curves**. Monthly cohort decay over time.
  Purchase Analytics or a new view is the right surface.
- **Configurable churn windows**. The 90-day cutoff is
  hardcoded. Production would expose it as a parameter.
- **Multi-class churn states**. Active / lapsing / churned /
  reactivated. The label is binary here.

## Try it live

[**Open Churn**](http://localhost:8500/churn/). Cold load is
~5 s (100 parallel predicts + 3 relates + 1 evaluate); cache
for 30 minutes after.

```bash
./do dev
# → http://localhost:8500/churn/
```

Watch the at-risk leaderboard: high-confidence rows (red chip)
tend to cluster on `small_animal_owner` + `oulu` + low total
orders — the drivers section on the right makes the pattern
explicit.
