"""The Product view (src/product_service.py): how its parts come together.

The parts have their own tests (history, buyers, decision, the two
what-ifs); here they are replaced by stand-ins, so these tests show what
the view asks of each and in what order. The default product's story is
checked against the generated data.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest

from src import product_service
from src.discount_what_if import BANDS, BandEstimate, DiscountWhatIf
from src.lookup_errors import ProductNotOnSaleError, UnknownProductError
from src.product_history import MonthRow, ProductHistory

DATA = Path(__file__).resolve().parent.parent / "data"
SKU = product_service.DEFAULT_SKU


def test_the_default_product_has_the_story_its_comment_tells():
    states = [s for s in json.loads((DATA / "product_states.json").read_text()) if s["product_sku"] == SKU]
    by_month = {s["month"]: s for s in states}

    # Data release 2's story (src/product_service.py's comment).
    assert by_month["2025-05"]["price_change"] == "rise" and by_month["2025-04"]["price_change"] == "none"
    assert by_month["2025-06"]["rival_launched"] and not by_month["2025-05"]["rival_launched"]
    assert by_month["2025-09"]["discount_band"] == "20+" and by_month["2026-03"]["discount_band"] == "20+"
    assert by_month["2026-04"]["discount_band"] == "none"


def test_the_default_product_sells_the_most_of_those_with_that_story():
    units: dict[str, int] = defaultdict(int)
    for row in json.loads((DATA / "monthly_sales.json").read_text()):
        units[row["product_sku"]] += row["units_sold"]
    states: dict[str, list[dict]] = defaultdict(list)
    for s in json.loads((DATA / "product_states.json").read_text()):
        states[s["product_sku"]].append(s)

    def has_the_story(rows: list[dict]) -> bool:
        latest = max(rows, key=lambda s: s["month"])
        return (any(s["on_offer"] for s in rows) and any(s["price_change"] == "rise" for s in rows)
                and any(s["rival_launched"] for s in rows) and not latest["on_offer"])

    candidates = [sku for sku, rows in states.items() if has_the_story(rows)]
    assert max(candidates, key=lambda sku: units[sku]) == SKU


# ── The view, from stand-ins for its parts ────────────────────────────


def month_row(month: str, band: str = "none") -> MonthRow:
    return MonthRow(month=month, units_sold=21, price_eur=2.79, list_price_eur=2.78, discount_band=band,
                    rating_band="4", age="established", rival_launched=False, price_change="none", reviews=3)


def discount(p_by_band: dict[str, float], current: str = "none") -> DiscountWhatIf:
    bands = [BandEstimate(band=b, p_purchase=p_by_band[b], vs_no_discount=p_by_band[b] / p_by_band["none"],
                          band_lift=None, product_lift=None, base_p=0.12, normaliser=1.0, calibrated=False,
                          shown=0, purchased=0, current=b == current) for b in BANDS]
    return DiscountWhatIf(sku=SKU, name="Dental Treats", current_band=current, month="2026-04",
                          bands=bands, last_query={})


@pytest.fixture
def parts(monkeypatch):
    """Stand-ins for the view's parts; `asked` records the prices the
    price what-if was asked about."""
    asked: list[float] = []
    state = {"discount": discount({"none": 0.27, "10-15": 0.42, "15-20": 0.43, "20+": 0.42})}
    history = ProductHistory(funnel=[], surfaces=[], months=[month_row("2026-03"), month_row("2026-04")],
                             ratings={}, sentiments={})
    monkeypatch.setattr(product_service, "get_product_history", lambda client, sku: history)
    monkeypatch.setattr(product_service, "get_buyers", lambda client, sku: [])
    monkeypatch.setattr(product_service, "get_discount_what_if", lambda client, sku, month: state["discount"])
    monkeypatch.setattr(product_service, "_unit_cost", lambda client, sku: 1.39)

    def price_what_if(client, sku, price):
        asked.append(price)
        return f"what-if at {price}"
    monkeypatch.setattr(product_service, "get_price_what_if", price_what_if)
    return {"asked": asked, "state": state}


def test_the_price_what_if_is_asked_at_todays_price_and_the_advised_bands(parts):
    view = product_service.get_product_view(None, SKU, "2026-04")

    # 10–15 % off wins on margin per showing; its price is 12.5 % off €2.78.
    assert view.decision.best_band == "10-15"
    assert sorted(parts["asked"]) == [2.43, 2.79]
    assert (view.price_now, view.price_best) == ("what-if at 2.79", "what-if at 2.43")


def test_when_the_advice_is_to_keep_the_price_is_asked_once(parts):
    parts["state"]["discount"] = discount({"none": 0.27, "10-15": 0.28, "15-20": 0.29, "20+": 0.30})

    view = product_service.get_product_view(None, SKU, "2026-04")

    assert view.decision.action == "keep"
    assert parts["asked"] == [2.79] and view.price_best is None


def test_a_month_the_product_was_not_on_sale_is_a_lookup_error(parts):
    with pytest.raises(ProductNotOnSaleError, match="from 2026-03 to 2026-04"):
        product_service.get_product_view(None, SKU, "2024-05")


def test_an_unknown_product_is_refused_before_any_query(parts):
    with pytest.raises(UnknownProductError):
        product_service.get_product_view(None, "SKU-NO-SUCH", "2026-04")
    assert parts["asked"] == []
