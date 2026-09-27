"""Demand Forecast — what the service asks Aito, and how it scores itself.

Offline: a fake client records each call and answers from a tiny panel.
These pin the three corrections in ADR 0014 §Correction: the forecast
remembers last month, accuracy is a time split judged against the naive
"same range as last month" rule, and a failed Aito call is an error, not
a forecast of zero.
"""

from __future__ import annotations

import pytest

from src import cache
from src.aito_client import AitoError
from src.demand_forecast import LATEST_MONTH
from src.demand_service import get_demand


def _row(sku: str, month: str, units: int, last: int, bucket: str, last_bucket: str) -> dict:
    return {"product_sku": sku, "month": month, "units_sold": units,
            "units_last_month": last, "units_bucket": bucket,
            "units_last_month_bucket": last_bucket, "pet_type": "dog",
            "category": "dry-food", "brand": "Acme", "season": "spring"}


# Two SKUs over two months. In the latest month SKU-A stayed in its
# range (8-15 → 8-15) and SKU-B jumped (4-7 → 16-31): naive gets 1 of 2.
PANEL = [
    _row("SKU-A", "2026-03", 9, 4, "8-15", "4-7"),
    _row("SKU-A", LATEST_MONTH, 12, 9, "8-15", "8-15"),
    _row("SKU-B", "2026-03", 5, 0, "4-7", "0"),
    _row("SKU-B", LATEST_MONTH, 20, 5, "16-31", "4-7"),
]


class FakeAito:
    def __init__(self, *, fail_on: str | None = None):
        self.fail_on = fail_on
        self.calls: list[tuple[str, dict]] = []

    def _record(self, name: str, **kwargs):
        self.calls.append((name, kwargs))
        if name == self.fail_on:
            raise AitoError(f"{name} failed", status_code=500)

    def search(self, table, where=None, limit=10, offset=0, select=None):
        self._record("search", table=table, where=where)
        if table == "products":
            return {"hits": [{"sku": "SKU-A", "name": "A"}, {"sku": "SKU-B", "name": "B"}]}
        rows = [r for r in PANEL if not where or all(r.get(k) == v for k, v in where.items())]
        return {"hits": rows[offset:offset + limit], "total": len(rows)}

    def estimate(self, table, where, estimate_field):
        self._record("estimate", where=where)
        return {"estimate": 11.0, "why": None}

    def relate(self, table, where, relate_field, limit=10):
        self._record("relate", where=where)
        return {"hits": []}

    def evaluate(self, table, where, predict_field, **kwargs):
        self._record("evaluate", where=where, predict_field=predict_field, **kwargs)
        return {"accuracy": 0.5, "baseAccuracy": 0.5, "n": 2}


@pytest.fixture(autouse=True)
def _no_cache():
    cache.clear()
    yield
    cache.clear()


def _calls(fake: FakeAito, name: str) -> list[dict]:
    return [kw for n, kw in fake.calls if n == name]


@pytest.mark.parametrize("failing_call", ["estimate", "evaluate", "relate"])
def test_a_failed_aito_call_raises_instead_of_showing_zeros(failing_call):
    """A swallowed error renders as "forecast 0 units" or "accuracy 0 %" —
    a confident, wrong number. The endpoint maps AitoError to a 502."""
    with pytest.raises(AitoError):
        get_demand(FakeAito(fail_on=failing_call), top_n=2)


def test_forecast_conditions_on_last_months_units_not_the_unseen_month():
    """`month: "2026-05"` matches no training row, so it is no evidence;
    last month's units are the evidence that tracks a growing SKU."""
    fake = FakeAito()
    get_demand(fake, top_n=2)
    wheres = [c["where"] for c in _calls(fake, "estimate")]
    assert wheres and all("month" not in w for w in wheres)
    assert {w["product_sku"]: w["units_last_month"] for w in wheres} == {"SKU-A": 12, "SKU-B": 20}


def test_accuracy_trains_on_earlier_months_and_tests_on_the_latest():
    fake = FakeAito()
    get_demand(fake, top_n=2)
    (call,) = _calls(fake, "evaluate")
    assert call["predict_field"] == "units_bucket"
    assert call["test"] == {"month": LATEST_MONTH}
    assert call["train"] == {"month": {"$not": LATEST_MONTH}}
    assert call["where"]["units_last_month_bucket"] == {"$get": "units_last_month_bucket"}
    assert "month" not in call["where"]


def test_page_reports_the_naive_forecast_on_the_same_test_rows():
    """Naive = "this month lands in last month's range". SKU-A stayed,
    SKU-B jumped: 1 of 2. The model must be shown next to this number."""
    evaluation = get_demand(FakeAito(), top_n=2).evaluation
    assert evaluation.naive_accuracy == 0.5
    assert evaluation.n == 2
    assert evaluation.accuracy == 0.5 and evaluation.base_accuracy == 0.5


def test_naive_score_refuses_a_test_set_that_disagrees_with_aitos():
    """The naive rate is computed from our own read of the test month; if
    that read and Aito's `n` differ, the two numbers are not comparable."""
    class Mismatched(FakeAito):
        def evaluate(self, *a, **kw):
            super().evaluate(*a, **kw)
            return {"accuracy": 0.5, "baseAccuracy": 0.5, "n": 3}

    with pytest.raises(AssertionError, match="test rows"):
        get_demand(Mismatched(), top_n=2)
