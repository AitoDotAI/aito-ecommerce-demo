"""A shopper's orders as of a month: everything the Shop's panels know
about their history (ADR 0031).

The grid, the drawer and the suggestions all read history through here,
so they agree on what "now" is: the month the user picked. An order in
that month or later hasn't happened yet.
"""

from __future__ import annotations

from src.aito_client import AitoClient, AitoError
from src.aito_compat import related_value
from src.shop_context import DURABLE_TYPES, item_type

MAX_ORDERS = 200
# How many commonly owned items a household is told it lacks (ADR 0033, R5).
COMMON_OWNED = 8
RELATE_LIMIT = 50
PETS = ("small_animal", "dog", "cat", "bird", "aquarium")
# The data's months. Outside them a Shop would answer from no data at all.
FIRST_MONTH, LATEST_MONTH = "2024-05", "2026-04"


def orders_before(client: AitoClient, customer_id: str, month: str) -> list[dict]:
    """The customer's orders before `month`, oldest first."""
    if not FIRST_MONTH <= month <= LATEST_MONTH:
        raise ValueError(f"The shop's data runs from {FIRST_MONTH} to {LATEST_MONTH}; {month} is outside it")
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


def missing_items(client: AitoClient, owned: list[str]) -> list[str]:
    """The items most often owned by households that own what this one owns,
    and that this one lacks, at most COMMON_OWNED: learned from the data, so
    the app needs no kit knowledge (ADR 0033, R5).

    `_recommend` reads `$match` as "contains" and infers nothing from what a
    context lacks, so the Shop states these as `$not $match` (Aito core
    td-20261020203235895741 is to widen absence evidence)."""
    if not owned:
        return []
    where = {"owned": {"$and": [{"$match": t} for t in owned]}}
    hits = client.relate("contexts", where, "owned", limit=RELATE_LIMIT)["hits"]
    if len(hits) == RELATE_LIMIT:
        raise AitoError(f"_relate over contexts.owned returned a full page of {RELATE_LIMIT}: items may be cut off")
    by_count = sorted(((related_value(h, "owned"), int(h["fs"]["fOnCondition"])) for h in hits),
                      key=lambda row: -row[1])
    return [token for token, _ in by_count if token not in owned][:COMMON_OWNED]
