"""A shopper's profile for the Shop's "Who is this?" popover: what the shop knows about them.

Everything here is read, not predicted: the customer row (what they declared or the shop recorded), and
their orders before the month the user picked, with the product names. It is the evidence behind the
suggestions, so an owner can see why a cold shopper is cold and a long history is long.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.aito_client import AitoClient
from src.shop_ranking import shop_scope

HISTORY_ORDERS = 8      # the most recent orders shown; the rest are counted
FACTS = ("region", "tenure_months", "loyalty_member", "interests")


@dataclass(frozen=True)
class ProfileOrder:
    month: str
    total_eur: float | None
    items: list[str]        # product names, one per line of the order


@dataclass(frozen=True)
class ShopperProfile:
    key: str
    name: str
    story: str
    pets: str
    pets_declared: bool     # False: read from their orders (ADR 0045)
    diet: str | None
    facts: dict[str, object]    # only those of `FACTS` the customer row holds
    orders_total: int
    spent_eur: float
    last_basket: ProfileOrder | None
    history: list[ProfileOrder]     # newest first, at most HISTORY_ORDERS

    def to_dict(self) -> dict:
        return asdict(self)


def get_shopper_profile(client: AitoClient, shopper_key: str, month: str) -> ShopperProfile:
    scope = shop_scope(client, shopper_key, month, [])
    customer = client.search("customers", where={"customer_id": scope.shopper.customer_id}, limit=1)["hits"][0]
    recent = scope.orders[-HISTORY_ORDERS:][::-1]
    skus = sorted({sku for order in recent for sku in order["skus"].split()})
    found = client.search("products", where={"sku": {"$or": skus}}, limit=len(skus))["hits"] if skus else []
    names = {p["sku"]: p["name"] for p in found}
    missing = [s for s in skus if s not in names]
    if missing:
        raise LookupError(f"Orders of {scope.shopper.customer_id} hold products not in the catalogue: {missing}")

    def shown(order: dict) -> ProfileOrder:
        return ProfileOrder(month=order["month"], total_eur=order.get("total_eur"),
                            items=[names[s] for s in order["skus"].split()])

    return ShopperProfile(
        key=scope.shopper.key, name=scope.shopper.name, story=scope.shopper.story, pets=scope.pets,
        pets_declared=scope.pets_declared, diet=scope.rule,
        facts={k: customer[k] for k in FACTS if customer.get(k) not in (None, "")},
        orders_total=len(scope.orders), spent_eur=round(sum(o.get("total_eur") or 0 for o in scope.orders), 2),
        last_basket=shown(recent[0]) if recent else None, history=[shown(o) for o in recent])
