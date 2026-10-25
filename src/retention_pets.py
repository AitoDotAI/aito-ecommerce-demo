"""The pets of the households Retention lists.

Most households declare no pet profile (ADR 0045), so a customer's `pets` is often empty. The
win-back offer is picked for the household's pets, so for the customers the view lists they
are read from what the household bought: the pet types of the products in its orders, the
way the Shop reads them (`shop_ranking._pets_of_orders`).
"""

from __future__ import annotations

from src.aito_client import AitoClient, AitoError
from src.catalogue_reads import read_all
from src.churn_risk import ScoredCustomer


def household_pets(client: AitoClient, customers: list[ScoredCustomer]) -> dict[str, str]:
    """Each customer's pets, "dog cat": the declared ones, else the pet types they bought for."""
    undeclared = [c.customer_id for c in customers if c.pets is None]
    from_orders = _pets_from_orders(client, undeclared) if undeclared else {}
    return {c.customer_id: c.pets if c.pets is not None else from_orders[c.customer_id] for c in customers}


def _pets_from_orders(client: AitoClient, customer_ids: list[str]) -> dict[str, str]:
    orders = read_all(client, "orders", where={"customer_id": {"$or": customer_ids}})
    skus_of: dict[str, set[str]] = {cid: set() for cid in customer_ids}
    for order in orders:
        skus_of[order["customer_id"]].update(order["skus"].split())
    all_skus = sorted(set().union(*skus_of.values()))
    found = client.search("products", where={"sku": {"$or": all_skus}}, limit=len(all_skus))["hits"] if all_skus else []
    pet_of = {p["sku"]: p["pet_type"] for p in found}
    pets = {}
    for cid, skus in skus_of.items():
        if not skus:
            raise AitoError(f"{cid} declared no pets and has no orders: Retention has nothing to read their pets from")
        if missing := skus - pet_of.keys():
            raise AitoError(f"{cid}'s orders hold products the catalogue doesn't: {sorted(missing)}")
        pets[cid] = " ".join(sorted({pet_of[s] for s in skus}))
    return pets
