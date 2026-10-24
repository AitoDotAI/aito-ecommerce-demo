"""Aito table schemas — the single source of truth for the demo's data model.

Extracted from `data_loader` so it can be imported without pulling in the
loader's dependency on `AitoClient`: the compat layer needs the link graph
to reconstruct v1's implicit `select` on v2 (ADR 0025), and `AitoClient`
imports the compat layer, so a `data_loader` import there would be a cycle.

Schemas are data, not loader logic — three modules read them now (the
loader, the v2 env staging, and the compat layer).

See `docs/adr/0003-aito-schema-and-loader.md` for the column-type
rationale — `String` vs `Text` vs `Decimal` — and the link-graph.
"""

from __future__ import annotations


# ── Schemas — keep in lock-step with `docs/aito-cheatsheet.md` ─────
#
# Load order: dict insertion order is the load order. Don't reorder
# without checking the link graph: linkers come after their targets.

SCHEMAS: dict[str, dict] = {
    # 1. products — link target for order_lines.product_sku.
    "products": {
        "type": "table",
        "columns": {
            "sku":       {"type": "String",  "nullable": False},
            # Text so `_search { name: "food" }` tokenises on
            # individual words. Critical for the Smart Search rank-
            # flip moment.
            "name":      {"type": "Text",    "nullable": False},
            "category":  {"type": "String",  "nullable": False},
            "pet_type":  {"type": "String",  "nullable": False},
            "brand":     {"type": "String",  "nullable": False},
            "price_eur": {"type": "Decimal", "nullable": False},
            # Nullable triple — drives the Product Filling demo's
            # input pile. ~5 % of products have ≥ 2 of these nulled.
            "weight_kg": {"type": "Decimal", "nullable": True},
            "dietary":   {"type": "String",  "nullable": True},
            "tax_class": {"type": "String",  "nullable": True},
            # Lifestyle / use-case markers synthesised from brand-tier
            # + dietary + category. Text so `_search { tags: $match }`
            # works and `_recommend basedOn: ["tags"]` can use the
            # token-level priors. ~5-8 tags per product. See ADR 0017.
            "tags":      {"type": "Text",    "nullable": False,
                          "analyzer": "whitespace"},
            # From the product's reviews (ADR 0030): null and "unrated"
            # when nobody reviewed it.
            "avg_rating":  {"type": "Decimal", "nullable": True},
            "rating_band": {"type": "String",  "nullable": False},
        },
    },
    # 2. customers — link target for orders.customer_id.
    "customers": {
        "type": "table",
        "columns": {
            "customer_id":   {"type": "String", "nullable": False},
            # Finnish display name so the UI feels like a real shop.
            # Stable per customer_id.
            "name":          {"type": "String", "nullable": False},
            "region":        {"type": "String", "nullable": False},
            "tenure_months": {"type": "Int",    "nullable": False},
            # What the household declared (ADR 0033): its pets ("dog cat"),
            # a dog's size, and the one kind of food it keeps to, if any
            # (grain-free | sensitive | senior | puppy, ADR 0030). The
            # generator's hidden traits (lifestyle, health focus, treat
            # affinity, brand loyalty) are never a column: Aito learns them
            # from what the customer does.
            "pets":          {"type": "Text",   "nullable": False, "analyzer": "whitespace"},
            "dog_size":      {"type": "String", "nullable": True},
            "diet":          {"type": "String", "nullable": True},
            # Order-history aggregates backfilled by the fixture
            # generator. Stored on customers so the Churn view's
            # `_predict churned` can condition on them without a
            # join. See ADR 0013.
            "total_orders":     {"type": "Int",     "nullable": False},
            "total_spent_eur":  {"type": "Decimal", "nullable": False},
            "last_order_month": {"type": "String",  "nullable": True},
            "churned":          {"type": "Boolean", "nullable": False},
            # ADR 0040: the device the customer first came on (the same id as
            # their visits before the first order), the source of the visit
            # with the first order, and what that order held.
            "visitor":                 {"type": "String",  "nullable": False},
            "first_source":            {"type": "String",  "nullable": False},
            "joined_month":            {"type": "String",  "nullable": False},
            "first_basket_categories": {"type": "Text",    "nullable": False, "analyzer": "whitespace"},
            # 3 or more orders in the first 6 months: a label from later data,
            # as `churned_in_3_months` is. Absent for customers who joined
            # less than 6 months before the data ends.
            "became_regular":          {"type": "Boolean", "nullable": True},
        },
    },
    # 2c. contexts — one moment a customer was shown products (ADR 0033):
    # who, when, where, and what the basket, the previous basket and the
    # household's kit held. Impressions link here; queries reach the
    # customer through it (`context.customer`).
    "contexts": {
        "type": "table",
        "columns": {
            "context_id":   {"type": "String", "nullable": False},
            # Absent before the visitor's first order (ADR 0040).
            "customer":     {"type": "String", "nullable": True,
                             "link": "customers.customer_id"},
            "visitor":      {"type": "String", "nullable": False},
            "month":        {"type": "String", "nullable": False},
            "weekday":      {"type": "String", "nullable": False},
            # search | for_you | category | bought_together, or `landing`: the
            # page a visitor who hasn't bought yet landed on.
            "surface":      {"type": "String", "nullable": False},
            # ADR 0040: where the visit came from and the page it landed on;
            # `first_order` marks the visit with the visitor's first order.
            "source":           {"type": "String",  "nullable": False},
            "landing":          {"type": "String",  "nullable": False},
            "landing_category": {"type": "String",  "nullable": True},
            "first_order":      {"type": "Boolean", "nullable": False},
            # ADR 0038, derived from the shopper's purchases in earlier months
            # (none | low | high): the share bought on offer, new, labelled.
            "offer_share":  {"type": "String", "nullable": False},
            "new_share":    {"type": "String", "nullable": False},
            "label_share":  {"type": "String", "nullable": False},
            # Text so `where {"context.search_query": {"$match": "food"}}` token-matches.
            "search_query": {"type": "Text",   "nullable": True, "analyzer": "whitespace"},
            # This month's basket, as SKUs and as words ("dog_dryfood
            # small_animal_cage"; no hyphens or spaces, which the analyzer splits).
            "basket":            {"type": "Text", "nullable": True, "analyzer": "whitespace"},
            "basket_categories": {"type": "Text", "nullable": True, "analyzer": "whitespace"},
            # The last order before this month (recency, S8), and the kit items
            # the household owns from its earlier orders (K1).
            "prev_basket":  {"type": "Text",   "nullable": True, "analyzer": "whitespace"},
            "owned":        {"type": "Text",   "nullable": True, "analyzer": "whitespace"},
        },
    },
    # 2b. product_states — each product as it was in each month on sale
    # (ADR 0032): what a shopper saw. Replaces `price_history` (same id and
    # price columns). Impressions, order lines and monthly sales link here,
    # so `_recommend product_state` can rank this month's products and an
    # offer, the stars or being new can be a reason in `$why`. A link
    # target, so it loads before the tables that link to it.
    "product_states": {
        "type": "table",
        "columns": {
            "product_state_id": {"type": "String",  "nullable": False},
            "product_sku":      {"type": "String",  "nullable": False,
                                 "link": "products.sku"},
            "month":            {"type": "String",  "nullable": False},
            "price_eur":        {"type": "Decimal", "nullable": False},
            "list_price_eur":   {"type": "Decimal", "nullable": False},
            "discount_pct":     {"type": "Decimal", "nullable": False},
            "on_offer":         {"type": "Boolean", "nullable": False},
            # Bands, because a number's bands can't be related on v2.
            "discount_band":    {"type": "String",  "nullable": False},
            "rating_band":      {"type": "String",  "nullable": False},
            "age":              {"type": "String",  "nullable": False},
            "rival_launched":   {"type": "Boolean", "nullable": False},
            "price_change":     {"type": "String",  "nullable": False},
            # ADR 0038: none | recommended | staff_pick | popular; in_stock |
            # low; and the reviews written before the month, as a band.
            "label":             {"type": "String", "nullable": False},
            "stock":             {"type": "String", "nullable": False},
            "review_count_band": {"type": "String", "nullable": False},
        },
    },
    # 3. orders — links to customers.
    "orders": {
        "type": "table",
        "columns": {
            "order_id":    {"type": "String",  "nullable": False},
            "customer_id": {"type": "String",  "nullable": False,
                            "link": "customers.customer_id"},
            # String (not Date) so `_relate` treats months
            # categorically — that's what surfaces seasonality
            # patterns directly in the Pattern Explorer view.
            "month":       {"type": "String",  "nullable": False},
            "total_eur":   {"type": "Decimal", "nullable": False},
            # Denormalised: every line's `<pet>__<category>` token,
            # space-separated. Text type so Aito tokenises on
            # whitespace and treats each underscored pair as a single
            # feature. Drives Bought Together's order-level
            # co-occurrence `_relate` without needing a reverse-link
            # traversal back into `order_lines`. See ADR 0008.
            "line_categories": {"type": "Text", "nullable": False},
            # ADR 0030, interactive shop: this order's SKUs, the previous
            # order's (recency), and the kit durables owned before it.
            "skus":         {"type": "Text", "nullable": False, "analyzer": "whitespace"},
            "prev_skus":    {"type": "Text", "nullable": True,  "analyzer": "whitespace"},
            "owned_before": {"type": "Text", "nullable": True,  "analyzer": "whitespace"},
        },
    },
    # 4. order_lines — links to orders, products and product_states.
    "order_lines": {
        "type": "table",
        "columns": {
            "line_id":     {"type": "String",  "nullable": False},
            "order_id":    {"type": "String",  "nullable": False,
                            "link": "orders.order_id"},
            "product_sku": {"type": "String",  "nullable": False,
                            "link": "products.sku"},
            "qty":         {"type": "Int",     "nullable": False},
            "returned":    {"type": "Boolean", "nullable": False},
            # ADR 0032: the product as it was that month (price, offer, stars, new).
            "product_state":           {"type": "String", "nullable": False,
                                        "link": "product_states.product_state_id"},
            # ADR 0039: the order's delivery was late or damaged.
            "incident":    {"type": "Boolean", "nullable": False},
        },
    },
    # 4b. impressions — one product shown in a context, with the funnel
    # outcome (clicked / added_to_cart / purchased): the conversion KPI the
    # recommendation surfaces rank on (`_recommend product_sku goal:
    # {purchased: true}`, ADR 0021). Who, when and where are on the
    # context (ADR 0033). Largest table — generated, not committed.
    "impressions": {
        "type": "table",
        "columns": {
            "impression_id": {"type": "String", "nullable": False},
            "context":       {"type": "String", "nullable": False,
                              "link": "contexts.context_id"},
            "product_sku":   {"type": "String", "nullable": False,
                              "link": "products.sku"},
            # ADR 0032: the product as it was that month (price, offer, stars, new).
            "product_state": {"type": "String", "nullable": False,
                              "link": "product_states.product_state_id"},
            # Descriptive only — never fed to recommend `basedOn`, so
            # Aito ranks on content, not "position predicts click".
            "position":      {"type": "Int",     "nullable": False},
            # The product was in the customer's last order (recency, S8).
            "just_bought":   {"type": "Boolean", "nullable": False},
            # Funnel outcome labels (monotone: purchased ⇒ cart ⇒ click).
            "clicked":       {"type": "Boolean", "nullable": False},
            "added_to_cart": {"type": "Boolean", "nullable": False},
            "purchased":     {"type": "Boolean", "nullable": False},
        },
    },
    # 5. reviews — links to customers AND products. Powers the
    # Feedback view's multi-field `_predict` over review text.
    # Loaded after customers + products so the link writes succeed.
    "reviews": {
        "type": "table",
        "columns": {
            "review_id":   {"type": "String",  "nullable": False},
            "customer_id": {"type": "String",  "nullable": False,
                            "link": "customers.customer_id"},
            "product_sku": {"type": "String",  "nullable": False,
                            "link": "products.sku"},
            "rating":      {"type": "Int",     "nullable": False},
            # Text so `_predict` over `{text: ...}` tokenises on
            # whitespace — drives the Feedback view's category /
            # sentiment / assigned_to / churn_within_90d predictions
            # from a single free-form text input. See ADR 0012.
            "text":        {"type": "Text",    "nullable": False,
                            "analyzer": "whitespace"},
            "category":    {"type": "String",  "nullable": False},
            "sentiment":   {"type": "String",  "nullable": False},
            "assigned_to": {"type": "String",  "nullable": False},
            "created_at":  {"type": "String",  "nullable": False},
            # Forward-looking label: True iff the reviewer churned and
            # never ordered after this review's month. Drives the
            # Feedback view's "churn risk from text" 4th predict —
            # see ADR 0013 §"Forward labels".
            "churn_within_90d": {"type": "Boolean", "nullable": False},
            # ADR 0039: the shop replied (to negative reviews, at random),
            # and the order line the review is about.
            "replied":     {"type": "Boolean", "nullable": False},
            "order_line":  {"type": "String",  "nullable": False,
                            "link": "order_lines.line_id"},
        },
    },
    # 5b. nps_responses — a survey answer after an order (ADR 0039): its
    # score and group. Links to the customer and the order surveyed.
    "nps_responses": {
        "type": "table",
        "columns": {
            "nps_response_id": {"type": "String", "nullable": False},
            "customer":        {"type": "String", "nullable": False,
                                "link": "customers.customer_id"},
            # Not `order`: kept clear of any reserved word in a query.
            "surveyed_order":  {"type": "String", "nullable": False,
                                "link": "orders.order_id"},
            "month":           {"type": "String", "nullable": False},
            "score":           {"type": "Int",    "nullable": False},
            # promoter (9–10) | passive (7–8) | detractor (0–6)
            "nps_group":       {"type": "String", "nullable": False},
        },
    },
    # 7. monthly_sales — SKU × month sales aggregate. Drives the
    # Demand Forecast view's `_predict units_sold` and the Inventory
    # view's daily-demand arithmetic. Denormalised pet_type / category
    # / brand / season so Aito conditions in one hop.
    "monthly_sales": {
        "type": "table",
        "columns": {
            "monthly_sale_id":  {"type": "String",  "nullable": False},
            "product_sku":      {"type": "String",  "nullable": False,
                                 "link": "products.sku"},
            "month":            {"type": "String",  "nullable": False},
            "units_sold":       {"type": "Int",     "nullable": False},
            "revenue_eur":      {"type": "Decimal", "nullable": False},
            "unique_customers": {"type": "Int",     "nullable": False},
            "pet_type":         {"type": "String",  "nullable": False},
            "category":         {"type": "String",  "nullable": False},
            "brand":            {"type": "String",  "nullable": False},
            "season":           {"type": "String",  "nullable": False},
            # Realised price (revenue / units) — drives the Price
            # view's demand curve via `_estimate units_sold` with
            # `price_eur` in the where clause.
            "price_eur":        {"type": "Decimal", "nullable": False},
            # Last month's units and both months as sales ranges
            # ("0", "1", "2-3" … "32+"). The Demand forecast conditions
            # on last month; its accuracy is scored on ranges against
            # the naive "same range as last month". See ADR 0014.
            "units_last_month":        {"type": "Int",    "nullable": False},
            "units_bucket":            {"type": "String", "nullable": False},
            "units_last_month_bucket": {"type": "String", "nullable": False},
            # ADR 0032: the product as it was that month (price, offer, stars, new).
            "product_state":           {"type": "String", "nullable": False,
                                        "link": "product_states.product_state_id"},
        },
    },
    # 8. inventory — per-SKU stock snapshot. Drives the Inventory
    # Intelligence view's reorder workflow + cash-impact figures.
    "inventory": {
        "type": "table",
        "columns": {
            "sku":                 {"type": "String",  "nullable": False,
                                    "link": "products.sku"},
            "current_stock":       {"type": "Int",     "nullable": False},
            "unit_cost_eur":       {"type": "Decimal", "nullable": False},
            "lead_time_days":      {"type": "Int",     "nullable": False},
            "reorder_point":       {"type": "Int",     "nullable": False},
            "safety_stock":        {"type": "Int",     "nullable": False},
            "supplier":            {"type": "String",  "nullable": False},
            "last_received_month": {"type": "String",  "nullable": False},
        },
    },
    # 6b. winback_campaigns — historical re-engagement emails sent to
    # then-inactive customers. Drives Retention's win-back offer: `_predict
    # responded` per at-risk customer and product (src/winback_offer.py). See ADR 0020.
    "winback_campaigns": {
        "type": "table",
        "columns": {
            "campaign_id":   {"type": "String",  "nullable": False},
            "customer_id":   {"type": "String",  "nullable": False,
                              "link": "customers.customer_id"},
            "product_sku":   {"type": "String",  "nullable": False,
                              "link": "products.sku"},
            "sent_month":    {"type": "String",  "nullable": False},
            # Days since the customer's last order at send time,
            # bucketed for K-NN. Strong predictor of response.
            "recency_bucket": {"type": "String", "nullable": False},
            # The customer's staple "pet/category" ("none" if none): a send
            # in it responds 2.5x as often (ADR 0027).
            "customer_staple_category": {"type": "String", "nullable": False},
            "product_pet_type":     {"type": "String", "nullable": False},
            "product_category":     {"type": "String", "nullable": False},
            "product_brand":        {"type": "String", "nullable": False},
            # Outcome label Aito learns from.
            "responded":      {"type": "Boolean", "nullable": False},
            "order_value_eur":{"type": "Decimal", "nullable": False},
        },
    },
    # 7. customer_months — panel data, one row per customer per month.
    # Drives Retention's churn score (`src/churn_risk.py`). Loaded last
    # because it links to customers.
    "customer_months": {
        "type": "table",
        "columns": {
            "customer_month_id": {"type": "String", "nullable": False},
            "customer_id":       {"type": "String", "nullable": False,
                                  "link": "customers.customer_id"},
            "customer_name":     {"type": "String", "nullable": False},
            "month":             {"type": "String", "nullable": False},
            "visits":            {"type": "Int",    "nullable": False},
            "purchases":         {"type": "Int",    "nullable": False},
            "spent_eur":         {"type": "Decimal", "nullable": False},
            # Declared by the household (ADR 0033), copied so `_predict` over
            # this table sees them directly.
            "pets":              {"type": "Text",   "nullable": False, "analyzer": "whitespace"},
            "dog_size":          {"type": "String", "nullable": True},
            "region":            {"type": "String", "nullable": False},
            "tenure_months_at_month": {"type": "Int", "nullable": False},
            # Latest-review snapshot in this month (if the customer
            # wrote one). Connects feedback to churn prediction —
            # negative ratings near the end of life predict drop-off.
            "latest_rating":     {"type": "Int",    "nullable": True},
            "latest_sentiment":  {"type": "String", "nullable": True},
            "latest_category":   {"type": "String", "nullable": True},
            # The forward-looking target. See ADR 0013 §"Forward
            # labels" for the customer.churned ∧ month ≥ last_order
            # rule.
            "churned_in_3_months": {"type": "Boolean", "nullable": False},
            # ADR 0039: the latest NPS group so far, and a negative review
            # in this month or the 2 before (and whether the shop replied).
            "nps_latest_group":    {"type": "String",  "nullable": True},
            "had_negative_review": {"type": "Boolean", "nullable": False},
            "review_replied":      {"type": "Boolean", "nullable": False},
        },
    },
}
