# Use case guides

Per-view implementation guides for the Predictive E-commerce
demo. Each guide pairs a hero screenshot, the actual Aito query
shape, the service-side Python code that produced it, the
relevant schema excerpt, and honest notes on tradeoffs + what
the demo abstracts away.

| # | Guide | Aito features used |
|---|-------|--------------------|
| 1 | [Dashboard](01-dashboard.md) | `_search limit=0` × 4 + `_relate` × 6 in parallel + Python aggregation |
| 2 | [Smart Search](02-smart-search.md) | `_search` baseline + `_recommend` with `where` + `goal` per persona |
| 3 | [For You](03-for-you.md) | `_recommend product_sku` with persona-segment goal, no `name $match` |
| 4 | [Bought Together](04-bought-together.md) | `_relate` over denormalised `orders.line_categories` Text column |
| 5 | [Purchase Analytics](05-purchase-analytics.md) | `_search` with `offset` pagination, Python aggregation per segment/month |
| 6 | [Pattern Explorer](06-pattern-explorer.md) | Same `_relate` body as Bought Together, no lift filter, three-band rendering |
| 7 | [Product Filling](07-product-filling.md) | `_predict` × 5 parallel for catalog enrichment, `$why` per field |
| 8 | [Evaluation](08-evaluation.md) | `_evaluate` × 4 parallel with `testSource` + `$get` substitution, honest failure |
| 9 | [Feedback](09-feedback.md) | `_predict` × 4 parallel over review `text` — category, sentiment, assigned_to, churn_within_90d |
| 10 | [Churn](10-churn.md) | `_predict` × N parallel over customer_months panel for at-risk leaderboard, `_relate` × 5 for drivers (incl. latest review fields), `_evaluate` for accuracy |
| 11 | [Demand Forecast](11-demand-forecast.md) | `_predict units_sold` per top-mover SKU over the `monthly_sales` panel + 4 parallel `_relate` for seasonality + `_evaluate` |
| 12 | [Inventory Intelligence](12-inventory-intelligence.md) | `_predict units_sold` per critical SKU + days-of-supply arithmetic; reorder queue ranked by revenue at risk in € |
| 13 | [Price Intelligence](13-price.md) | Per-SKU fair-band from `price_history` + 3 parallel `_relate` over discount band ↔ `product_sku.category` |
| 14 | [Markdown Decision](14-markdown.md) | `_estimate units_sold` × 5 markdown levels per overstock SKU + clearance-revenue picker |
| 15 | [Cart Completion](15-cart-completion.md) | `_relate` over `orders.line_categories` × 4 preset checkout carts + `_search` for popular products in top related category |
| 16 | [Win-back Campaigns](16-winback.md) | `_recommend product_sku from winback_campaigns goal {responded: true}` + `_estimate order_value_eur` per suggestion; Netigate action+impact pattern ported |

Each guide is self-contained — read in any order. Prerequisites
(running demo, loaded data) are listed in the project
[README](../../README.md).

## What you'll learn

Reading the guides front-to-back walks you through the demo's
five headline moments (Smart Search rank flip → For You persona
switch → Bought Together 2.72× → Product Filling 5 fields →
Evaluation honest failure) and the Aito patterns behind each.
The guides also capture the gotchas that surfaced during the
build — full set in [`../aito-cheatsheet.md`](../aito-cheatsheet.md).

The demo's thirteen views exercise six Aito endpoints: `_search`,
`_match` (via `$match`), `_recommend`, `_relate`, `_predict`,
and `_evaluate`. Every endpoint shows up in at least one guide
— read top-to-bottom for a tour of Aito's predictive surface.
