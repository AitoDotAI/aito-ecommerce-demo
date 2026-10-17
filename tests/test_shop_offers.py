"""This month's offers, a fact from price_history (src/shop_offers.py)."""

import pytest

from src.aito_client import AitoError
from src.shop_offers import offers_this_month


class FakeAito:
    def __init__(self, rows, total=None):
        self.rows, self.total = rows, total

    def search(self, table, *, where, limit=10, **_):
        assert table == "price_history" and where["month"] == "2026-04"
        return {"hits": self.rows, "total": self.total if self.total is not None else len(self.rows)}


def test_only_a_discount_a_shopper_would_notice_is_an_offer():
    fake = FakeAito([{"product_sku": "SKU-A", "discount_pct": 17.5},
                     {"product_sku": "SKU-B", "discount_pct": 1.5},    # list-price noise
                     {"product_sku": "SKU-C", "discount_pct": -1.2}])  # a premium

    assert offers_this_month(fake, ["SKU-A", "SKU-B", "SKU-C"], "2026-04") == {"SKU-A": 17.5}


def test_more_than_one_price_per_product_and_month_raises():
    with pytest.raises(AitoError, match="more than one"):
        offers_this_month(FakeAito([{"product_sku": "SKU-A", "discount_pct": 0}], total=2), ["SKU-A"], "2026-04")
