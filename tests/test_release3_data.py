"""Data release 3a's absolute checks (docs/verification/release3a-prereg.md, ADR 0049 and 0050): the list price
and the listing are state, and the tables agree about them.

The planted effects themselves are ratios judged on three seeds: `python3 -m scripts.release3_effects`.
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from data import listing

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> list[dict]:
    path = DATA_DIR / name
    if not path.exists():
        pytest.skip(f"{name} missing — run `./do generate-fixtures`.")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def states() -> dict[str, dict]:
    return {st["product_state_id"]: st for st in _load("product_states.json")}


@pytest.fixture(scope="module")
def sales() -> list[dict]:
    return _load("monthly_sales.json")


def test_every_monthly_sale_has_its_state_and_the_listing_it_was_copied_from(states, sales):
    assert {ms["product_state"] for ms in sales} == set(states)
    for ms in sales:
        state = states[ms["product_state"]]
        for column in ("list_price_index", "image_count", "description_quality", "ad_level"):
            assert ms[column] == state[column], f"{ms['monthly_sale_id']}: {column}"


def test_q8a_the_effective_price_index_is_the_list_index_less_the_offer(states, sales):
    for ms in sales:
        state = states[ms["product_state"]]
        expected = state["list_price_index"] * state["price_eur"] / state["list_price_eur"]
        assert ms["price_index"] == pytest.approx(expected, abs=0.002), ms["monthly_sale_id"]


def test_q8b_the_list_price_moves_in_at_least_40_percent_of_products(states):
    seen = defaultdict(set)
    for state in states.values():
        seen[state["product_sku"]].add(state["list_price_index"])
    moving = sum(len(values) >= 2 for values in seen.values()) / len(seen)
    assert moving >= 0.40, f"only {moving:.0%} of products ever change their list price"


def test_q8c_most_products_with_a_year_of_months_show_eight_price_points(sales):
    points = defaultdict(set)
    months = Counter()
    for ms in sales:
        points[ms["product_sku"]].add(round(ms["price_index"] / 0.02))
        months[ms["product_sku"]] += 1
    long_lived = [sku for sku, n in months.items() if n >= 12]
    rich = sum(len(points[sku]) >= 8 for sku in long_lived) / len(long_lived)
    assert rich >= 0.70, f"only {rich:.0%} of products with 12+ months have 8 price points"


def test_q9_the_listing_columns_have_their_drawn_shares(states):
    def share(column: str, value: str) -> float:
        return sum(s[column] == value for s in states.values()) / len(states)
    # Drawn per product, and upgraded in a quarter / a fifth of them: the shares drift up a little.
    assert share("image_count", "0-1") == pytest.approx(0.25 * (1 - listing.IMAGE_UPGRADE_SHARE / 2), abs=0.05)
    assert share("description_quality", "thin") == pytest.approx(0.25 * (1 - listing.DESCRIPTION_UPGRADE_SHARE / 2), abs=0.05)
    # 15 % of products run a campaign of 1 to 3 months in a 24-month window: about 1.3 % of product-months.
    assert 0.008 <= 1 - share("ad_level", "none") <= 0.03


def test_q9_a_campaign_runs_one_to_three_months_and_is_never_both_levels(states):
    by_product = defaultdict(list)
    for state in sorted(states.values(), key=lambda s: s["month"]):
        by_product[state["product_sku"]].append(state["ad_level"])
    for sku, levels in by_product.items():
        advertised = [level for level in levels if level != "none"]
        assert len(set(advertised)) <= 1, f"{sku} ran two kinds of campaign"
        assert len(advertised) <= listing.CAMPAIGN_MONTHS[1], f"{sku} was advertised {len(advertised)} months"


def test_held_products_keep_their_list_price_and_run_no_extra_offers():
    held = frozenset({"SKU-A"})
    plan = listing.plan_listing(42, ["SKU-A", "SKU-B", "SKU-C", "SKU-D"], ["2025-01", "2025-02", "2025-03"], held)

    assert plan.policy["SKU-A"] == "hold"
    assert not [key for key in plan.list_index if key[0] == "SKU-A"]
    assert not [key for key in plan.extra_discount if key[0] == "SKU-A"]


def test_the_listing_is_the_same_for_the_same_seed():
    args = (7, [f"SKU-{i}" for i in range(50)], ["2025-01", "2025-02"], frozenset())

    assert listing.plan_listing(*args) == listing.plan_listing(*args)


def test_the_relative_targets_are_the_month_against_the_products_earlier_mean(sales):
    by_product = defaultdict(list)
    for ms in sorted(sales, key=lambda r: r["month"]):
        by_product[ms["product_sku"]].append(ms)
    for sku, rows in list(by_product.items())[:150]:
        for i, ms in enumerate(rows):
            for column, index in (("units_sold", "units_index"), ("showings", "showings_index")):
                mean = sum(r[column] for r in rows[:i]) / i if i else 0.0
                if mean > 0:
                    assert ms[index] == pytest.approx(ms[column] / mean, abs=0.001), (sku, ms["month"], index)
                else:
                    assert ms.get(index) is None, f"{sku} {ms['month']}: {index} is set with nothing earlier to compare with"
