# ADR 0013: Churn — the killer Understand-section view

**Status:** Accepted
**Date:** 2026-05-12
**Deciders:** Antti

## Context

E-commerce churn is the single most economically-relevant
prediction a retailer can make. Identify who's about to stop
buying and you can retarget; identify the drivers (segment,
region, tenure, basket size) and you can build retention
strategy. Most shops do this with rule-of-thumb tables ("anyone
who hasn't ordered in 90 days is at risk") and a CSV export to
the email tool.

This view runs the actual classifier: given a customer's
features (segment, pet_size, region, tenure_months,
total_orders, total_spent_eur), Aito's `_predict churned`
returns P(churned=true) — without using the timestamp the label
was derived from.

This is the **killer feature** of the Understand section. The
narrative: "Aito ranks your customers by churn risk in one
query, surfaces the drivers, and tells you its accuracy honestly."

## Aito usage

Four query types, in order:

**1. KPI counts** — three `_search limit=0` calls:

```json
{ "from": "customers", "limit": 0 }
{ "from": "customers", "where": { "churned": true }, "limit": 0 }
```

**2. At-risk leaderboard** — N parallel `_predict` calls. For
each active customer:

```json
{
  "from": "customers",
  "where": {
    "segment": "small_animal_owner",
    "region": "oulu",
    "tenure_months": 24,
    "total_orders": 2,
    "total_spent_eur": 47.5
  },
  "predict": "churned"
}
```

The `where` carries only the **feature** columns — deliberately
no `last_order_month`. With the timestamp included, Aito reads
the label directly off the same column the label was derived
from and "predicts" at 100% accuracy. The narrative is "predict
churn from who they are, not from when they last ordered."

**3. Drivers** — three parallel `_relate` calls, one per discrete
feature:

```json
{
  "from": "customers",
  "where": { "churned": true },
  "relate": "segment"
}
```

Same body with `relate: "region"` and `relate: "pet_size"`.
Returns lift per value of that field — "small_animal_owner segment
→ 2.3× churn lift".

**4. Accuracy** — one `_evaluate` over a 200-row sample:

```json
{
  "testSource": { "from": "customers", "limit": 200 },
  "evaluate": {
    "from": "customers",
    "where": {
      "segment":        { "$get": "segment" },
      "region":         { "$get": "region" },
      "tenure_months":  { "$get": "tenure_months" },
      "total_orders":   { "$get": "total_orders" },
      "total_spent_eur": { "$get": "total_spent_eur" }
    },
    "predict": "churned"
  },
  "select": ["accuracy", "baseAccuracy", "n"]
}
```

`$get` reads each held-out row's value — without it `_evaluate`
would predict the same fixed input 200 times.

## Decision

### Schema additions to `customers`

Four new columns, backfilled at fixture-gen time from the order
history:

| Column | Type | Notes |
|---|---|---|
| `total_orders` | Int | Count of orders this customer placed |
| `total_spent_eur` | Decimal | Sum of order totals |
| `last_order_month` | String, nullable | YYYY-MM of most recent order |
| `churned` | Boolean | `last_order_month ≤ 2026-01` (3 months before frozen demo today) |

### Churn signal engineered into the order distribution

`data/generate_fixtures.py` decides per non-persona customer
whether they're "churning" based on feature contributions:

```python
def _churn_propensity(customer, n_orders) -> float:
    p = 0.02                                            # base
    if customer.tenure_months > 18:    p += 0.06        # drift
    if customer.tenure_months < 4:     p -= 0.02        # too new
    if n_orders <= 3:                  p += 0.06        # low engagement
    if customer.segment == "small_animal_owner":  p += 0.07
    if customer.segment == "aquarium_owner":      p += 0.05
    if customer.segment == "cat_owner":           p -= 0.02
    if customer.region == "oulu":                 p += 0.04
    if customer.region == "helsinki":             p -= 0.02
    return max(0.01, min(0.40, p))
```

Decision is keyed on `customer.customer_id` (sub-RNG) so it
doesn't perturb the main fixture RNG sequence — the existing
demo signals (dog-food→dental lift, persona overlaps) stay
byte-identical.

For churning customers, the order-month picker restricts to
months `≤ 2025-11`. The 2-month gap between `2025-11` and the
2026-01 cutoff stops random month picks from straddling the
boundary.

Personas (Maija / Olli / Saara) are never churned — they drive
the For You demo and have to stay active.

### Frontend layout

`/churn` route, four blocks:

1. **KPI strip** — total / active / churned / churn-rate cards.
2. **At-risk leaderboard** (left, 60% width) — top 20 active
   customers ranked by P(churned). Risk chip color-coded by
   confidence band (red ≥ 0.70, yellow 0.45-0.70, grey < 0.45).
3. **Drivers** (right, top) — list of feature → value rows with
   lift chips. Up-arrow + red for `lift > 1` (drives churn),
   down-arrow + green for `lift < 1` (protective).
4. **Evaluation** (right, bottom) — accuracy + baseline + gain
   pp, with the "timestamp held out" caveat called out in the
   subtitle.

## Acceptance criteria

- [x] A user can open `/churn` and see the 4-card KPI strip with a
      current churn rate in the 25-35% band.
- [x] The at-risk leaderboard shows 20 customers sorted by P(churn)
      descending with risk chips.
- [x] The drivers list surfaces 3-5 strong drivers (lift > 1.3 or
      < 0.7) with the underlying support counts.
- [x] The evaluation card shows held-out accuracy ≥ baseline + 10pp
      (i.e. the model passes its own bar).
- [x] The Aito panel shows one of the live query bodies (the
      per-customer predict, with the features substituted).

## Demo impact

The narrative arc closes with Churn as the strongest "Aito gives
you something a rule table can't" view in the demo. Pairs with
Evaluation (ADR 0010) — Evaluation shows "Aito tells you when it
doesn't know"; Churn shows "Aito ranks the customers correctly
when it does know".

Adds a **sixth demo moment** to the canonical script (in addition
to the original five): "Aito ranks 2,000 active customers by churn
risk in 2 seconds — the at-risk list isn't a rule table, it's a
prediction with confidence intervals."

## Out of scope

- **Per-customer retention recommendation** ("offer this customer
  20% off cat food"). That's `_recommend` from the
  per-customer-feature row with `goal: {churned: false}` — a
  follow-up.
- **Churn over time** (cohort retention curves). The view is
  point-in-time. Pattern Explorer or Purchase Analytics is the
  right surface for monthly cohorts.
- **Churn definitions other than 90 days**. The cutoff is
  hardcoded to `2026-01`. A real product would expose the window
  as a parameter; we picked 90 days because it's the SaaS /
  e-commerce default.
- **Multi-class churn** (active / lapsing / churned / reactivated).
  The label is binary; a 3-state model would need a different
  schema.

## Consequences

**Good:**
- The first view in the demo that uses `_predict` at scale — N
  parallel calls per request, the right pattern for "score every
  row in a table".
- Demonstrates the "evaluate with timestamp held out" technique
  that's broadly applicable when you're predicting a label
  derived from time data.
- The drivers section gives `_relate` a second worked example
  (after Bought Together / Pattern Explorer), this time over a
  classification target instead of co-occurrence.

**Bad:**
- 100 parallel `_predict` calls (top_n × 5 = 100 candidates) are
  the costliest single page in the demo — ~2 s warm, ~5 s cold.
  Mitigated by 30-minute cache; production with N = 2,000
  customers would need precompute.
- The churn rate of ~30% is dataset-specific. A real customer's
  data could vary widely; the demo's narrative numbers won't
  transfer.

## Notes

The "predict without using the timestamp" technique is borrowed
from the accounting demo's anomaly detection (where the
prediction target is `gl_code` and timestamp would similarly
leak the label).

The decision to inject churn via a sub-RNG (keyed on customer_id)
rather than the main RNG is a deliberate signal-engineering
choice — see ADR 0002 §"Engineered signal" for the precedent.
Future churn-signal tuning should follow the same isolation
pattern so the existing demo moments don't drift.
