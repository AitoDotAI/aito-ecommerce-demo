"""The `?` popover of a k-NN `_estimate` (Inventory, Demand), in units.

Aito's default `_estimate` averages the nearest past months. Each
neighbour's value is `mean + Σ field terms + its own residual`, and the
field terms are the query's own, the same in every neighbour. So the
estimate splits into a base, one row per field and one "similar past
months" row, all in units.

The popover used to read these values as log-scale deltas and printed
`units_last_month=30` (+15.39 units) as "↑ 483987665%". The neighbours
below are two of the eight env `observable` returned for SKU-PT-0206 on
2026-10-24 (values rounded).
"""

import math

import pytest

from src.aito_client import AitoError
from src.estimate_why import explain_estimate

FIELD_TERMS = {
    "units_last_month": 15.392, "product_sku": 6.658, "category": -1.953,
    "season": 0.480, "pet_type": -0.235, "brand": -0.083,
}
WHERE = {"units_last_month": 30, "product_sku": "SKU-PT-0206", "category": "accessories",
         "season": "spring", "pet_type": "dog", "brand": "PetNord"}
MEAN = 3.300
RESIDUALS = [4.132, -20.014]


def neighbour(residual, *, terms=FIELD_TERMS, mean=MEAN, multiply=False, weight=1.0):
    adjustments = {"type": "sum", "terms": [
        {"type": "input", "name": "residual", "value": residual},
        *[{"type": "regression", "proposition": {field: WHERE[field]}, "value": value}
          for field, value in terms.items()],
        {"type": "mean centering", "name": "mean", "value": mean},
    ]}
    total = mean + residual + sum(terms.values())
    if multiply:
        adjustments = {"type": "exponent", "base": {"type": "constant", "value": math.e},
                       "power": adjustments}
    value = math.exp(total) if multiply else total
    return {"weight": weight, "value": {"type": "neighborContext", "value": value,
                                        "adjustments": adjustments}}


def knn_why(*neighbours):
    values = [n["value"]["value"] for n in neighbours]
    return {"type": "weightedAverage", "value": sum(values) / len(values),
            "components": list(neighbours)}


AVERAGE = MEAN + sum(FIELD_TERMS.values()) + sum(RESIDUALS) / len(RESIDUALS)


def test_a_knn_why_reads_as_a_base_plus_units_per_field_plus_similar_months():
    why = explain_estimate(knn_why(*[neighbour(r) for r in RESIDUALS]), AVERAGE, field_label="units_sold")

    assert why["form"] == "add"
    assert why["base"] == pytest.approx(MEAN)
    last_month = next(c for c in why["components"] if c["label"] == "Sold 30 last month")
    # Units added, not a log-scale delta: e^15.39 would read "+483987665 %".
    assert last_month["effect"] == pytest.approx(15.392)
    similar = next(c for c in why["components"] if c["type"] == "neighbours")
    assert similar == {"type": "neighbours", "label": "Similar past months (2 neighbours)",
                       "effect": pytest.approx(sum(RESIDUALS) / 2)}
    assert why["base"] + sum(c["effect"] for c in why["components"]) == pytest.approx(AVERAGE)


def test_every_field_gets_a_row_largest_first_none_folded_away():
    why = explain_estimate(knn_why(*[neighbour(r) for r in RESIDUALS]), AVERAGE, field_label="units_sold")

    fields = [c for c in why["components"] if c["type"] == "field"]
    assert len(fields) == len(FIELD_TERMS)
    assert [abs(c["effect"]) for c in fields] == sorted((abs(v) for v in FIELD_TERMS.values()), reverse=True)


def test_an_estimate_that_differs_from_the_neighbours_average_shows_the_gap_as_its_own_row():
    # Seen live: SKU-PT-0155's estimate was 8.08 while its neighbours averaged 10.36.
    why = explain_estimate(knn_why(*[neighbour(r) for r in RESIDUALS]), AVERAGE - 2.28, field_label="units_sold")

    gap = why["components"][-1]
    assert gap["type"] == "unexplained"
    assert gap["effect"] == pytest.approx(-2.28)
    assert why["base"] + sum(c["effect"] for c in why["components"]) == pytest.approx(AVERAGE - 2.28)


def test_log_scale_neighbours_become_multipliers_that_chain_to_the_estimate():
    residuals = [0.2, -0.1]
    terms = {"units_last_month": 1.09, "season": 0.07}
    neighbours = [neighbour(r, terms=terms, mean=1.1, multiply=True) for r in residuals]
    estimate = knn_why(*neighbours)["value"]

    why = explain_estimate(knn_why(*neighbours), estimate, field_label="units_sold")

    assert why["form"] == "multiply"
    assert why["base"] == pytest.approx(math.exp(1.1))
    assert why["components"][0]["effect"] == pytest.approx(math.exp(1.09))
    assert why["base"] * math.prod(c["effect"] for c in why["components"]) == pytest.approx(estimate)


def test_neighbours_with_different_field_terms_are_shown_unconverted():
    other = {**FIELD_TERMS, "season": 0.9}
    why = explain_estimate(knn_why(neighbour(1.0), neighbour(1.0, terms=other, weight=2.0)), 30.0,
                           field_label="units_sold")

    # The split into fields + neighbours isn't true here, so no chain is drawn.
    assert why["form"] == "raw" and why["base"] is None
    assert {c["type"] for c in why["components"]} == {"raw"}
    assert {"type": "raw", "label": "Season: spring", "effect": 0.9} in why["components"]


def test_a_neighbour_whose_terms_do_not_give_its_value_raises():
    broken = neighbour(1.0)
    broken["value"]["value"] += 5

    with pytest.raises(AitoError, match="terms give"):
        explain_estimate(knn_why(broken), AVERAGE, field_label="units_sold")


def test_a_why_that_is_not_a_neighbour_average_raises():
    with pytest.raises(AitoError, match="weightedAverage"):
        explain_estimate({"type": "sum", "terms": []}, 3.0, field_label="units_sold")


def test_no_why_means_no_popover():
    assert explain_estimate(None, 3.0, field_label="units_sold") is None
