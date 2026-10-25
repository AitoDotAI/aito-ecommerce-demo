"""Retention reads a listed household's pets from its orders when it declared none."""

import pytest

from src.aito_client import AitoError
from src.churn_risk import ScoredCustomer
from src.retention_pets import household_pets


def _customer(cid: str, pets: str | None) -> ScoredCustomer:
    return ScoredCustomer(customer_id=cid, name=cid, pets=pets, dog_size=None, region="oulu",
                          last_order_month="2026-03", tenure_months=6, visits=2, latest_rating=None,
                          risk_p=0.9, evidence={})


class Shop:
    """Orders and products as the two searches return them."""
    def __init__(self, orders, products):
        self.orders, self.products = orders, products

    def search(self, table, where=None, limit=10, offset=0, **_):
        rows = self.orders if table == "orders" else self.products
        wanted = (where or {}).get("customer_id", {}).get("$or")
        if wanted is not None:
            rows = [r for r in rows if r["customer_id"] in wanted]
        skus = (where or {}).get("sku", {}).get("$or")
        if skus is not None:
            rows = [r for r in rows if r["sku"] in skus]
        return {"hits": rows[offset:offset + limit], "total": len(rows)}


ORDERS = [{"customer_id": "A", "skus": "S1 S2"}, {"customer_id": "A", "skus": "S2"}, {"customer_id": "B", "skus": "S3"}]
PRODUCTS = [{"sku": "S1", "pet_type": "dog"}, {"sku": "S2", "pet_type": "cat"}, {"sku": "S3", "pet_type": "rabbit"}]


def test_undeclared_pets_are_the_pet_types_of_what_the_household_bought():
    pets = household_pets(Shop(ORDERS, PRODUCTS), [_customer("A", None), _customer("B", None)])

    assert pets == {"A": "cat dog", "B": "rabbit"}


def test_declared_pets_are_kept_as_declared():
    pets = household_pets(Shop(ORDERS, PRODUCTS), [_customer("A", "hamster"), _customer("B", None)])

    assert pets == {"A": "hamster", "B": "rabbit"}


def test_no_undeclared_household_means_no_lookup():
    assert household_pets(Shop([], []), [_customer("A", "dog")]) == {"A": "dog"}


def test_a_household_with_no_orders_fails_loudly():
    with pytest.raises(AitoError, match="has no orders"):
        household_pets(Shop([], PRODUCTS), [_customer("A", None)])


def test_an_order_holding_an_unknown_product_fails_loudly():
    with pytest.raises(AitoError, match="S9"):
        household_pets(Shop([{"customer_id": "A", "skus": "S9"}], PRODUCTS), [_customer("A", None)])
