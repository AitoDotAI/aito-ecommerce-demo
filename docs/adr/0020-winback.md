# ADR 0020 — Win-back campaign view

**Status:** Accepted

## Context

The Churn view surfaces *who's at risk*. Customers who've already
churned were a dead end — the demo had no story for "what do you
do about them?". Marketers asked this every time. The right answer
is a CRM-style win-back campaign: for each churned customer,
predict which product they'd respond to in a re-engagement email,
plus the revenue impact if they do.

Ports the Netigate accounting-demo's "action + impact estimation"
pattern: historical actions with outcome labels let Aito's
`_predict` empirically estimate the response rate per
(customer × action) context, then multiply by the customer's LTV
to surface revenue impact. Same shape; e-commerce flavour.

## Decision

### New `winback_campaigns` table

Historical email re-engagement campaigns sent to then-inactive
customers. The outcome label `responded` is what Aito learns from
to predict response rates for currently-churned customers.

| Column | Type | Purpose |
|---|---|---|
| `campaign_id` | String | primary |
| `customer_id` | String (link → customers) | |
| `product_sku` | String (link → products) | the SKU emailed |
| `sent_month` | String | YYYY-MM |
| `recency_bucket` | String | "0-90d" \| "90-180d" \| "180d+" at send time |
| `customer_segment / pet_size / lifestyle / health_focus` | String | denorm |
| `product_pet_type / category / brand` | String | denorm |
| **`responded`** | Boolean | **the outcome label** |
| `order_value_eur` | Decimal | value of resulting order if responded |

~1800 campaigns generated; 31 % overall response rate.

### Engineered response correlations

| Trait | Multiplier on base 0.10 |
|---|---|
| `lifestyle = premium` | ×2.4 |
| `lifestyle = budget` | ×0.5 |
| `recency = 0-90d` | ×1.6 |
| `recency = 180d+` | ×0.4 |
| Product pet_type matches customer's segment preference | ×3.0 |
| Mismatched product | ×0.35 |
| `health_focus = high` + dietary product | ×1.5 |

Clipped to [0.01, 0.65] per campaign. Audit:
- Premium customers respond **51 %** vs budget **18 %** (~3× ratio)
- Recent (0-90d) respond **42 %** vs old (180d+) **14 %** (~3× ratio)

### Aito query shapes

Per currently-churned customer (target):

1. **Product ranking** — `_recommend product_sku from winback_campaigns`:
   ```json
   {
     "from": "winback_campaigns",
     "where": {
       "customer_lifestyle":   "premium",
       "customer_segment":     "dog_owner",
       "customer_pet_size":    "large",
       "customer_health_focus":"high",
       "recency_bucket":       "0-90d"
     },
     "recommend": "product_sku",
     "goal":      { "responded": true },
     "basedOn":   ["pet_type", "category", "brand"],
     "limit":     8
   }
   ```
   `basedOn` paths are relative to the recommend target — bare
   column names on the linked `products` table (cf. ADR 0017's
   "When do priors actually move the ranking?" — these priors
   matter here because the win-back per-segment slice is thin).

2. **AOV estimate** — `_estimate order_value_eur from winback_campaigns`
   per suggested product, conditioned on the same customer profile
   + `responded: true`. Gives the basket-value forecast.

### Revenue impact formula

Same shape as Netigate's `euro_saved = (p_churn − p_churn_after) ×
arr − cost`. Adapted:

```
expected_revenue = response_p × predicted_aov − email_cost
```

with `email_cost = €0.50` (representative SendGrid / Mailchimp
re-engagement send cost). Per-customer recovery = sum across 3
suggested products.

### Top-N selection

20 customers, sorted by `total_spent_eur` descending. These are
the high-LTV churned segment where re-engagement spend pays off.
Future iteration could weight by predicted recovery instead.

## Acceptance criteria

- A user can open `/winback` and see ~20 churned customers each
  with name, profile, last order, lifetime €, and expected
  recovery €.
- Clicking a row expands to show the top-3 product suggestions
  with predicted response rate, AOV, and expected revenue per
  product.
- KPI strip rolls up: targets identified, predicted recoverable
  revenue, average response rate, campaign cost.
- Customers whose profile has no historical campaigns are
  gracefully omitted (the row doesn't appear).

## Demo impact

- **Churn** stays the "who's at risk" view.
- **Win-back** becomes the "what to do about the lost ones" view.
- KPI table tells the marketer the same way it would on a CRM
  dashboard: total send count, total cost, predicted recovered
  revenue, ROI.

Headline number this demo can stand behind: "Aito identifies
€3 000 in recoverable revenue across 20 win-back targets, at a
€30 campaign cost — 100× ROI." Speaks marketer + CFO at once.

## Out of scope

- **Actual email send.** This is a recommendation engine view, not
  a CRM integration.
- **Multi-touch attribution.** We assume one email per (customer ×
  product) suggestion. Real platforms layer click → open →
  conversion tracking.
- **Sequential / drip campaigns.** Each customer gets 3
  suggestions; we don't model "if no response in 7 days, send
  next".

## References

- Netigate demo's action+impact pattern —
  `aito-accounting-demo`-adjacent task at
  `/home/arau/episto/tasks/netigate-demo/api/server.py:195-201`.
- Customer-profile traits that drive the segmentation — ADR 0017.
- Churn view's `churned` flag — ADR 0013.
- basedOn priors and slice density — `docs/notes/aito-perf-findings.md` §5.
