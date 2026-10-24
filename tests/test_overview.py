"""Overview (ADR 0041): the shop's totals, its household cards, and one
headline per owner view, each a link with numbers from data.

Offline: the totals are pure functions over rows as `_search` returns
them, and the headlines read the Overview payload and the snapshots the
linked views serve. The live checks are in `test_aito_check.py`.
"""

from __future__ import annotations

import pytest

from src.household_cards import rank_pill
from src.overview_headlines import owner_headlines, product_headline, retention_headline, supply_headline
from src.overview_service import months_back, shop_totals, top_products


def order(order_id, month, total, customer="C1"):
    return {"order_id": order_id, "customer_id": customer, "month": month, "total_eur": total}


# ── Totals: the last 12 months against the 12 before ─────────────────


def test_twelve_months_back_crosses_the_year():
    assert months_back("2026-04", 12) == "2025-04"
    assert months_back("2026-01", 1) == "2025-12"


def test_the_last_12_months_are_compared_with_the_12_before():
    orders = [order("O1", "2024-05", 10.0), order("O2", "2025-04", 30.0),
              order("O3", "2025-05", 50.0, "C2"), order("O4", "2026-04", 70.0, "C3"),
              order("O5", "2026-04", 20.0, "C3")]

    monthly, totals = shop_totals(orders)

    assert [m.month for m in monthly] == ["2024-05", "2025-04", "2025-05", "2026-04"]
    assert (totals["first_month"], totals["last_month"]) == ("2025-05", "2026-04")
    assert (totals["orders"], totals["orders_before"], totals["months_before"]) == (3, 2, 2)
    assert (totals["revenue_eur"], totals["revenue_before_eur"]) == (140.0, 40.0)
    assert totals["avg_basket_eur"] == pytest.approx(46.67)
    # C2 and C3 ordered in the last 12 months; C1 only before.
    assert totals["customers_ordering"] == 2


def test_best_sellers_count_units_in_the_last_12_months_only():
    month_of_order = {"O1": "2025-04", "O2": "2025-05", "O3": "2026-04"}
    lines = [{"order_id": "O1", "product_sku": "OLD", "qty": 50},
             {"order_id": "O2", "product_sku": "A", "qty": 2},
             {"order_id": "O3", "product_sku": "B", "qty": 3},
             {"order_id": "O3", "product_sku": "A", "qty": 2}]
    products = {s: {"name": f"Product {s}", "pet_type": "dog", "category": "toys"} for s in ("OLD", "A", "B")}

    best = top_products(lines, month_of_order, "2025-05", products)

    assert [(p.sku, p.units) for p in best] == [("A", 4), ("B", 3)]


# ── Household pills: derived from the numbers each card shows ────────
# Shares and baskets as the observable dataset shows them.
SHARES = {"dog": 42.1, "cat": 29.8, "dog cat": 15.2, "small_animal": 7.3, "aquarium": 5.6}
BASKETS = {"dog": 74.34, "cat": 74.74, "dog cat": 108.38, "small_animal": 119.48, "aquarium": 63.05}


def test_a_household_pill_states_only_a_rank_the_card_shows():
    assert rank_pill("small_animal", SHARES, BASKETS) == ("Highest basket", "orange")
    assert rank_pill("dog", SHARES, BASKETS) == ("Largest group", "blue")
    assert rank_pill("aquarium", SHARES, BASKETS) == ("Lowest basket", "grey")
    assert rank_pill("cat", SHARES, BASKETS) is None


# ── Headlines: one per owner view, each a link ───────────────────────

OVERVIEW = {
    "kpis": {"first_month": "2025-05", "last_month": "2026-04"},
    "top_products": [{"sku": "SKU-PT-0490", "name": "Silica Crystals Cat Litter 7kg", "units": 612}],
    "top_basket_pair": {"first": "Dog dry-food", "second": "Dog dental-treats", "first_id": "dog_dryfood",
                        "lift": 2.66, "interval_low": 2.34, "interval_high": 3.03,
                        "orders_with_both": 2911, "orders_with_first": 4325, "confidence": 0.673},
}
INVENTORY = {"kpis": [{"label": "Critical", "value": 60.0}, {"label": "Overstock", "value": 87.0},
                      {"label": "Tied capital", "value": 26576.0}, {"label": "Revenue at risk", "value": 2088.0}]}
CHURN = {"kpis": [{"label": "Total customers", "value": 3000}, {"label": "Churned", "value": 1004}],
         "drivers": [{"field": "tenure", "value": "under 6 months", "lift": 0.2, "churn_rate": 0.07,
                      "churn_rate_overall": 0.33},
                     {"field": "tenure", "value": "18 months or more", "lift": 1.85, "churn_rate": 0.62,
                      "churn_rate_overall": 0.33}]}


def test_the_patterns_headline_leads_with_the_strongest_pair_and_the_orders_without_it():
    patterns = owner_headlines(OVERVIEW, {"inventory": INVENTORY, "churn": CHURN}.get)[0]

    assert patterns["href"] == "/patterns/?anchor=dog_dryfood"
    assert patterns["headline"].startswith(
        "Dog dry-food baskets hold dog dental-treats 2.66× as often as the average basket [2.34–3.03]")
    assert patterns["detail"] == ("2,911 of 4,325 dog dry-food orders (67%) already hold dog dental-treats; "
                                  "1,414 don't.")


def test_the_product_headline_opens_the_best_seller_in_product():
    product = product_headline(OVERVIEW)

    assert product.href == "/product/?sku=SKU-PT-0490"
    assert "612 units in 2025-05 … 2026-04" in product.headline


def test_the_supply_headline_reads_the_numbers_supply_shows():
    supply = supply_headline(INVENTORY)

    assert supply.headline.startswith("Reorder 60 products below their reorder point: about €2,088")
    assert "estimated" in supply.headline   # the € rests on Aito's forecast
    assert supply.detail.startswith("87 more hold €26,576")


def test_the_retention_headline_gives_the_strongest_driver_as_observed_rates():
    retention = retention_headline(CHURN)

    assert retention.headline == "Win back 1,004 of 3,000 customers (33%) who haven't ordered in 90 days."
    assert retention.detail.startswith("Customers with tenure 18 months or more left at 62%, against 33% overall.")


def test_a_view_without_a_snapshot_shows_as_unavailable_not_absent():
    headlines = owner_headlines(OVERVIEW, lambda name: None)

    assert [h["view"] for h in headlines] == ["Patterns", "Product", "Supply", "Retention", "Evidence"]
    missing = [h for h in headlines if not h["available"]]
    assert [h["view"] for h in missing] == ["Supply", "Retention"]
    assert all("./do precompute" in h["detail"] for h in missing)


def test_a_snapshot_without_the_expected_kpi_fails_loudly():
    with pytest.raises(KeyError, match="Revenue at risk"):
        supply_headline({"kpis": [{"label": "Critical", "value": 1}]})
