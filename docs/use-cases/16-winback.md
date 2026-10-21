# Win-back Campaigns — empirical revenue impact per send

![Win-back](../../screenshots/inspect/16-winback-default.png)

*For each currently-churned customer, Aito's `_recommend
product_sku from winback_campaigns` ranks products by predicted
email response rate (goal `responded: true`); `_estimate
order_value_eur` per suggestion gives the AOV forecast.
Revenue impact = `response_p × AOV − €0.50 / email`. Ports
Netigate's "action + impact estimation" pattern to e-commerce.*

## Overview

The Churn view surfaces *who's at risk*. Customers who've already
churned were a dead end until this view. For each churned customer
(top-20 by lifetime €), Win-back predicts which products they'd
respond to in a re-engagement email + the revenue impact if they do.

On the synthetic demo data (env `observable`) the view predicts about
€1,050 recoverable revenue across 20 targets at a €30 campaign cost.
The data is generated, so this illustrates the arithmetic, not a result.

Three blocks per page load:

1. **KPI strip** — targets identified / predicted recoverable
   revenue / average response rate / campaign cost
2. **Customer table** — 20 rows with name, profile, last order,
   lifetime €, expected recovery €
3. **Per-row expansion** — click to reveal top-3 product
   suggestion cards with per-product response rate + AOV +
   expected revenue €

## How it works

### The `winback_campaigns` historical table

~2,400 synthetic past re-engagement emails sent to then-inactive
customers. The outcome label `responded` is what Aito learns from
to predict response rates for currently-churned customers.

Engineered correlations baked into the fixture. The generator draws
them from each customer's hidden traits; Aito never sees those traits
(ADR 0033), only the customer, their staple and the recency:

| Planted in the generator | Multiplier on base 0.05 |
|---|---|
| a premium shopper (hidden trait) | ×2.4 |
| a budget shopper (hidden trait) | ×0.5 |
| `recency = 0-90d` | ×1.6 |
| `recency = 180d+` | ×0.4 |
| product for the household's pets | ×3.0 |
| product for other pets | ×0.35 |
| a health-focused shopper (hidden trait) + dietary product | ×1.5 |
| product in the customer's staple "pet/category" (ADR 0027) | ×2.5 |
| a "pet/category" the customer never bought | ×0.5 |

Clipped to `[0.005, 0.35]` so even strong cases stay within
real-world re-engagement campaign ranges.

### Product ranking — `_recommend`

```python
# src/winback_service.py — _recommend_products()
client.recommend(
    table="winback_campaigns",
    where={
        "customer_id":              customer["customer_id"],
        "customer_staple_category": staple,           # "dog/dry-food", or "none"
        "recency_bucket":           recency_bucket,   # from last_order_month
    },
    recommend_field="product_sku",
    goal={"responded": True},
    based_on=["pet_type", "category", "brand"],   # paths relative to recommend target
    limit=8,
)
```

- `customer_id` is a link to `customers`: Aito reads the customer
  through it (what they declared, and their own earlier sends).
- `customer_staple_category` is derived from the customer's orders
  (their most-bought "pet/category", at least 3 lines), as their send
  rows record it.
- `recency_bucket` is derived from `last_order_month`.

For each candidate `product_sku`, Aito returns
`$p = P(responded=true | this product, this customer's context)`
plus the linked product fields (name / brand / price). `basedOn`
paths are relative to the recommend target (`product_sku` →
linked `products` table), so bare column names.

### AOV per suggestion — `_estimate`

```python
# src/winback_service.py — _predict_aov_for_product()
client.estimate(
    "winback_campaigns",
    where={
        "customer_id":              customer["customer_id"],
        "customer_staple_category": staple,
        "recency_bucket":           recency_bucket,
        "product_sku":              product_sku,
        "responded":                True,
    },
    estimate_field="order_value_eur",
)
```

Conditional expectation given response. `responded: true` in the
where filters out the AOV-0 rows so the estimate reflects what
the customer would actually spend if they came back.

### Revenue impact formula

```python
expected_revenue = response_p × predicted_aov − €0.50 / email
```

Mirrors Netigate's `euro_saved = (p_churn − p_churn_after) × arr −
cost` shape. Per-customer recovery = sum across 3 suggested
products. €0.50/email is a representative SendGrid / Mailchimp
re-engagement send cost.

## Key features

### 1. Empirical, not simulated

The response rate isn't a hand-tuned multiplier — it's Aito
estimating P(responded=true) from the historical campaigns table.
When a customer's profile matches an under-represented slice, the
prediction has correspondingly low confidence; the KPI strip's
"average response rate" surfaces that honestly.

### 2. Top-20 by lifetime €, not by predicted recovery

Targets the customers worth re-engaging — high-LTV churned
segment where the email cost pays off. Could alternatively rank
by predicted recovery; current choice is "value the merchant
already has, not value to be created".

### 3. Real Finnish customer names

The `customers.name` column carries deterministic Finnish first +
last names (3,800 unique combinations for 2,997 generic
customers). At-risk rows read "Riitta Aaltonen / 2026-01 /
€411.31 / €302.32" — not "CUST-00042 / NULL / NULL". Brings the
view into CRM-grade legibility.

## Data schema

New table — `winback_campaigns` — added in ADR 0017 / 0020:

```json
{
  "winback_campaigns": {
    "type": "table",
    "columns": {
      "campaign_id":            { "type": "String" },
      "customer_id":            { "type": "String", "link": "customers.customer_id" },
      "product_sku":            { "type": "String", "link": "products.sku" },
      "sent_month":             { "type": "String" },
      "recency_bucket":         { "type": "String" },
      "customer_staple_category": { "type": "String" },
      "product_pet_type":       { "type": "String" },
      "product_category":       { "type": "String" },
      "product_brand":          { "type": "String" },
      "responded":              { "type": "Boolean" },
      "order_value_eur":        { "type": "Decimal" }
    }
  }
}
```

The customer's traits are not columns: the link to `customers` carries
what they declared (ADR 0033).

## Tradeoffs and gotchas

- **Customers with few sends of their own** lean on their staple and
  recency: two such customers with the same staple and recency get
  similar suggestions.
- **Response rates can read high.** Aito's `_recommend` returns
  the TOP-ranked candidates; for high-signal slices they cluster
  near the engineered ceiling (35 %). The KPI "average response
  rate" across all proposed sends lands around 80 % which is
  generous vs real-world re-engagement (~15-20 %). Disclose in
  the demo script.
- **No live email send.** This is a recommendation view, not a
  CRM integration. The "send email" button is a future ADR.

## What this demo abstracts away

- **Email-platform integration** (SendGrid / Mailchimp / Iterable)
- **Multi-touch attribution** (currently models the email as the
  only touchpoint)
- **Sequential / drip campaigns** ("if no response in 7 days,
  send next product")
- **Click → open → conversion tracking** (we model the outcome
  binary `responded` only)
- **Holdout-group lift measurement** (would need control-cohort
  experiments)

## Try it live

[**Open Win-back**](http://localhost:8500/winback/). Cold load
~15 s (20 customers × 1 recommend + 3 estimates each, parallel
across customers); cached 30 minutes. Click any row to expand
its three product cards — each shows the per-product response
rate, AOV, and expected € contribution to the customer's
recovery total.
