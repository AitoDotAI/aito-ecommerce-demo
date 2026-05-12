# ADR 0013: Churn — the killer Understand-section view

**Status:** Accepted
**Date:** 2026-05-12
**Deciders:** Antti

## Context

E-commerce churn is the single most economically-relevant
prediction a retailer can make. Identify who's about to stop
buying and you can retarget; identify the drivers and you can
build retention strategy. Most shops do this with rule-of-thumb
tables ("anyone who hasn't ordered in 90 days is at risk") and
a CSV export to the email tool.

This view runs the actual classifier. The training shape is a
**panel** — one row per customer per month they were a customer
— with this-month aggregates (visits, purchases, spent_eur),
denormalised profile features (segment, pet_size, region,
tenure-at-this-month), the latest review snapshot (rating,
sentiment, category), and the **forward-looking** target
`churned_in_3_months`.

Aito's `_predict churned_in_3_months` over the latest
customer_month row of each active customer returns P(this
customer will be churned 3 months from now). That's the actually-
useful business question — not "are they churned right now"
(trivially answerable from `last_order_month`) but "are they
*becoming* churned".

This is the **killer feature** of the Understand section.

## Aito usage

Four query types, in order:

**1. KPI counts** — three `_search limit=0` calls:

```json
{ "from": "customers", "limit": 0 }
{ "from": "customers", "where": { "churned": true }, "limit": 0 }
```

**2. At-risk leaderboard** — N parallel `_predict` calls over
the customer_months panel. Pull every active customer's latest
row, score each:

```json
{
  "from": "customer_months",
  "where": {
    "segment": "small_animal_owner",
    "region": "oulu",
    "visits": 4,
    "purchases": 0,
    "spent_eur": 0,
    "tenure_months_at_month": 18,
    "latest_rating": 2,
    "latest_sentiment": "negative",
    "latest_category": "shipping"
  },
  "predict": "churned_in_3_months"
}
```

The `where` carries the row's feature columns — time-series
(visits, purchases, spent_eur), profile (segment, region,
pet_size, tenure-at-this-month), and latest-review snapshot
(rating, sentiment, category).

The active-customer pre-filter is one `_search`:

```json
{
  "from": "customer_months",
  "where": { "month": "2026-04", "churned_in_3_months": false },
  "limit": 120
}
```

This returns every active customer's row at the cutoff month
(`DEMO_TODAY_YYYYMM`).

**3. Drivers** — five parallel `_relate` calls over the panel,
one per discrete feature (segment / region / pet_size /
latest_category / latest_sentiment):

```json
{
  "from": "customer_months",
  "where": { "churned_in_3_months": true },
  "relate": "segment"
}
```

Same shape with `relate` swapped out. Returns lift per value
of that field — "small_animal_owner segment → 1.8× lift in the
churned subset". The latest-review fields surface the feedback↔
churn correlation: "latest_sentiment=negative → 2.4× lift".

**4. Accuracy** — one `_evaluate` over a 300-row sample of
customer_months:

```json
{
  "testSource": { "from": "customer_months", "limit": 300 },
  "evaluate": {
    "from": "customer_months",
    "where": {
      "segment":                { "$get": "segment" },
      "region":                 { "$get": "region" },
      "tenure_months_at_month": { "$get": "tenure_months_at_month" },
      "visits":                 { "$get": "visits" },
      "purchases":              { "$get": "purchases" },
      "spent_eur":              { "$get": "spent_eur" }
    },
    "predict": "churned_in_3_months"
  },
  "select": ["accuracy", "baseAccuracy", "n"]
}
```

`$get` reads each held-out row's value — without it `_evaluate`
would predict the same fixed input 300 times.

## Decision

### Schema additions

**`customers` (4 backfilled columns)** — kept for the
point-in-time KPI strip (`_search where {churned: true}` counts):

| Column | Type | Notes |
|---|---|---|
| `total_orders` | Int | Count of orders this customer placed |
| `total_spent_eur` | Decimal | Sum of order totals |
| `last_order_month` | String, nullable | YYYY-MM of most recent order |
| `churned` | Boolean | `last_order_month ≤ 2026-01` (3 months before frozen demo today) |

**`customer_months` (new table)** — panel data, one row per
customer per month they were a customer:

| Column | Type | Notes |
|---|---|---|
| `customer_month_id` | String, PK | `CUST-00001-2025-03` |
| `customer_id` | String, link → customers | |
| `month` | String | YYYY-MM |
| `visits` | Int | Synthesised per-month sessions, decay-before-churn applied |
| `purchases` | Int | Orders in this month |
| `spent_eur` | Decimal | Sum of orders this month |
| `segment` / `pet_size` / `region` | String | Denormalised profile (Aito single-hop) |
| `tenure_months_at_month` | Int | Months since first order |
| `latest_rating` | Int, nullable | Most-recent review rating in this month |
| `latest_sentiment` | String, nullable | Sentiment of that review |
| `latest_category` | String, nullable | Category of that review |
| `churned_in_3_months` | Boolean | **TARGET** — see "Forward labels" below |

Volume: ~26,500 rows (3,000 customers × ~9 months average).

**`reviews` (one new column)** — the same forward-looking label,
per review:

| Column | Type | Notes |
|---|---|---|
| `churn_within_90d` | Boolean | True iff reviewer has no orders in 3 months after review |

Powers the Feedback view's 4th `_predict` — churn risk straight
from the review text.

### Forward labels

For a customer_months row at month M:

```
churned_in_3_months[M] = customer.churned  AND  M ≥ customer.last_order_month
```

- Active customer (not currently churned): every row's label is
  False. The features are stable; Aito learns "active customer
  features → not churning".
- Churned customer (last order at L, L ≤ 2026-01): rows for
  M < L have False (they were still active then), rows for M ≥ L
  have True (they had stopped by then). The transition rows
  (M = L) are where Aito learns the leading-indicator pattern.

For a review created at month R by customer C:

```
churn_within_90d[R, C] = C.churned  AND  R ≥ C.last_order_month
```

Same structure. Reviews written near the customer's last activity
have True; reviews written during active periods have False.

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

### Visit-decay synthesis

`visits` is generated per customer per month from a segment base
rate × decay factor + Gaussian noise. The decay applies only to
churning customers, over the 2-3 months before their last order:

| Offset from last_order | Multiplier |
|---|---|
| ≤ −3 months | 1.0 (normal activity) |
| −2 | 0.75 |
| −1 | 0.50 |
| 0 (last order month) | 0.30 |
| +1 | 0.10 |
| ≥ +2 | 0.04 |

For active customers, multiplier = 1.0 across all months. The
resulting "active vs churned latest-month visits" gap is ~10 vs
~0.5 — Aito's strongest learnable feature.

### Frontend layout

`/churn` route, four blocks:

1. **KPI strip** — total / active / churned / churn-rate cards
   from the customers table (point-in-time totals).
2. **At-risk leaderboard** (left, 60% width) — top 20 active
   customers ranked by P(churned_in_3_months). Table columns
   surface the *features that drive the score*: visits this
   month, spend this month, latest rating, plus segment+region.
   Risk chip color-coded by band.
3. **Drivers** (right, top) — list of feature → value rows
   sorted by |lift - 1|. Includes the latest-review fields —
   "latest_sentiment=negative → 2.4× lift" makes the
   feedback↔churn connection visible.
4. **Evaluation** (right, bottom) — accuracy + baseline + gain
   pp, with the "300-row held-out sample" caveat.

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
