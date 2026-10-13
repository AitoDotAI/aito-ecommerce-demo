"""The Shop's two proactive suggestions (ADR 0031).

- **Fill my usual basket**: `_predict` with `predict: "skus.$feature"` from
  a nested `from` holding only this shopper's orders. `$feature` makes it
  one probability per SKU rather than one per whole basket (the plain
  `predict: "skus"` returns past baskets at p 0.1 each).
- **What's next for your pet**: `_predict product_sku` on `order_lines`
  whose order already owned what this shopper owns (`order_id.owned_before`
  matching each kit item), for their pet's accessories and toys. ADR 0030
  check A2: after cage, bottle and hideout, the exercise wheel comes top.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.aito_client import AitoClient
from src.shop_context import DURABLE_TYPES, item_type
from src.shop_history import orders_before
from src.shop_personas import shopper

USUAL_ITEMS = 8
NEXT_ITEMS = 4
# Below this, "next" is noise: the shopper has the whole kit.
MIN_NEXT_P = 0.05


@dataclass(frozen=True)
class Suggestion:
    sku: str
    name: str
    p: float


@dataclass(frozen=True)
class Suggestions:
    usual: list[Suggestion]       # empty, with no_history set, for a shopper without orders
    next_for_pet: list[Suggestion]
    owned: dict[str, list[str]]   # kit items owned per pet: {"small_animal": ["cage", …]}
    no_history: bool
    queries: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def get_suggestions(client: AitoClient, shopper_key: str, month: str) -> Suggestions:
    """As of `month`: only the shopper's orders before it count."""
    customer_id = shopper(shopper_key).customer_id
    orders = orders_before(client, customer_id, month)
    if not orders:
        return Suggestions([], [], {}, True, [])

    # Their orders before the month, as the population (a nested `from`).
    population = {"from": "orders", "where": {"order_id": {"$or": [o["order_id"] for o in orders]}}}
    usual_hits = client.predict_rows(population, "skus.$feature", limit=USUAL_ITEMS + 6)["hits"]
    usual_body = {"from": population, "predict": "skus.$feature", "limit": USUAL_ITEMS + 6}

    owned = _owned(client, orders[-1])        # {"small_animal": {"cage", "water_bottle"}}
    next_hits, next_bodies = [], []
    for pet, kinds in sorted(owned.items()):
        where = {"order_id.owned_before": {"$and": [{"$match": f"{pet}_{k}"} for k in sorted(kinds)]},
                 "product_sku.pet_type": pet,
                 "product_sku.category": {"$or": ["accessories", "toys"]}}
        next_bodies.append({"from": "order_lines", "where": where, "predict": "product_sku", "limit": 12})
        next_hits += [(pet, h) for h in client.predict_rows("order_lines", "product_sku", where=where, limit=12)["hits"]]
    # What they already own isn't next.
    fresh = [h for pet, h in next_hits
             if _kind(h["name"], h["brand"]) not in owned[pet] and h["$p"] >= MIN_NEXT_P]
    fresh.sort(key=lambda h: -h["$p"])

    products = _products(client, [h["feature"] for h in usual_hits])
    # Kit items are bought once: a cage is in their history, not their routine.
    routine = [h for h in usual_hits
               if item_type(products[h["feature"]]["name"], products[h["feature"]]["brand"]) not in DURABLE_TYPES]
    return Suggestions(
        usual=[Suggestion(h["feature"], products[h["feature"]]["name"], round(float(h["$p"]), 3))
               for h in routine[:USUAL_ITEMS]],
        next_for_pet=[Suggestion(h["sku"], h["name"], round(float(h["$p"]), 3)) for h in fresh[:NEXT_ITEMS]],
        owned={pet: sorted(kinds) for pet, kinds in owned.items()},
        no_history=False,
        queries=[{"endpoint": "_predict", "body": usual_body}]
                + [{"endpoint": "_predict", "body": b} for b in next_bodies],
    )


PETS = ("small_animal", "dog", "cat", "bird", "aquarium")


def _owned(client: AitoClient, last_order: dict) -> dict[str, set[str]]:
    """Kit items owned now, per pet: those owned before the last order, plus
    the last order's own. Tokens are `pet_kind`, as the generator writes them."""
    owned: dict[str, set[str]] = {}
    for token in (last_order.get("owned_before") or "").split():
        pet = next(p for p in PETS if token.startswith(f"{p}_"))
        owned.setdefault(pet, set()).add(token[len(pet) + 1:])
    for p in client.search("products", where={"sku": {"$or": last_order["skus"].split()}}, limit=50)["hits"]:
        if item_type(p["name"], p["brand"]) in DURABLE_TYPES:
            owned.setdefault(p["pet_type"], set()).add(_kind(p["name"], p["brand"]))
    return owned


def _kind(name: str, brand: str) -> str:
    """"Trixie Water Bottle 500ml" → "water_bottle", the word the tokens use."""
    return item_type(name, brand).lower().replace(" ", "_")


def _products(client: AitoClient, skus: list[str]) -> dict[str, dict]:
    if not skus:
        return {}
    rows = client.search("products", where={"sku": {"$or": skus}}, limit=len(skus))["hits"]
    return {p["sku"]: p for p in rows}
