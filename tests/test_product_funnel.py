"""The Funnel tab's arithmetic (src/product_funnel.py), against a fake Aito: impressions from showings, clicks
and purchases from the chance a showing ends in one, profit after the cost and the ad spend."""

from types import SimpleNamespace

import pytest

import src.product_funnel as product_funnel
from src.lookup_errors import ProductNotOnSaleError
from src.product_funnel import AD_SPEND_EUR, get_product_funnel

PRODUCT = {"sku": "SKU-1", "brand": "PetNord", "category": "treats", "pet_type": "dog"}
STATE = {"list_price_eur": 10.0, "list_price_index": 1.0, "list_price_band": "100", "discount_pct": 0.0, "on_offer": False,
         "discount_band": "none", "ad_level": "none", "rating_band": "4", "label": "none", "age": "established",
         "stock": "in_stock", "rival_launched": False, "image_count": "2-3", "description_quality": "ok"}
SALES = [{"month": f"2026-0{m}", "showings": 10, "units_sold": 2, "price_index": 1.0, "units_index": 1.0}
         for m in range(1, 5)]
# 40 showings, half ranked: 16 clicked (the ranked 8 too), 8 purchased (the ranked 4 too): units 8 ÷ 8 purchases.
COUNTS = {"impressions": (20, 8, 4), "unranked_showings": (20, 8, 4)}


class FakeAito:
    """Showings rise 50 % with an advertisement and 80 % with a 20 %+ offer; units follow the price."""

    def __init__(self, state=STATE, sales=SALES, counts=COUNTS, conversion=0.5):
        self.state, self.sales, self.counts, self.conversion = state, sales, counts, conversion

    def search(self, table, *, where=None, limit=10, **_):
        rows = {"products": [PRODUCT], "product_states": [self.state], "inventory": [{"unit_cost_eur": 6.0}],
                "monthly_sales": self.sales}[table]
        return {"hits": rows}

    def batch(self, queries):
        index = {None: 0, "clicked": 1, "purchased": 2}
        return [{"total": self.counts[q["from"]][index[next((k for k in ("clicked", "purchased") if k in q["where"]), None)]]}
                for q in queries]

    def predict(self, table, where, field, **_):
        assert where["clicked"] is True and field == "purchased", (where, field)
        conversion = 0.75 if where["product_state.image_count"] == "4+" else self.conversion
        return {"hits": [{"feature": True, "$p": conversion}, {"feature": False, "$p": 1 - conversion}]}

    def estimate(self, table, where, field, *, model=None, with_why=True):
        if field == "showings_index":
            return {"estimate": (1.5 if where["ad_level"] != "none" else 1.0) * (1.8 if where["discount_band"] == "20+" else 1.0)}
        return {"estimate": 1.0}          # units_index


@pytest.fixture(autouse=True)
def kpis(monkeypatch):
    """Clicks 40 % of showings."""
    def fake(client, sku, month, changes):
        return SimpleNamespace(estimates={"clicked": SimpleNamespace(p=0.40)})
    monkeypatch.setattr(product_funnel, "get_product_kpis", fake)


def test_the_funnel_narrows_from_showings_to_clicks_to_purchases_and_buys_units():
    funnel = get_product_funnel(FakeAito(), "SKU-1", "2026-05")

    assert funnel.changed == [] and funnel.asked == funnel.now
    now = funnel.now
    assert (now.impressions, now.clicks, now.purchases, now.units) == (10.0, 4.0, 2.0, 2.0)
    assert now.gross_profit_eur == pytest.approx(2.0 * (10.0 - 6.0)) and now.profit_eur == now.gross_profit_eur


def test_a_purchase_is_a_click_that_went_on_so_it_never_exceeds_the_clicks():
    for ad in ("none", "search", "banner"):
        for conversion in (0.1, 0.5, 0.99):
            funnel = get_product_funnel(FakeAito(conversion=conversion), "SKU-1", "2026-05", {"ad_level": ad})
            assert funnel.asked.purchases <= funnel.asked.clicks <= funnel.asked.impressions


