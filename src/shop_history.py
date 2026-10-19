"""A shopper's orders as of a month: everything the Shop's panels know
about their history (ADR 0031).

The grid, the drawer and the suggestions all read history through here,
so they agree on what "now" is: the month the user picked. An order in
that month or later hasn't happened yet.
"""

from __future__ import annotations

from src.aito_client import AitoClient, AitoError
from src.shop_context import DURABLE_TYPES, item_type

MAX_ORDERS = 200
PETS = ("small_animal", "dog", "cat", "bird", "aquarium")


def orders_before(client: AitoClient, customer_id: str, month: str) -> list[dict]:
    """The customer's orders before `month`, oldest first."""
    res = client.search("orders", where={"customer_id": customer_id}, limit=MAX_ORDERS)
    if res["total"] > len(res["hits"]):
        raise AitoError(f"{customer_id} has {res['total']} orders, more than the {MAX_ORDERS} read")
    return sorted((o for o in res["hits"] if o["month"] < month), key=lambda o: o["month"])


def owned_kit(client: AitoClient, orders: list[dict]) -> dict[str, set[str]]:
    """Kit items the household owns after `orders`, per pet: those owned before
    the last order (`orders.owned_before`), plus the last order's own. Words
    as the data writes them: {"small_animal": {"cage", "water_bottle"}}."""
    if not orders:
        return {}
    last = orders[-1]
    owned: dict[str, set[str]] = {}
    for token in (last.get("owned_before") or "").split():
        pet = next(p for p in PETS if token.startswith(f"{p}_"))
        owned.setdefault(pet, set()).add(token[len(pet) + 1:])
    skus = last["skus"].split()
    for p in client.search("products", where={"sku": {"$or": skus}}, limit=len(skus))["hits"]:
        if item_type(p["name"], p["brand"]) in DURABLE_TYPES:
            owned.setdefault(p["pet_type"], set()).add(kind_word(p["name"], p["brand"]))
    return owned


def kit_tokens(owned: dict[str, set[str]]) -> list[str]:
    """{"small_animal": {"cage"}} → ["small_animal_cage"], as `contexts.owned` holds them."""
    return sorted(f"{pet}_{kind}" for pet, kinds in owned.items() for kind in kinds)


def kind_word(name: str, brand: str) -> str:
    """"Trixie Water Bottle 500ml" → "water_bottle", the word the tokens use."""
    return item_type(name, brand).lower().replace(" ", "_")
