"""Offline tests for the Churn drivers (src/churn_drivers.py).

A fake client stands in for Aito and records each `_relate` and count it
is asked.
The hits it returns have the shape `normalize_response` produces, so these
tests cover which questions are asked and how the answers become the list,
not the HTTP layer (`test_aito_methods.py`, `test_v2_compat.py`). The live
behaviour of the same queries is asserted in `test_aito_check.py`.
"""

from __future__ import annotations

import pytest

from src.aito_client import AitoError
from src.churn_drivers import CHURNED, PROFILE_FIELDS, TENURE_BANDS, get_churn_drivers


CUSTOMERS, CHURNERS = 3000, 1000


def _hit(lift: float, related: dict) -> dict:
    # 300 customers have the value; Aito's lift fixes how many churned.
    f = 300
    churners = round(f * (CHURNERS / CUSTOMERS) * lift)
    return {
        "related": related,
        "lift": lift,
        "fs": {"f": f, "fOnCondition": churners, "fCondition": CHURNERS, "n": CUSTOMERS},
    }


class FakeClient:
    """Answers `relate` from `lifts` ({field: {value: lift}}) and counts from
    `tenure` ({band label: (customers in band, churners in band)})."""

    def __init__(self, lifts: dict, tenure: dict):
        self.lifts = lifts
        self.tenure = tenure
        self.calls: list[dict] = []
        self.counted: list[dict | None] = []

    def relate(self, *, table, where, relate_field, limit):
        self.calls.append({"table": table, "where": where, "relate": relate_field})
        values = self.lifts.get(relate_field, {})
        return {"hits": [_hit(lift, related={relate_field: {"$has": v}}) for v, lift in values.items()]}

    def search(self, table, *, where=None, limit=10):
        assert table == "customers" and limit == 0
        self.counted.append(where)
        if where is None:
            return {"total": CUSTOMERS}
        if where == CHURNED:
            return {"total": CHURNERS}
        for label, band in TENURE_BANDS:
            in_band, churners_in_band = self.tenure[label]
            if where == band:
                return {"total": in_band}
            if where == {"$and": [CHURNED, band]}:
                return {"total": churners_in_band}
        raise AssertionError(f"unexpected count: {where}")


# Each band holds a third of everyone and a third of the churners: lift 1.
NEUTRAL_TENURE = {label: (CUSTOMERS // 3, CHURNERS // 3) for label, _ in TENURE_BANDS}


def _client(tenure: dict | None = None, **lifts) -> FakeClient:
    neutral = {f: {"a": 1.0, "b": 1.0} for f in PROFILE_FIELDS}
    return FakeClient({**neutral, **lifts}, tenure or NEUTRAL_TENURE)


def test_every_profile_field_is_related_over_churned_customers_not_months():
    client = _client()

    get_churn_drivers(client)

    # One `_relate` per profile field, on the customers table with churn as
    # the condition: each customer counts once, however long they stayed.
    assert {c["table"] for c in client.calls} == {"customers"}
    assert all(c["where"] == CHURNED for c in client.calls)
    assert sorted(c["relate"] for c in client.calls) == sorted(PROFILE_FIELDS)


def test_tenure_bands_are_counted_with_and_without_churn():
    client = _client()

    get_churn_drivers(client)

    # v2 `_relate` can't relate a range, so each band is two counts (band,
    # band among churners) against the two totals.
    for _, band in TENURE_BANDS:
        assert band in client.counted
        assert {"$and": [CHURNED, band]} in client.counted
    assert dict(TENURE_BANDS)["18 months or more"] == {"tenure_months": {"$gte": 18}}


def test_tenure_lift_is_the_bands_churn_rate_over_everyones():
    # 635 of 3000 customers have 18+ months, and 395 of them churned.
    client = _client(tenure={**NEUTRAL_TENURE, "18 months or more": (635, 395)})

    long_tenure = next(d for d in get_churn_drivers(client).drivers if d.value == "18 months or more")

    assert (long_tenure.customers, long_tenure.churners) == (635, 395)
    assert long_tenure.churn_rate == round(395 / 635, 4)            # 62 %
    assert long_tenure.churn_rate_overall == round(1000 / 3000, 4)  # 33 %
    assert long_tenure.lift == round((395 / 635) / (1000 / 3000), 2)


def test_drivers_keep_strong_lifts_sorted_by_distance_from_one():
    client = _client(
        segment={"aquarium_owner": 1.38, "cat_owner": 0.89, "dog_owner": 0.99},
        region={"oulu": 1.34, "helsinki": 0.91},
        # Lifts 0.38 (under 6 months) and 1.45 (18+); 6–17 months stays at 1.0.
        tenure={"under 6 months": (1000, 127), "6–17 months": (1000, 333), "18 months or more": (1000, 483)},
    )

    result = get_churn_drivers(client)

    assert [(d.field, d.value, d.lift) for d in result.drivers] == [
        ("tenure", "under 6 months", 0.38),
        ("tenure", "18 months or more", 1.45),
        ("segment", "aquarium_owner", 1.38),
        ("region", "oulu", 1.34),
    ]


def test_driver_row_reads_as_churn_rate_in_the_group_vs_overall():
    client = _client(region={"oulu": 1.34})

    oulu = get_churn_drivers(client).drivers[0]

    # From `fs`: 300 customers in Oulu, 134 of them churned (fOnCondition),
    # against 1000 of 3000 customers overall (fCondition / n).
    assert (oulu.customers, oulu.churners) == (300, 134)
    assert oulu.churn_rate == round(134 / 300, 4)
    assert oulu.churn_rate_overall == round(1000 / 3000, 4)


def test_fields_with_no_effect_are_named_not_dropped():
    client = _client(segment={"aquarium_owner": 1.38})

    result = get_churn_drivers(client)

    # The reader should see "lifestyle doesn't predict churn here", not an
    # absence they can't tell apart from "lifestyle wasn't asked".
    assert "segment" not in result.fields_without_effect
    assert "lifestyle" in result.fields_without_effect
    assert "tenure" in result.fields_without_effect


def test_a_field_with_no_hits_fails_loudly():
    client = _client(lifestyle={})

    with pytest.raises(AitoError, match="lifestyle returned no hits"):
        get_churn_drivers(client)
