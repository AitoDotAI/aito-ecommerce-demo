"""The Shop grid (src/shop_grid.py, src/shop_ranking.py), against a fake Aito."""

import pytest

from src.aito_client import AitoError
from src.lookup_errors import UnknownProductError
from src.shop_grid import get_shop_grid
from src.shop_reasons import Reason
from tests.fake_shop_aito import FakeShopAito as FakeAito, product

def test_a_household_rule_is_a_filter_on_the_candidates():
    fake = FakeAito([product("SKU-A", 0.5)])

    grid = get_shop_grid(fake, "janne", "2026-04", [])

    assert grid.rule == "grain-free"
    assert {"product_sku.name": {"$match": "Grain"}} in fake.recommends[0]["$or"]


def test_the_carts_items_are_context_and_are_not_recommended_again():
    fake = FakeAito([product("SKU-A", 0.5)])

    get_shop_grid(fake, "helena", "2026-04", ["SKU-C"])

    where = fake.recommends[0]
    assert where["product_sku"] == {"$not": {"$or": ["SKU-C"]}}
    assert where["just_bought"] is False   # ranked as not just bought; the re-ask handles those
    # The cart as words for the ranking (td-20261020210945109481); its SKUs only exclude.
    assert "context.basket" not in where and where["context.basket_categories"]["$and"]


def test_an_item_bought_last_order_is_reasked_as_just_bought_and_falls():
    # SKU-B ranks first, but the shopper bought it last order; Aito's answer
    # for "just bought" (0.02) drops it below SKU-A.
    fake = FakeAito([product("SKU-B", 0.6), product("SKU-A", 0.5)])

    grid = get_shop_grid(fake, "helena", "2026-04", [])

    [query] = fake.batches[0]
    assert query["where"]["product_sku"] == "SKU-B" and query["where"]["just_bought"] is True
    assert [i.sku for i in grid.items] == ["SKU-A", "SKU-B"]
    assert grid.items[1].p == 0.02 and grid.items[1].p_if_new == 0.6


def test_the_last_order_is_the_latest_one_before_the_month():
    fake = FakeAito([product("SKU-A", 0.5)])

    assert get_shop_grid(fake, "helena", "2026-04", []).last_order_skus == ["SKU-B", "SKU-X"]
    assert get_shop_grid(fake, "helena", "2026-01", []).last_order_skus == ["SKU-OLD"]


def test_a_cart_item_that_does_not_exist_is_refused():
    with pytest.raises(UnknownProductError, match="NOPE-1"):
        get_shop_grid(FakeAito([]), "helena", "2026-04", ["NOPE-1"])


def test_a_predict_without_a_true_answer_raises():
    fake = FakeAito([product("SKU-B", 0.6)])
    fake.batch = lambda queries: [{"hits": [{"feature": False, "$p": 1.0}]}]

    with pytest.raises(AitoError, match="no `true` hit"):
        get_shop_grid(fake, "helena", "2026-04", [])


def test_a_cart_listing_a_product_twice_is_refused():
    with pytest.raises(ValueError, match="twice"):
        get_shop_grid(FakeAito([]), "helena", "2026-04", ["SKU-C", "SKU-C"])


def test_each_item_carries_aitos_reasons_and_the_facts_beside_them():
    fake = FakeAito([product("SKU-A", 0.5, category="dry-food", pet_type="dog")], offers={"SKU-A": 17.5})

    [item] = get_shop_grid(fake, "janne", "2026-04", []).items

    assert item.reasons == [Reason("Sells in April", 1.3)]
    # Facts, not reasons: the offer this month, the stars, and the rule kept.
    assert (item.offer_pct, item.avg_rating, item.keeps_rule) == (17.5, 4.2, True)


def test_picked_for_you_shows_only_the_declared_pets_products():
    fake = FakeAito([product("SKU-A", 0.5)])

    get_shop_grid(fake, "janne", "2026-04", [])

    # Janne's household declared a dog: a rule on the candidates, like the diet.
    assert fake.recommends[0]["product_sku.pet_type"] == {"$or": ["dog"]}
