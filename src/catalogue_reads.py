"""The catalogue tables Supply reads whole: stock, products, monthly sales
and realised prices.

Each is one paged `_search`. The tables are small (658 SKUs, ~15k
monthly rows), so reading them once and doing the arithmetic in Python
is cheaper than one Aito call per SKU: 658 parallel `_aggregate`s trip
the rate limit.
"""

from __future__ import annotations

from src.aito_client import AitoClient


def read_all(client: AitoClient, table: str, *, where: dict | None = None, page: int = 5000) -> list[dict]:
    """Every row of `table` (that matches `where`), a page at a time."""
    rows: list[dict] = []
    offset = 0
    while True:
        hits = client.search(table, where=where, limit=page, offset=offset).get("hits", [])
        rows.extend(hits)
        if len(hits) < page:
            return rows
        offset += page


def products_by_sku(client: AitoClient) -> dict[str, dict]:
    return {p["sku"]: p for p in read_all(client, "products")}


def rows_by_sku(rows: list[dict], key: str = "product_sku") -> dict[str, list[dict]]:
    """Group rows (monthly sales, product states) by their SKU column."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row[key], []).append(row)
    return grouped
