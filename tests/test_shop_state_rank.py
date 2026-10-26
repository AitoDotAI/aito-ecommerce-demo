"""The Shop's "state in the ranking" option: a month's offer and stars re-score Aito's `$p` (src/shop_rescore.py).

    offer:  score = $p × lift(offer band now) / lift(no offer)
    change: score = $p × lift(offer band now) / lift(last month's band) × lift(stars now) / lift(last month's)

The lifts are the shop-wide ones of tests/test_shop_rescore.py.
"""

import pytest

from src.shop_rescore import previous_month, state_rescore
from tests.test_shop_rescore import DISCOUNT_LIFTS, RATING_LIFTS, item, lifts_batch


class FakeAito:
    """product_states by month, and the lifts' batch."""
    env = "fake"

    def __init__(self, rows: dict[str, list[dict]]):
        self.rows = rows

    def search(self, table, *, where, limit, **_):
        assert table == "product_states"
        hits = [r for r in self.rows[where["month"]] if r["product_sku"] in where["product_sku"]["$or"]]
        return {"total": len(hits), "hits": hits}

    def batch(self, queries):
        return lifts_batch()["data"]


def state(sku: str, band: str = "none", stars: str = "4") -> dict:
    return {"product_sku": sku, "discount_band": band, "rating_band": stars}


ITEMS = [item("A", 0.30), item("B", 0.29), item("C", 0.28)]


def test_an_offer_lifts_a_product_over_the_ones_without():
    client = FakeAito({"2026-04": [state("A"), state("B", "20+"), state("C")]})

    ranked = state_rescore(client, ITEMS, "2026-04", "offer")

    assert [i.sku for i in ranked] == ["B", "A", "C"]
    lift = DISCOUNT_LIFTS["20+"] / DISCOUNT_LIFTS["none"]
    assert ranked[0].adjustment.score == pytest.approx(0.29 * lift)
    assert ranked[0].measured_rank == 2          # where Aito alone put it


def test_the_offer_mode_leaves_the_stars_alone():
    client = FakeAito({"2026-04": [state("A", stars="1-2"), state("B", stars="5"), state("C")]})

    ranked = state_rescore(client, ITEMS, "2026-04", "offer")

    assert [i.sku for i in ranked] == ["A", "B", "C"]
    assert all(i.adjustment.rating_factor == 1.0 for i in ranked)


def test_the_change_mode_moves_only_what_changed_since_last_month():
    client = FakeAito({"2026-04": [state("A", "20+"), state("B", "20+"), state("C", stars="5")],
                       "2026-03": [state("A", "20+"), state("B"), state("C", stars="4")]})

    ranked = state_rescore(client, ITEMS, "2026-04", "change")

    by_sku = {i.sku: i.adjustment for i in ranked}
    assert by_sku["A"].offer_factor == pytest.approx(1.0)       # on offer last month too: nothing new
    assert by_sku["B"].offer_factor == pytest.approx(DISCOUNT_LIFTS["20+"] / DISCOUNT_LIFTS["none"])
    assert by_sku["C"].rating_factor == pytest.approx(RATING_LIFTS["5"] / RATING_LIFTS["4"])


def test_a_product_with_no_state_row_keeps_aitos_probability():
    client = FakeAito({"2026-04": [state("A", "20+")]})

    ranked = state_rescore(client, ITEMS, "2026-04", "offer")

    assert [i.sku for i in ranked] == ["A", "B", "C"]
    assert ranked[1].adjustment is None and ranked[1].p == 0.29


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError, match="state mode"):
        state_rescore(FakeAito({}), ITEMS, "2026-04", "stars")


def test_the_previous_month_crosses_a_year():
    assert (previous_month("2026-04"), previous_month("2026-01")) == ("2026-03", "2025-12")
