"""Search in the Shop (src/shop_search.py), against a fake Aito."""

import pytest

from tests.fake_shop_aito import FakeShopAito, product
from src.shop_search import search_shop


def test_only_products_whose_name_matches_are_ranked_for_the_shopper():
    # SKU-N matches no query word ($score 1.0): it isn't a result, however likely.
    fake = FakeShopAito([product("SKU-N", 0.9), product("SKU-A", 0.3), product("SKU-B", 0.2)],
                        text_scores={"SKU-N": 1.0, "SKU-A": 50.0, "SKU-B": 50.0})

    found = search_shop(fake, "helena", "2026-04", [], "dental")

    assert fake.recommends[0]["product_sku"] == {"$or": ["SKU-A", "SKU-B"]}
    assert [i.sku for i in found.items] == ["SKU-A", "SKU-B"]


def test_results_are_ranked_by_purchase_probability_times_text_match():
    # SKU-B is less likely bought, but its name matches the words far better.
    fake = FakeShopAito([product("SKU-A", 0.3), product("SKU-B", 0.2)],
                        text_scores={"SKU-A": 10.0, "SKU-B": 100.0}, last_order="SKU-X")

    found = search_shop(fake, "helena", "2026-04", [], "fresh breath")

    assert [i.sku for i in found.items] == ["SKU-B", "SKU-A"]


def test_a_result_bought_last_order_is_reasked_and_falls():
    fake = FakeShopAito([product("SKU-A", 0.3), product("SKU-B", 0.2)],
                        text_scores={"SKU-A": 10.0, "SKU-B": 100.0}, last_order="SKU-B", reasked_p=0.02)

    found = search_shop(fake, "helena", "2026-04", [], "fresh breath")

    # 0.02 × 100 < 0.3 × 10: just bought, it drops below the weaker text match.
    assert [(i.sku, i.p_if_new) for i in found.items] == [("SKU-A", None), ("SKU-B", 0.2)]


def test_the_grids_context_and_rule_apply_to_search():
    fake = FakeShopAito([product("SKU-A", 0.3)], text_scores={"SKU-A": 10.0, "SKU-C": 10.0})

    search_shop(fake, "janne", "2026-04", ["SKU-C"], "food")

    where = fake.recommends[0]
    assert {"product_sku.name": {"$match": "Grain"}} in where["$or"]
    assert "context.basket" not in where and where["context.basket_categories"]["$and"]
    assert where["product_sku"] == {"$or": ["SKU-A"]}     # the cart's own item isn't a result


def test_a_query_no_product_name_matches_says_so_and_returns_nothing():
    fake = FakeShopAito([product("SKU-A", 0.9)], text_scores={"SKU-A": 1.0})

    found = search_shop(fake, "helena", "2026-04", [], "zzz")

    assert (found.text_matched, found.items) == (False, [])
    assert fake.recommends == []
    assert found.last_query["body"]["from"] == "products"   # the page shows the query that found nothing


def test_an_empty_query_is_refused():
    with pytest.raises(ValueError, match="at least one word"):
        search_shop(FakeShopAito([]), "helena", "2026-04", [], "  ")
