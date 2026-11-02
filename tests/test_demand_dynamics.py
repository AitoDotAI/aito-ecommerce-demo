"""Demand that moves over time (ADR 0062): off, it changes nothing; on, a product has a time profile of its own."""
from types import SimpleNamespace

import pytest

from data import demand_dynamics, planted_switches

MONTHS = [f"{2024 + (4 + i) // 12}-{(4 + i) % 12 + 1:02d}" for i in range(24)]
PRODUCTS = [SimpleNamespace(sku=f"SKU-{i:03d}", category="toys", pet_type="dog", price_eur=10.0 + i) for i in range(300)]


@pytest.fixture
def switches():
    saved = dict(planted_switches.ON)
    yield planted_switches.ON
    planted_switches.ON.update(saved)


def plan(launches=None):
    return demand_dynamics.plan(42, PRODUCTS, MONTHS, launches or {}, frozenset())


def test_every_switch_is_off_in_the_committed_fixtures():
    assert not any(planted_switches.ON[name] for name in ("D1", "D2", "D3"))


def test_with_the_switches_off_no_product_has_a_time_profile():
    dynamics = plan()
    assert {dynamics.factor(p.sku, m, None) for p in PRODUCTS for m in MONTHS} == {1.0}


def test_seasonal_ware_sells_in_its_season_and_little_outside_it(switches):
    switches["D1"] = True
    dynamics = plan()
    winter = next(sku for sku, season in dynamics.seasonal.items() if season == "winter")
    assert dynamics.factor(winter, "2025-01", None) > 4 * dynamics.factor(winter, "2025-07", None)


def test_a_rising_trend_grows_month_on_month_and_a_fading_one_shrinks(switches):
    switches["D2"] = True
    dynamics = plan()
    rising = next(sku for sku, (direction, _) in dynamics.trend.items() if direction > 0)
    fading = next(sku for sku, (direction, _) in dynamics.trend.items() if direction < 0)
    assert dynamics.factor(rising, MONTHS[-1], None) > dynamics.factor(rising, MONTHS[0], None)
    assert dynamics.factor(fading, MONTHS[-1], None) < dynamics.factor(fading, MONTHS[0], None)


def test_a_fairly_priced_good_launch_takes_off_and_a_dear_poor_one_flops(switches):
    switches["D3"] = True
    dynamics = plan({"SKU-000": "2024-08", "SKU-299": "2024-08"})
    dynamics.launch_strength.update({"SKU-000": 2.5, "SKU-299": 0.2})
    assert dynamics.launch_factor("SKU-000", "2024-11", "2024-08") > 2.0
    assert dynamics.launch_factor("SKU-299", "2024-11", "2024-08") < 1.0
    assert dynamics.launch_factor("SKU-000", "2025-06", "2024-08") is None


def test_the_plan_is_the_same_for_the_same_seed():
    assert plan().seasonal == plan().seasonal and plan().trend == plan().trend
