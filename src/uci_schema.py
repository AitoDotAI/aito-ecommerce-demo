"""The Aito schema of env `uci`: UCI Online Retail II, as the benchmark loaded it.

`customers`, `invoices` and `lines` are Aito core's benchmark schema
(retail2_aito.SCHEMA) unchanged; the draft order's `_predict` runs on
them. `products` and `baskets` are the demo's additions, deliberately
linked from nothing, so they can't add evidence to that `_predict`.

Listed in link-target order: a table is created after the tables its
links point to, and deleted before them.
"""

UCI_SCHEMA: dict[str, dict] = {
    # Only the id. Customer attributes would be evidence the benchmark
    # didn't give Aito.
    "customers": {"type": "table", "columns": {
        "customer_id": {"type": "String", "nullable": False}}},
    "invoices": {"type": "table", "columns": {
        "invoice": {"type": "String", "nullable": False},
        "customer_id": {"type": "String", "nullable": False, "link": "customers.customer_id"},
        # "YYYY-MM", a String: the benchmark's Aito saw the month as a
        # category. Its form changes the measured hit rate.
        "month": {"type": "String", "nullable": False}}},
    "lines": {"type": "table", "columns": {
        "line_id": {"type": "String", "nullable": False},
        "invoice": {"type": "String", "nullable": False, "link": "invoices.invoice"},
        # A plain String, never `link: "products.code"`: a link would make
        # the product's description and price evidence for the prediction,
        # and the measured number would no longer be the benchmark's.
        "code": {"type": "String", "nullable": False}}},
    "products": {"type": "table", "columns": {
        "code": {"type": "String", "nullable": False},
        "description": {"type": "Text", "nullable": False},
        "last_price_gbp": {"type": "Decimal", "nullable": False}}},
    "baskets": {"type": "table", "columns": {
        "invoice": {"type": "String", "nullable": False},
        # A plain String, not a link: baskets stay outside the benchmark's tables.
        "customer_id": {"type": "String", "nullable": False},
        "month": {"type": "String", "nullable": False},
        # The invoice's codes, space-separated. The whitespace analyzer
        # keeps a code like "85123A" one token (as `orders.skus` does in
        # the pet shop), so `_relate` can relate code to code.
        "codes": {"type": "Text", "nullable": False, "analyzer": "whitespace"}}},
}
