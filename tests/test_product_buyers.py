"""Product › For whom (src/product_buyers.py): who buys a product.

One `_relate` per declared customer field over the product's order
lines. A fake client answers them; the hits are in the shape
`normalize_response` produces. The shopper link picks the Shop shopper
whose declared profile (data/customers.json) the clear lifts favour.
"""

from __future__ import annotations

import pytest

from src.aito_client import AitoError
from src.product_buyers import BUYER_FIELDS, BuyerRow, get_buyers, shopper_for

SKU = "SKU-PT-0192"


def _hit(field, value, lift, on_condition):
    return {"related": {field: {"$has": value}}, "lift": lift,
            "fs": {"fOnCondition": on_condition, "fCondition": 157, "f": 1000, "n": 38013}}


class FakeClient:
    def __init__(self):
        self.relates: list[dict] = []

    def relate(self, *, table, where, relate_field, limit):
        self.relates.append({"from": table, "where": where, "relate": relate_field})
        if relate_field != "order_id.customer_id.pets":
            return {"hits": [_hit(relate_field, "x", 1.02, 40)]}
        return {"hits": [_hit("order_id.customer_id.pets", "cat", 0.52, 3),
                         _hit("order_id.customer_id.pets", "dog", 1.30, 157)]}


def row(field: str, value: str, lift: float, lines: int = 50) -> BuyerRow:
    return BuyerRow(f"order_id.customer_id.{field}", value, lift, lines, 157)


def test_each_declared_field_is_related_over_the_products_order_lines():
    client = FakeClient()

    get_buyers(client, SKU)

    assert sorted(r["relate"] for r in client.relates) == sorted(BUYER_FIELDS)
    assert all(r["from"] == "order_lines" and r["where"] == {"product_sku": SKU} for r in client.relates)


def test_a_lift_on_a_handful_of_lines_ranks_below_well_supported_lifts():
    # Cat households are 0.52× on 3 of 157 lines: further from 1 than dog
    # households' 1.30× on 157 lines, but three lines are not a finding.
    buyers = get_buyers(FakeClient(), SKU)

    pets = [b.value for b in buyers if b.field.endswith("pets")]
    assert pets == ["dog", "cat"]
    assert (buyers[0].value, buyers[0].lift, buyers[0].lines, buyers[0].lines_total) == ("dog", 1.3, 157, 157)


def test_a_relate_that_fills_its_limit_fails_instead_of_dropping_values():
    class FullPageClient(FakeClient):
        def relate(self, *, table, where, relate_field, limit):
            return {"hits": [_hit(relate_field, f"v{i}", 1.0, 5) for i in range(limit)]}

    with pytest.raises(AitoError, match="may have been cut off"):
        get_buyers(FullPageClient(), SKU)


def test_the_shopper_link_goes_to_the_shopper_the_clear_lifts_describe():
    # Medium dogs, grain-free diets: Janne's declared household.
    link = shopper_for([row("pets", "dog", 1.3), row("dog_size", "medium", 1.32), row("diet", "grain-free", 1.23, 12)])

    assert link is not None and link.key == "janne"
    assert link.matches == ["medium", "dog", "grain-free"]


def test_thin_or_flat_lifts_choose_no_shopper():
    # A large dog at 1.9× on 4 lines is not a finding, and 1.05× is no difference.
    assert shopper_for([row("dog_size", "large", 1.9, lines=4), row("pets", "dog", 1.05)]) is None


def test_a_product_its_buyers_avoid_links_to_no_shopper():
    assert shopper_for([row("pets", "dog", 0.6), row("pets", "cat", 0.7)]) is None
