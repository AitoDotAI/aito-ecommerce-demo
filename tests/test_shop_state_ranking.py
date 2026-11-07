"""The Shop ranked by this month's product state (ADR 0065, src/shop_state_ranking.py), against a fake Aito.

The candidates are `product_states` rows of the month shown, so their price, offer and stars are part of what
is asked. A hit carries the state's id and its product's sku; the card's product fields are read from `products`.
"""

import pytest

from src.aito_client import AitoError
from src.shop_grid import get_shop_grid
from tests.fake_shop_aito import FakeShopAito, product


def state_hit(sku: str, p: float, month: str = "2026-04") -> dict:
    """A `_recommend product_state` hit with a `$why` holding one reason for it (the shape Aito 2.12.0 returned)."""
    state_id = f"{sku}-{month}"
    return {"product_state_id": state_id, "product_sku": sku, "$p": p,
            "$why": {"type": "product", "factors": [
                {"type": "baseP", "value": 0.14, "proposition": {"purchased": True}},
                {"type": "hitPropositionLift", "proposition": {"product_state": {"$has": state_id}}, "value": 1.6,
                 "factors": [{"type": "relatedPropositionLift", "proposition": {"context.month": month}, "value": 1.34}]}]}}


class FakeStateAito(FakeShopAito):
    """The state ranking's `_recommend`, and the products the cards read."""

    def __init__(self, state_hits, **kwargs):
        super().__init__([], **kwargs)
        self.state_hits = state_hits
        self.targets: list[str] = []

    def recommend(self, table, where, recommend_field, goal, *, select=None, limit=8, **_):
        self.targets.append(recommend_field)
        self.recommends.append(where)
        assert recommend_field == "product_state"
        return {"hits": self.state_hits[:limit]}


def test_the_state_ranking_recommends_this_months_states_not_products():
    fake = FakeStateAito([state_hit("SKU-A", 0.5)])

    get_shop_grid(fake, "janne", "2026-04", ["SKU-C"], state="native")

    where = fake.recommends[0]
    assert fake.targets == ["product_state"]
    assert where["product_state.month"] == "2026-04"
    assert where["product_state.product_sku"] == {"$not": {"$or": ["SKU-C"]}}      # the cart, one link further
    assert "product_sku" not in where and "product_sku.pet_type" not in where
    assert {"product_state.product_sku.name": {"$match": "Grain"}} in where["$or"]  # the household rule


def test_cards_are_ranked_by_the_states_p_and_carry_the_states_reasons():
    fake = FakeStateAito([state_hit("SKU-A", 0.30), state_hit("SKU-D", 0.60)])

    grid = get_shop_grid(fake, "helena", "2026-04", [], state="native")

    assert [i.sku for i in grid.items] == ["SKU-D", "SKU-A"]
    assert grid.items[0].p == pytest.approx(0.60)
    assert [r.lift for r in grid.items[0].reasons] == [pytest.approx(1.34)]
    assert grid.state == "native"


def test_the_panel_shows_the_state_query_that_ranked_the_cards():
    fake = FakeStateAito([state_hit("SKU-A", 0.5)])

    grid = get_shop_grid(fake, "helena", "2026-04", [], state="native")

    assert grid.last_query["body"]["recommend"] == "product_state"
    assert grid.last_query["body"]["where"]["product_state.month"] == "2026-04"


def test_an_item_bought_last_order_is_still_reasked_as_just_bought():
    fake = FakeStateAito([state_hit("SKU-B", 0.40)], reasked_p=0.02)

    grid = get_shop_grid(fake, "helena", "2026-04", [], state="native")

    assert grid.items[0].p == pytest.approx(0.02)
    assert grid.items[0].p_if_new == pytest.approx(0.40)


def test_a_hit_whose_product_is_not_in_the_catalogue_raises_rather_than_dropping_the_card():
    class NoProducts(FakeStateAito):
        def search(self, table, **kwargs):
            if table == "products":
                return {"hits": [], "total": 0}
            return super().search(table, **kwargs)

    with pytest.raises(AitoError, match="SKU-A"):
        get_shop_grid(NoProducts([state_hit("SKU-A", 0.5)]), "helena", "2026-04", [], state="native")
