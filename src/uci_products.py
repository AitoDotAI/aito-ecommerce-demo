"""Labels and prices for UCI StockCodes: a `_search` on env `uci`'s `products`.

`products` is linked from nothing (see `src/uci_schema.py`), so the
draft's `_predict` returns bare codes and the descriptions and £ prices
are looked up here, in one query for the whole draft.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError


@dataclass(frozen=True)
class Product:
    code: str
    description: str
    last_price_gbp: float     # unit price on the code's latest line before the cutoff


class UnknownStockCodeError(LookupError):
    """The requested StockCode was not sold before the cutoff, so it is not in `products`."""


def lookup_products(client: AitoClient, codes: list[str]) -> dict[str, Product]:
    """Every code's product. A code missing from `products` raises: each
    code Aito can predict came from a training line, and so has a row."""
    hits = client.search("products", where={"code": {"$or": codes}}, limit=len(codes))["hits"]
    products = {h["code"]: Product(h["code"], h["description"], float(h["last_price_gbp"])) for h in hits}
    missing = [c for c in codes if c not in products]
    if missing:
        raise AitoError(f"products has no row for {missing} (asked for {len(codes)} codes)")
    return products


def find_product(client: AitoClient, code: str) -> Product:
    """One product, or UnknownStockCodeError (a 404) for a code not in the data."""
    hits = client.search("products", where={"code": code}, limit=1)["hits"]
    if not hits:
        raise UnknownStockCodeError(f"No StockCode {code!r} was sold before 2011-09-01")
    hit = hits[0]
    return Product(hit["code"], hit["description"], float(hit["last_price_gbp"]))
