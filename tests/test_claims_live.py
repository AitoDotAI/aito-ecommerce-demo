"""The demo script's numbers, recomputed through the app's own endpoints (`./do aito-check` style: needs Aito).

Each test reads one claim's number from a running app on the loaded release, formats it the way
`docs/demo-script.md` writes it, and requires the script to say exactly that. The script's Product, Funnel,
Pricing, Shop and Patterns numbers were read on release 3a; the release now served is 3b, so a failure here
means the sentence is out of date, not that the app is wrong. The offline half is `tests/test_claims.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.aito_client import AitoClient
from src.config import load_config

SCRIPT = re.sub(r"\s+", " ", (Path(__file__).resolve().parents[1] / "docs" / "demo-script.md").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def app_client():
    if not AitoClient(load_config()).check_connectivity():
        pytest.skip("Aito not reachable")
    from src.app import app, release_gate
    release_gate.check()                # data routes answer 503 until the release has been checked
    assert release_gate.is_ready, f"the data does not match its release: {release_gate.status()}"
    with TestClient(app) as client:
        yield client


def get(app_client: TestClient, url: str) -> dict:
    response = app_client.get(url)
    assert response.status_code == 200, f"{url} answered {response.status_code}: {response.text[:200]}"
    return response.json()


def says(text: str) -> bool:
    return text in SCRIPT


def pct(p: float) -> str:
    return f"{round(p * 100, 1):g}"


# ── 2. Product what-if: the decision, for the Trixie Hideout (SKU-PT-0563) ──────────────


@pytest.fixture(scope="module")
def decision(app_client) -> dict:
    return get(app_client, "/api/product?sku=SKU-PT-0563&month=2026-04")["decision"]


def test_the_scripts_decision_row_is_what_the_product_view_leads_with(decision):
    now, best = decision["current"], decision["best"]
    expected = (f"bought when shown {now['p_purchase'] * 100:.1f} % → {best['p_purchase'] * 100:.1f} % "
                f"(×{decision['expected_ratio']:.2f})")

    assert says(expected), f"the demo script does not say: {expected}"


def test_the_scripts_margin_row_is_the_decisions_margin_per_100_showings(decision):
    now, best = decision["current"], decision["best"]
    expected = (f"€{now['margin_per_100_eur']:.2f} → €{best['margin_per_100_eur']:.2f} "
                f"(+{(best['margin_per_100_eur'] / now['margin_per_100_eur'] - 1) * 100:.0f} %); "
                f"break-even ×{decision['breakeven_ratio']:.2f}")

    assert says(expected), f"the demo script does not say: {expected}"


# ── 2b. Pricing and the funnel, for the dental treats (SKU-PT-0194) ──────────────────────


def test_the_scripts_funnel_row_is_the_funnel_today(app_client):
    now = get(app_client, "/api/product/funnel?sku=SKU-PT-0194&month=2026-04")["now"]
    expected = (f"{now['impressions']:.1f} showings → {now['clicks']:.1f} clicks → {now['purchases']:.1f} purchases")

    assert says(expected), f"the demo script does not say: {expected}"
    assert says(f"= {now['units']:.1f} units; profit €{now['profit_eur']:.2f}")


def test_the_scripts_pricing_row_names_the_most_profitable_price(app_client):
    best = get(app_client, "/api/product/pricing?sku=SKU-PT-0194&month=2026-04")["best"]

    assert says(f"€{best['list_price_eur']:.2f} list, €{best['profit_eur']:.2f} a month")


# ── 4. The Shop as Anna (`paivi`) ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def shop(app_client) -> dict:
    return get(app_client, "/api/shop/suggestions?shopper=paivi&month=2026-04")


def test_the_scripts_kit_path_is_the_order_and_percentages_the_shop_shows(shop):
    kit = ", ".join(f"{item['name']} {pct(item['p'])} %" for item in shop["next_for_pet"][:4])

    assert says(kit), f"the demo script does not say: {kit}"


def test_the_scripts_buy_again_card_is_the_one_the_shop_shows(shop):
    first = shop["usual"][0]

    assert says(f"{first['name']}, {round(first['p'] * 100)} %")


# ── If there's time: Patterns ───────────────────────────────────────────────────────────


def test_the_scripts_dog_food_and_dental_treats_numbers_are_the_patterns_views(app_client):
    pairs = get(app_client, "/api/shop-analytics/baskets")["pairs"]
    pair = next(p for p in pairs if (p["first_id"], p["second_id"]) == ("dog_dryfood", "dog_dentaltreats"))

    assert says(f"in the same basket {pair['lift']:.2f}× more often than chance "
                f"(interval {pair['interval_low']:.2f}–{pair['interval_high']:.2f})")
    assert says(f"{round(pair['confidence'] * 100)} % of dog dry-food orders have dental treats, "
                f"and {round(pair['reverse_confidence'] * 100)} % the other way round "
                f"({pair['orders_with_both']:,} of {pair['orders']:,} orders hold both)")
