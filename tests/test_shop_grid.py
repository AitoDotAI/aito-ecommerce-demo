"""The Shop grid (src/shop_grid.py, src/shop_ranking.py), against a fake Aito."""

from dataclasses import replace

import pytest

from src.aito_client import AitoError
from src.lookup_errors import UnknownProductError
from src.shop_grid import get_shop_grid
from src.shop_reasons import Reason
from src.shop_rescore import ScoreAdjustment
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


def test_skus_that_share_a_name_show_as_one_card_the_highest_ranked():
    # The generator names SKU-PT-0542 and SKU-PT-0544 alike, with the same details.
    fake = FakeAito([product("SKU-0544", 0.44, name="Veggie Crunch Treats 100g"),
                     product("SKU-0554", 0.43, name="Fruit Drops Treats 200g"),
                     product("SKU-0542", 0.37, name="Veggie Crunch Treats 100g")], last_order="SKU-X")

    grid = get_shop_grid(fake, "helena", "2026-04", [])

    assert [(i.sku, i.p, i.same_name_skus) for i in grid.items] == [
        ("SKU-0544", 0.44, ["SKU-0542"]), ("SKU-0554", 0.43, [])]


def test_in_the_sandbox_the_levered_sku_wins_its_name_and_its_rank_change_counts_cards(monkeypatch):
    # Measured: the twin SKU-0564 is the 2nd card. The owner levered SKU-0563.
    fake = FakeAito([product("SKU-W", 0.40, name="Exercise Wheel"),
                     product("SKU-0564", 0.30, name="Trixie Hideout"),
                     product("SKU-F", 0.29, name="Fruit Drops"),
                     product("SKU-0563", 0.27, name="Trixie Hideout")], last_order="SKU-X")

    def levered(client, items, month):
        offer = ScoreAdjustment(aito_p=0.27, offer_band="20+", offer_factor=1.81, rating_band="4",
                                rating_band_before="4", rating_factor=1.0, score=0.49)
        measured = [replace(i, measured_rank=r) for r, i in enumerate(items, start=1)]
        rescored = [replace(i, adjustment=offer) if i.sku == "SKU-0563" else i for i in measured]
        return sorted(rescored, key=lambda i: -(i.adjustment.score if i.adjustment else i.p))
    monkeypatch.setattr("src.shop_grid.rescore", levered)

    grid = get_shop_grid(fake, "helena", "2026-05", [], rescored=True)

    assert [i.sku for i in grid.items] == ["SKU-0563", "SKU-W", "SKU-F"]
    # Its name was the 2nd card before the lever, now the 1st: "↑ 1", not "↑ 3".
    assert grid.items[0].measured_rank == 2 and grid.items[0].same_name_skus == ["SKU-0564"]


@pytest.mark.parametrize("shopper_key", ["eemil", "juhani"])
def test_a_shopper_without_a_pet_profile_is_ranked_from_the_pets_of_their_orders(shopper_key):
    # Eemil declared no pets; Juhani declined tracking too, so he has no contexts and
    # nothing but his orders to read. Both used to fail on `customer["pets"]`.
    fake = FakeAito([product("SKU-A", 0.5)])

    grid = get_shop_grid(fake, shopper_key, "2026-04", [])

    where = fake.recommends[0]
    assert where["context.pets_from_orders"] == {"$and": [{"$match": "cat"}]}
    assert "context.customer.pets" not in where and "context.customer" not in where
    assert where["product_sku.pet_type"] == {"$or": ["cat"]}
    assert [i.sku for i in grid.items] == ["SKU-A"]


def test_a_shopper_without_a_profile_or_an_order_is_refused_loudly():
    from src.shop_ranking import UnknownShopperProfileError

    fake = FakeAito([product("SKU-A", 0.5)])

    with pytest.raises(UnknownShopperProfileError, match="CUST-01896"):
        get_shop_grid(fake, "eemil", "2024-05", [])   # the fake's earliest order is 2025-11


def test_the_customer_is_in_the_query_only_when_asked_for_beside_their_pets():
    plain, personal = FakeAito([product("SKU-A", 0.5)]), FakeAito([product("SKU-A", 0.5)])

    get_shop_grid(plain, "helena", "2026-04", [])
    grid = get_shop_grid(personal, "helena", "2026-04", [], identity=True)

    assert "context.customer" not in plain.recommends[0]
    # An id condition brings none of the customer's fields (and none at all when the id has no rows),
    # so the declared pets stay as a path, and the pets filter stays unless asked to trust.
    assert personal.recommends[0]["context.customer"] == "CUST-00053" and grid.identity is True
    assert "context.customer.pets" in personal.recommends[0] and "product_sku.pet_type" in personal.recommends[0]


def test_trusting_the_customer_drops_the_pets_filter_too():
    trusting = FakeAito([product("SKU-A", 0.5)])

    grid = get_shop_grid(trusting, "helena", "2026-04", [], identity=True, trust=True)

    assert "product_sku.pet_type" not in trusting.recommends[0] and grid.trust is True


def test_trust_means_nothing_without_the_customer():
    fake = FakeAito([product("SKU-A", 0.5)])

    grid = get_shop_grid(fake, "helena", "2026-04", [], trust=True)

    assert "product_sku.pet_type" in fake.recommends[0] and grid.trust is False
