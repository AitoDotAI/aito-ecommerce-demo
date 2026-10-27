"""The Funnel tab's arithmetic (src/product_funnel.py), against a fake Aito: impressions from showings, clicks
and purchases from the chance a showing ends in one, profit after the cost and the ad spend."""

from types import SimpleNamespace

import pytest

import src.product_funnel as product_funnel
from src.lookup_errors import ProductNotOnSaleError
from src.product_funnel import AD_SPEND_EUR, get_product_funnel

STATE = {"list_price_eur": 10.0, "list_price_index": 1.0, "list_price_band": "100", "discount_pct": 0.0, "on_offer": False,
         "discount_band": "none", "ad_level": "none"}
SALES = [{"month": f"2026-0{m}", "showings": 10, "units_sold": 2, "price_index": 1.0, "units_index": 1.0}
         for m in range(1, 5)]


class FakeAito:
    """Showings rise 50 % with an advertisement and 80 % with a 20 %+ offer; units follow the price."""

    def __init__(self, state=STATE, sales=SALES, purchased_showings=8):
        self.state, self.sales, self.purchased_showings = state, sales, purchased_showings

    def search(self, table, *, where=None, limit=10, **_):
        if table == "impressions":
            return {"hits": [], "total": self.purchased_showings}
        rows = {"product_states": [self.state], "inventory": [{"unit_cost_eur": 6.0}], "monthly_sales": self.sales}[table]
        return {"hits": rows}

    def estimate(self, table, where, field, *, model=None, with_why=True):
        if field == "showings_index":
            return {"estimate": (1.5 if where["ad_level"] != "none" else 1.0) * (1.8 if where["discount_band"] == "20+" else 1.0)}
        return {"estimate": 1.0}          # units_index


@pytest.fixture(autouse=True)
def kpis(monkeypatch):
    """Clicks 40 %, purchases 10 % of showings; a better listing lifts the purchase."""
    def fake(client, sku, month, changes):
        rate = 0.15 if changes.get("image_count") == "4+" else 0.10
        return SimpleNamespace(estimates={"clicked": SimpleNamespace(p=0.40), "purchased": SimpleNamespace(p=rate)})
    monkeypatch.setattr(product_funnel, "get_product_kpis", fake)


def test_the_funnel_runs_from_showings_to_profit():
    funnel = get_product_funnel(FakeAito(), "SKU-1", "2026-05")

    assert funnel.changed == [] and funnel.asked == funnel.now
    now = funnel.now
    assert (now.impressions, now.clicks, now.purchases) == (10.0, 4.0, 1.0)
    assert now.gross_profit_eur == pytest.approx(1.0 * (10.0 - 6.0)) and now.profit_eur == now.gross_profit_eur


def test_purchases_are_units_a_product_sells_per_showing_that_ends_in_a_purchase():
    funnel = get_product_funnel(FakeAito(purchased_showings=4), "SKU-1", "2026-05")      # 8 units from 4 purchased showings

    assert funnel.units_per_purchase == 2.0 and funnel.now.purchases == pytest.approx(2.0)
    assert funnel.check_ok is True                                                      # now it agrees with 2 units a month


def test_units_with_no_purchased_showing_are_refused():
    with pytest.raises(Exception, match="none from a showing"):
        get_product_funnel(FakeAito(purchased_showings=0), "SKU-1", "2026-05")


def test_advertising_buys_showings_and_costs_money():
    funnel = get_product_funnel(FakeAito(), "SKU-1", "2026-05", {"ad_level": "banner"})

    assert funnel.asked.impressions == 15.0 and funnel.asked.purchases == 1.5     # more showings, same chance each
    assert funnel.asked.ad_spend_eur == AD_SPEND_EUR["banner"]
    assert funnel.asked.profit_eur == pytest.approx(1.5 * 4.0 - AD_SPEND_EUR["banner"])
    assert funnel.asked.profit_eur < funnel.now.profit_eur                          # on a product that sells 1 a month


def test_pictures_raise_the_chance_of_a_purchase_not_the_showings():
    funnel = get_product_funnel(FakeAito(), "SKU-1", "2026-05", {"image_count": "4+"})

    assert funnel.asked.impressions == funnel.now.impressions
    assert funnel.asked.purchases == pytest.approx(1.5)


def test_a_list_price_becomes_an_index_and_a_price_the_shopper_pays():
    funnel = get_product_funnel(FakeAito(), "SKU-1", "2026-05", list_price_eur=12.0)

    assert funnel.changed == ["list_price_index"]
    assert funnel.asked.price_eur == 12.0 and funnel.asked.gross_profit_eur == pytest.approx(1.0 * (12.0 - 6.0))


def test_an_offer_the_owner_picks_is_priced_at_its_typical_discount_and_shown_more():
    funnel = get_product_funnel(FakeAito(), "SKU-1", "2026-05", {"discount_band": "20+"})

    assert funnel.asked.impressions == pytest.approx(18.0)
    assert funnel.asked.price_eur < 10.0


def test_funnel_units_are_checked_against_units_by_price_and_a_gap_is_reported():
    agrees = get_product_funnel(FakeAito(), "SKU-1", "2026-05")      # 1 purchase against 1.0 × 2 mean units: a gap
    assert agrees.check_units == 2.0 and agrees.check_ok is False and agrees.check_gap == pytest.approx(-0.5)

    close = get_product_funnel(FakeAito(sales=[{**s, "units_sold": 1} for s in SALES], purchased_showings=4), "SKU-1", "2026-05")
    assert close.check_ok is True


def test_a_month_without_a_state_is_refused():
    class NoState(FakeAito):
        def search(self, table, **kw):
            return {"hits": []} if table == "product_states" else super().search(table, **kw)

    with pytest.raises(ProductNotOnSaleError):
        get_product_funnel(NoState(), "SKU-1", "2026-05")
