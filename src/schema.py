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
            "segment":       {"type": "String", "nullable": False},
            # `pet_size` is set only for dog_owner / multi_pet rows;
            # nullable so the segments that don't have one don't
            # have to invent a placeholder.
            "pet_size":      {"type": "String", "nullable": True},
            "region":        {"type": "String", "nullable": False},
            "tenure_months": {"type": "Int",    "nullable": False},
            # Latent profile traits sampled at customer creation,
            # stable across purchase history. Drive within-segment
            # product preference (lifestyle ↔ brand tier, health
            # focus ↔ dietary, treat affinity ↔ category, brand
            # loyalty ↔ favorite brands). Give Aito's `_recommend
            # basedOn` real signal on thin-history customers. See
            # ADR 0017.
            "lifestyle":      {"type": "String", "nullable": False},
            "health_focus":   {"type": "String", "nullable": False},
            "treat_affinity": {"type": "String", "nullable": False},
            "brand_loyalty":  {"type": "String", "nullable": False},
            # Order-history aggregates backfilled by the fixture
            # generator. Stored on customers so the Churn view's
            # `_predict churned` can condition on them without a
            # join. See ADR 0013.
            "total_orders":     {"type": "Int",     "nullable": False},
            "total_spent_eur":  {"type": "Decimal", "nullable": False},
            "last_order_month": {"type": "String",  "nullable": True},
            "churned":          {"type": "Boolean", "nullable": False},
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
        },
    },
    # 4. order_lines — links to orders AND products. Load last.
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
            # Denormalised mirror of `customers.{segment, pet_size}`.
            # Aito's queries from `order_lines` only do single-hop
            # link traversal — to bias by customer attributes without
            # a two-hop chain (`order_id → orders → customer_id →
            # customers`) we pull the demo-load-bearing customer
            # fields down to the line level. Drives Smart Search's
            # customer-context biasing. See ADR 0006.
            "customer_segment":  {"type": "String", "nullable": False},
            "customer_pet_size": {"type": "String", "nullable": True},
            # Latent profile traits denormalised onto the line (same
            # single-hop rationale as `customer_segment` /
            # `customer_pet_size`). Drive within-segment patterns
            # surfaced by Pattern Explorer / Bought Together /
            # Purchase Analytics. See ADR 0017.
            "customer_lifestyle":      {"type": "String", "nullable": False},
            "customer_health_focus":   {"type": "String", "nullable": False},
            "customer_treat_affinity": {"type": "String", "nullable": False},
            "customer_brand_loyalty":  {"type": "String", "nullable": False},
        },
    },
    # 4b. impressions — one product shown to a customer in a browsing
    # context, with the funnel outcome (clicked / added_to_cart /
    # purchased). This is the table that gives the recommendation
    # surfaces a real conversion KPI: `_recommend product_sku
    # goal: {purchased: true}`. Links to customers + products, so it
    # loads after both. Largest table — generated, not committed
    # (gitignored). See ADR 0021.
    "impressions": {
        "type": "table",
        "columns": {
            "impression_id": {"type": "String", "nullable": False},
            "session_id":    {"type": "String", "nullable": False},
            "customer_id":   {"type": "String", "nullable": False,
                              "link": "customers.customer_id"},
            "product_sku":   {"type": "String", "nullable": False,
                              "link": "products.sku"},
            "surface":       {"type": "String", "nullable": False},
            "month":         {"type": "String", "nullable": False},
            # Descriptive only — never fed to recommend `basedOn`, so
            # Aito ranks on content, not "position predicts click".
            "position":      {"type": "Int",    "nullable": False},
            # The query string for surface == "search". Text so
            # `where {search_query: {$match: "food"}}` token-matches.
            "search_query":  {"type": "Text",   "nullable": True,
                              "analyzer": "whitespace"},
            # Denormalised customer profile — single-hop conditioning.
            "customer_segment":      {"type": "String", "nullable": False},
            "customer_pet_size":     {"type": "String", "nullable": True},
            "customer_lifestyle":    {"type": "String", "nullable": False},
            "customer_health_focus": {"type": "String", "nullable": False},
            "customer_treat_affinity":{"type": "String", "nullable": False},
            "customer_brand_loyalty":{"type": "String", "nullable": False},
            # Denormalised product attributes for `basedOn` priors.
            "product_pet_type": {"type": "String", "nullable": False},
            "product_category": {"type": "String", "nullable": False},
            "product_brand":    {"type": "String", "nullable": False},
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
            # Forward-looking label: True iff the reviewer has no
            # orders in the 3 months after this review. Drives the
            # Feedback view's "churn risk from text" 4th predict —
            # see ADR 0013 §"Forward labels".
            "churn_within_90d": {"type": "Boolean", "nullable": False},
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
    # 9. price_history — per-SKU per-month price snapshots. Drives
    # the Price Intelligence view's fair-band display + `_relate`
    # for price-band ↔ units_sold sweet spots.
    "price_history": {
        "type": "table",
        "columns": {
            "price_observation_id": {"type": "String",  "nullable": False},
            "product_sku":          {"type": "String",  "nullable": False,
                                     "link": "products.sku"},
            "month":                {"type": "String",  "nullable": False},
            "price_eur":            {"type": "Decimal", "nullable": False},
            "list_price_eur":       {"type": "Decimal", "nullable": False},
            "discount_pct":         {"type": "Decimal", "nullable": False},
        },
    },
    # 6b. winback_campaigns — historical re-engagement emails sent to
    # then-inactive customers. Drives the Win-back view's `_predict
    # responded` per currently-churned customer. See ADR 0020.
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
            # Denormalised so Aito conditions in one hop.
            "customer_segment":     {"type": "String", "nullable": False},
            "customer_pet_size":    {"type": "String", "nullable": True},
            "customer_lifestyle":   {"type": "String", "nullable": False},
            "customer_health_focus":{"type": "String", "nullable": False},
            "product_pet_type":     {"type": "String", "nullable": False},
            "product_category":     {"type": "String", "nullable": False},
            "product_brand":        {"type": "String", "nullable": False},
            # Outcome label Aito learns from.
            "responded":      {"type": "Boolean", "nullable": False},
            "order_value_eur":{"type": "Decimal", "nullable": False},
        },
    },
    # 7. customer_months — panel data, one row per customer per month.
    # Drives the Churn view's time-series prediction. Loaded last
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
            # Profile features denormalised onto each row so `_predict`
            # over customer_months sees them directly (Aito's
            # single-hop link-traversal limit).
            "segment":           {"type": "String", "nullable": False},
            "pet_size":          {"type": "String", "nullable": True},
            "region":            {"type": "String", "nullable": False},
            # Latent profile traits denormalised so Churn's `_predict
            # churned_in_3_months` can condition on them. Engineered
            # correlation: budget+flexible customers churn ~12 pp
            # higher than premium+loyal. See ADR 0017.
            "lifestyle":         {"type": "String", "nullable": False},
            "health_focus":      {"type": "String", "nullable": False},
            "treat_affinity":    {"type": "String", "nullable": False},
            "brand_loyalty":     {"type": "String", "nullable": False},
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
        },
    },
}
