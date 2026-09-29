"""Price view — which findings it is allowed to show.

Offline: a fake client answers from a tiny price history. These pin the
two rules that keep the view from presenting noise as a finding: an
"outlier" needs enough history to have a band, and a "sweet spot" needs
enough support for its lift to be distinguishable from 1.
"""

from __future__ import annotations

import pytest

from src import cache
from src.price_service import get_prices


def _prices(sku: str, values: list[float]) -> list[dict]:
    return [{"product_sku": sku, "price_eur": v, "discount_pct": 0.0} for v in values]


PRODUCTS = [
    # Two observations, list price far above them: looks like an outlier,
    # but a band from two points means nothing.
    {"sku": "THIN", "name": "Cage Cover", "pet_type": "small_animal",
     "category": "accessories", "price_eur": 18.77},
    # Twelve observations tightly around 10, list price 14: a real outlier.
    {"sku": "REAL", "name": "Chicken Dog Food", "pet_type": "dog",
     "category": "dry-food", "price_eur": 14.00},
    # Twelve observations around 5, list price inside the band.
    {"sku": "FAIR", "name": "Cat Litter", "pet_type": "cat",
     "category": "litter", "price_eur": 5.00},
]
HISTORY = (
    _prices("THIN", [17.37, 17.79])
    + _prices("REAL", [9.8, 10.0, 10.2] * 4)
    + _prices("FAIR", [4.8, 5.0, 5.2] * 4)
)


def _relate_hit(category: str, lift: float, f_on: int, f_cond: int, f: int, n: int) -> dict:
    return {"related": {"product_sku.category": {"$has": category}}, "lift": lift,
            "fs": {"fOnCondition": f_on, "fCondition": f_cond, "f": f, "n": n},
            "ps": {"pOnCondition": f_on / f_cond, "p": f / n}}


class FakeAito:
    def search(self, table, where=None, limit=10, offset=0, **_):
        rows = {"price_history": HISTORY, "products": PRODUCTS}[table]
        return {"hits": rows[offset:offset + limit], "total": len(rows)}

    def aggregate(self, table, where, aggregate_fields):
        return {"mean": 10.0}

    def relate(self, table, where, relate_field, limit=10):
        return {"hits": [
            # Big lift, tiny support: indistinguishable from 1.
            _relate_hit("grooming", 1.66, f_on=11, f_cond=1000, f=66, n=10000),
            # Modest lift, huge support: a real effect.
            _relate_hit("toys", 1.30, f_on=390, f_cond=1000, f=3000, n=10000),
        ]}


@pytest.fixture(autouse=True)
def _no_cache():
    cache.clear()
    yield
    cache.clear()


def test_a_sku_with_two_observations_is_never_flagged_as_an_outlier():
    """The live view opened on exactly this: a cage cover whose "band"
    came from two sales (demo review, 2026-09-28)."""
    bands = {b.sku: b for b in get_prices(FakeAito()).fair_bands}
    assert bands["THIN"].outlier is False


def test_a_well_supported_outlier_is_still_flagged_and_listed_first():
    response = get_prices(FakeAito())
    assert {b.sku: b.outlier for b in response.fair_bands}["REAL"] is True
    assert response.fair_bands[0].sku == "REAL"
    assert response.summary["outlier_skus"] == 1


def test_a_sweet_spot_needs_a_lift_distinguishable_from_one():
    """Grooming's 1.66 rests on 11 rows; its 95 % interval spans 1. Toys'
    1.30 rests on 390; its interval excludes 1. Only toys is a finding."""
    spots = get_prices(FakeAito()).sweet_spots
    assert {s.category for s in spots} == {"toys"}
