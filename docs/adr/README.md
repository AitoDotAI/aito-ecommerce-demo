# Architecture Decision Records

One ADR per non-trivial design decision. Use `0000-template.md` as
the starting point.

| # | Title | Status |
|---|---|---|
| 0001 | [Scaffold + stack mirrored from `aito-erp-demo`](0001-scaffold-and-stack.md) | Accepted |
| 0002 | [Data model + deterministic fixtures](0002-data-model-and-fixtures.md) | Accepted |
| 0003 | [Aito schema, data loader, and query-method surface](0003-aito-schema-and-loader.md) | Accepted |
| 0004 | [Layout shell + design tokens](0004-layout-shell.md) | Accepted |
| 0005 | [Dashboard view + overview_service](0005-dashboard.md) | Accepted |
| 0006 | [Smart Search — predictive re-ranking](0006-smart-search.md) | Accepted |
| 0007 | [For You — personalised tile grid + persona switcher](0007-for-you.md) | Accepted |
| 0008 | [Bought Together — order-level co-occurrence via `_relate`](0008-bought-together.md) | Accepted |
| 0009 | [Product Filling — multi-field `_predict`](0009-product-filling.md) | Accepted |
| 0010 | [Evaluation — honest pass/fail across four models](0010-evaluation.md) | Accepted |
| 0011 | [Purchase Analytics + Pattern Explorer](0011-analytics-and-patterns.md) | Accepted |
| 0012 | [Feedback — multi-field `_predict` over review text](0012-feedback-multi-predict.md) | Accepted |
| 0013 | [Churn — the killer Understand-section view](0013-churn-prediction.md) | Accepted |
| 0014 | [Demand Forecast — `_predict units_sold` over monthly_sales](0014-demand.md) | Accepted |
| 0015 | [Inventory Intelligence — the killer Operate view](0015-inventory.md) | Accepted |
| 0016 | [Price Intelligence — fair-band + sweet-spot `_relate`](0016-price.md) | Accepted |
| 0017 | [Customer-profile traits, product tags, real names](0017-customer-profiles-and-tags.md) | Accepted |
| 0018 | [Markdown decision view](0018-markdown.md) | Accepted |
| 0019 | [Cart-completion view](0019-cart-completion.md) | Accepted |
| 0020 | [Win-back campaign view](0020-winback.md) | Accepted |
| 0021 | [Impressions table and a real recommendation KPI](0021-impressions-and-recommendation-kpi.md) | Accepted |
| 0022 | [Basket rule mining (association rules as a live query)](0022-basket-rule-mining.md) | Accepted |
| 0024 | [Precompute-and-serve store for heavy read endpoints](0024-precompute-and-serve-store.md) | Accepted |
| 0025 | [Migrate to Aito API v2 (Rep2), staged in a separate env](0025-v2-migration.md) | Proposed |
| 0026 | [Smart Search as one three-way blend — text × meaning × purchase probability](0026-three-way-smart-search.md) | Proposed |
| 0027 | [Purchase data with a lifecycle — restocking, and a starter kit that grows](0027-purchase-lifecycle-data.md) | Accepted |
| 0028 | [Product Insights — one product, its funnel and its buyers](0028-product-insights.md) | Accepted |
| 0029 | [Price what-if — set a price, see units, profit and why](0029-price-what-if.md) | Accepted |
| 0030 | [Shoppers with a story — personas, guided kits, seasons, routines](0030-shoppers-with-a-story.md) | Accepted |
| 0031 | [An interactive shop, and the owner's view of its patterns](0031-interactive-shop-and-owner-analytics.md) | Accepted |
| 0032 | [Product states — recommend a product as it is this month](0032-product-states.md) | Accepted |
| 0033 | [Only what a shop can observe — impressions, contexts and customers](0033-only-what-a-shop-observes.md) | Accepted |
| 0034 | [A business buyer's next order, on real data (UCI Online Retail II)](0034-business-reorders-on-real-data.md) | Accepted |
| 0035 | [The data promotion is a step of the deploy](0035-data-promotion-in-the-deploy.md) | Accepted |
| 0036 | [Backtest the reorder suggestion on a merchant's own orders](0036-reorder-backtest-on-a-merchants-orders.md) | Accepted |
| 0037 | [An evidence section, kept apart from the demo](0037-an-evidence-section.md) | Accepted |
| 0038 | [Actionable product states, shoppers who react differently, and a product manager's view](0038-actionable-product-states.md) | Accepted |
| 0039 | [Reviews with consequences — clicks, purchases, NPS, churn, demand and price](0039-reviews-with-consequences.md) | Accepted |
| 0040 | [Where customers come from — sources, landing pages, first orders and who stays](0040-acquisition-funnel.md) | Accepted |
| 0041 | [One view per job — the site's structure](0041-one-view-per-job.md) | Accepted |
| 0042 | [Ask the store — the levers as agent tools](0042-ask-the-store.md) | Accepted |
| 0043 | [Pull a lever in a sandbox, and watch the shop react](0043-pull-a-lever-in-a-sandbox.md) | Accepted |
| 0044 | [What a shop can know about a person](0044-what-a-shop-can-know-about-a-person.md) | Accepted |
| 0045 | [One source for showings and sales](0045-one-source-for-showings-and-sales.md) | Accepted |
| 0046 | [Catalogue manager — import, fill, edit, and see the estimates](0046-catalogue-manager.md) | Accepted |
| 0047 | [Chained baskets — each order points to the one before it](0047-chained-baskets.md) | Accepted |
| 0048 | [Product KPIs by properties — clicks and purchases, explained, and editable](0048-product-kpis-by-properties.md) | Accepted |
| 0049 | [Data release 3 — price that the data can learn, and the listing as product state](0049-data-release-3-price-and-listing-state.md) | Accepted for release 3a |
| 0050 | [Product pricing tab with an editable list price, and the funnel](0050-product-pricing-tab-and-funnel.md) | Accepted for release 3a |
| 0051 | [Actions and their outcomes — retention, advertising, availability and customer messages](0051-actions-and-their-outcomes.md) | Slice 1 live |
| 0052 | [The shopkeeper agent — routine runs with a confidence gate and an approval step](0052-shopkeeper-agent.md) | Accepted |
| 0053 | [Customer profiles — how customers shop, and who responds to what](0053-customer-profiles.md) | Accepted |
| 0054 | [Rules and agents: what the shop decides by calculation, and what a model does](0054-rules-and-agents.md) | Accepted |
| 0055 | [Customers as generic analytics: a time range, more narrowing tabs, and the raw rows](0055-customers-as-analytics.md) | Accepted |
| 0056 | [Planted incidents: one loud batch recall and three quiet quality problems](0056-planted-incidents.md) | Accepted |
| 0057 | [The stock routine as a rule, and the first real agent: product entry](0057-stock-rule-and-product-entry-agent.md) | Accepted, part 1 built |
| 0058 | [Feedback with text and context: NPS comments, reviews that read like their stars, and metadata inferred from them](0058-feedback-text.md) | Accepted |
| 0059 | [The journey of a segment: the months around the last order, those who left against those who stayed](0059-customer-journey.md) | Accepted |

ADRs are externally legible — an outside developer should understand
the decision and its rationale without project-internal context. Keep
the **Aito usage** and **Acceptance criteria** sections concrete.

A merged ADR is not a contract you can't break; it's the *latest* word
on a decision. To revisit, open a superseding ADR — don't edit history
in place.
