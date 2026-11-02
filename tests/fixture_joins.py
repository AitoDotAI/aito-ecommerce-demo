"""Joined views of the fixtures, for the data checks (ADR 0033).

Aito sees only what a shop observes: thin impressions, their contexts, and
customers with declared fields. The data checks also need the generator's
hidden model (a customer's lifestyle, segment, ...) to verify that it
plants what it says. These helpers join the public tables with the
generator's answer key (`data/answer_key/customer_traits.json`, never
loaded into Aito) under the column names the checks have always used.
"""

import json
from functools import cache
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HIDDEN = ("segment", "lifestyle", "health_focus", "treat_affinity", "brand_loyalty", "pet_size", "diet_rule")


def _present(row: dict) -> dict:
    """Without null fields, as the generator writes rows."""
    return {k: v for k, v in row.items() if v is not None}


def load(name: str) -> list[dict]:
    path = DATA_DIR / name
    if not path.exists():
        pytest.skip(f"{name} missing — run `./do generate-fixtures`.")
    return json.loads(path.read_text(encoding="utf-8"))


@cache
def _traits() -> dict[str, dict]:
    return {row["customer_id"]: row for row in load("answer_key/customer_traits.json")}


def customers_with_traits() -> list[dict]:
    """customers rows plus the hidden model's fields."""
    traits = _traits()
    return [_present({**{k: traits[c["customer_id"]].get(k) for k in HIDDEN}, **c}) for c in load("customers.json")]


def _as_customer_columns(customer_id: str) -> dict:
    t = _traits()[customer_id]
    return {f"customer_{k}": t.get(k) for k in HIDDEN}


def order_lines_with_customer() -> list[dict]:
    """order_lines with the buyer's hidden model as `customer_*`."""
    customer_of = {o["order_id"]: o["customer_id"] for o in load("orders.json")}
    return [_present({**ln, **_as_customer_columns(customer_of[ln["order_id"]])}) for ln in load("order_lines.json")]


def impressions_in_context(include_visitors: bool = False) -> list[dict]:
    """impressions with their context's fields under the names they had
    before ADR 0033, the customer's hidden model as `customer_*`, and the
    product's pet type and category.

    Customers' impressions only, unless `include_visitors`: a visitor who
    hasn't bought yet (ADR 0040) has no hidden model and never buys."""
    contexts = {c["context_id"]: c for c in load("contexts.json")}
    products = {p["sku"]: p for p in load("products.json")}
    out = []
    for imp in load("impressions.json"):
        ctx = contexts[imp["context"]]
        product = products[imp["product_sku"]]
        if "customer" not in ctx:
            if include_visitors:
                out.append({**imp, "month": ctx["month"], "surface": ctx["surface"]})
            continue
        out.append(_present({
            **imp,
            "customer_id": ctx["customer"], "month": ctx["month"], "surface": ctx["surface"],
            "search_query": ctx.get("search_query"), "basket_categories": ctx.get("basket_categories"),
            "basket_skus": ctx.get("basket"), "last_order_skus": ctx.get("prev_basket"),
            "owned": ctx.get("owned"),
            "product_pet_type": product["pet_type"], "product_category": product["category"],
            **_as_customer_columns(ctx["customer"]),
        }))
    return out