def test_the_products_own_history_sets_the_level_and_aito_moves_it_in_odds():
    funnel = get_product_funnel(FakeAito(counts={"impressions": (20, 8, 2), "unranked_showings": (20, 8, 2)},
                                         conversion=0.25), "SKU-1", "2026-05")

    assert funnel.units_per_purchase == 2.0 and funnel.own_conversion == 0.25      # 8 units from 4 purchases
    assert funnel.now.purchases == pytest.approx(1.0) and funnel.now.units == pytest.approx(2.0)


def test_advertising_buys_showings_and_costs_money():
    funnel = get_product_funnel(FakeAito(), "SKU-1", "2026-05", {"ad_level": "banner"})

    assert funnel.asked.impressions == 15.0 and funnel.asked.purchases == 3.0     # more showings, same chance each
    assert funnel.asked.ad_spend_eur == AD_SPEND_EUR["banner"]
    assert funnel.asked.profit_eur == pytest.approx(3.0 * 4.0 - AD_SPEND_EUR["banner"])
    assert funnel.asked.profit_eur < funnel.now.profit_eur                          # on a product that sells 2 a month


def test_pictures_raise_the_conversion_not_the_showings_or_the_clicks():
    funnel = get_product_funnel(FakeAito(), "SKU-1", "2026-05", {"image_count": "4+"})

    assert funnel.asked.impressions == funnel.now.impressions and funnel.asked.clicks == funnel.now.clicks
    assert funnel.asked.purchases == pytest.approx(3.0)     # 4 clicks × 0.75


def test_a_list_price_becomes_an_index_and_a_price_the_shopper_pays():
    funnel = get_product_funnel(FakeAito(), "SKU-1", "2026-05", list_price_eur=10.4)

    assert funnel.changed == ["list_price_index"] and funnel.no_data is None
    assert funnel.asked.price_eur == 10.4 and funnel.asked.gross_profit_eur == pytest.approx(2.0 * (10.4 - 6.0))


def test_a_list_price_beyond_the_prices_tried_is_left_out_and_says_so():
    funnel = get_product_funnel(FakeAito(), "SKU-1", "2026-05", {"ad_level": "search"}, list_price_eur=12.0)

    assert funnel.changed == ["ad_level"] and funnel.asked.price_eur == 10.0       # the advertising still shows
    assert "outside what this product has sold at" in funnel.no_data


def test_an_offer_the_owner_picks_is_priced_at_its_typical_discount_and_shown_more():
    funnel = get_product_funnel(FakeAito(), "SKU-1", "2026-05", {"discount_band": "20+"})

    assert funnel.asked.impressions == pytest.approx(18.0)
    assert funnel.asked.price_eur < 10.0


def test_funnel_units_are_checked_against_units_by_price_and_a_gap_is_reported():
    agrees = get_product_funnel(FakeAito(), "SKU-1", "2026-05")       # 2 units against 1.0 × 2 mean units
    assert agrees.check_units == 2.0 and agrees.check_ok is True

    better_pictures = get_product_funnel(FakeAito(), "SKU-1", "2026-05", {"image_count": "4+"})
    assert better_pictures.check_ok is False and better_pictures.check_gap == pytest.approx(0.5)


def test_a_product_that_sold_but_never_from_a_ranked_showing_is_refused():
    with pytest.raises(Exception, match="no rate of its own"):
        get_product_funnel(FakeAito(counts={"impressions": (20, 8, 0), "unranked_showings": (20, 8, 8)}), "SKU-1", "2026-05")


def test_a_product_that_never_sold_shows_a_funnel_of_zero_purchases():
    unsold = [{**s, "units_sold": 0} for s in SALES]

    funnel = get_product_funnel(FakeAito(sales=unsold), "SKU-1", "2026-05")

    assert funnel.now.units == 0.0 and funnel.now.impressions == 10.0


def test_a_month_without_a_state_is_refused():
    class NoState(FakeAito):
        def search(self, table, **kw):
            return {"hits": []} if table == "product_states" else super().search(table, **kw)

    with pytest.raises(ProductNotOnSaleError):
        get_product_funnel(NoState(), "SKU-1", "2026-05")
