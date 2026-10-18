# Aito core findings, 2026-10-18 (ADR 0032, test env `states`)

Found while probing ADR 0032's data on `shared.aito.ai`, Aito 2.11.4, env
`states` (cloned from master, every table then dropped and reloaded by
`./do reset-data` from the `product-states` branch). All read-only.

## 1. `_recommend` reports baseP 1.0 under `where {"just_bought": false}`

```json
POST /env/states/api/v2/_recommend
{ "from": "impressions", "where": { "just_bought": false },
  "recommend": "product_sku", "goal": { "purchased": true },
  "select": ["$p", "$why"], "limit": 1 }
```

| env | `$why` baseP | top `$p` | P(purchased \| just_bought = false) by count |
|---|---|---|---|
| `states` | **1.000** | 0.990 | 14,239 / 115,005 = 0.124 |
| master | 0.105 | 0.274 | (the ADR 0030 data) |

The column is `{"type": "Boolean", "nullable": false}` in both envs. On
`states`, `{"just_bought": true}`, `{"surface": "search"}` and every
customer field alone give baseP 0.122 (the overall rate). Only the
`false` value of this one column trips it, and any `where` that holds it
inherits the effect: the Shop's grid ranks dog treats at p 1.0 for a
guinea-pig owner ("Goes with your cart ×1491").

What differs between the envs is the data: `states` has 116,616
impressions with a new link column `product_state` (15,157 distinct
values); master has 125,935 without it. Not yet tried: the same data
without the `product_state` column, to tell whether the link matters.

## 2. `_recommend` on a sparse, high-cardinality link target is overconfident

`_recommend product_state` (15,157 candidates, ~8 impressions each)
against `_predict` for the same `where` and candidate:

| where | candidate | `_recommend` `$p` | `_predict` p(true) | rows matching |
|---|---|---|---|---|
| `{"customer_segment": "dog_owner"}` | SKU-PT-0008-2024-09 | 0.931 | 0.119 | 0 |
| the Shop's full context (holds `just_bought: false`) | SKU-PT-0168-2026-04 | 0.957 | 0.431 | 0 |

With no matching rows, `_recommend` ranks candidates first at 0.931.
The second row may be finding 1 again.

## 3. (Seen on master too) `where {"clicked": false}` gives top p 0.997

A purchase requires a click in this data, so P(purchased | not clicked)
is 0, yet `_recommend` tops at 0.996 (master) / 0.997 (`states`).

## What works (for the cheatsheet once confirmed)

- `where` on `product_state.month` narrows `_recommend product_state`'s
  candidates to that month.
- A two-link `where` (`product_state.product_sku.category`, and the rule's
  `$or` through two links) filters candidates.
- Field-form `_relate` through one link (`product_state.on_offer`,
  `product_state.discount_band`) and through two links
  (`product_state.product_sku.category`) both answer, with sane counts:
  budget shoppers' purchases relate to `on_offer` at 2.22×.
