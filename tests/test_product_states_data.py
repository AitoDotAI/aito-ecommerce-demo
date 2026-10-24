"""ADR 0032's absolute data checks: nothing of a launched product before its
launch (P2a), and every row linked to its month's state (P0; P6 in ADR 0032's
pre-registration, renamed for ADR 0038's P6).

The planted effects themselves (P1–P5) are judged against null generations
of the same seed, which a test can't afford: `./do planted-effects`
(scripts/planted_effects.py, docs/verification/product-states-prereg.md).
"""

import json
from pathlib import Path

import pytest

from tests.fixture_joins import impressions_in_context

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> list[dict]:
    path = DATA_DIR / name
    if not path.exists():
        pytest.skip(f"{name} missing — run `./do generate-fixtures`.")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def states() -> dict[str, dict]:
    return {st["product_state_id"]: st for st in _load("product_states.json")}


@pytest.fixture(scope="module")
def launches(states) -> dict[str, str]:
    """sku → launch month, for products whose first state is after the window's first month."""
    first: dict[str, str] = {}
    for st in states.values():
        first[st["product_sku"]] = min(first.get(st["product_sku"], st["month"]), st["month"])
    window_start = min(first.values())
    return {sku: m for sku, m in first.items() if m > window_start}


def test_p2a_nothing_of_a_launched_product_exists_before_its_launch(launches):
    assert len(launches) == 50
    month_of_order = {o["order_id"]: o["month"] for o in _load("orders.json")}
    dated = (
        [(r["product_sku"], r["month"]) for r in impressions_in_context(include_visitors=True)]
        + [(r["product_sku"], month_of_order[r["order_id"]]) for r in _load("order_lines.json")]
        + [(r["product_sku"], r["month"]) for r in _load("monthly_sales.json")]
        + [(r["product_sku"], r["month"]) for r in _load("product_states.json")]
    )
    early = [(sku, m) for sku, m in dated if sku in launches and m < launches[sku]]
    assert not early, early[:5]


def test_p0_every_row_links_to_its_months_state(states):
    month_of_order = {o["order_id"]: o["month"] for o in _load("orders.json")}
    rows = (
        [(r["product_state"], r["product_sku"], r["month"]) for r in impressions_in_context(include_visitors=True)]
        + [(r["product_state"], r["product_sku"], month_of_order[r["order_id"]]) for r in _load("order_lines.json")]
        + [(r["product_state"], r["product_sku"], r["month"]) for r in _load("monthly_sales.json")]
    )
    wrong = [r for r in rows if r[0] not in states or r[0] != f"{r[1]}-{r[2]}"]
    assert not wrong, wrong[:5]
