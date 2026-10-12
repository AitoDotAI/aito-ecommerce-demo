"""Price what-if (ADR 0029): set a price, get next month's units, revenue,
profit and the factors behind the estimate.

With `model: "regression"`, Aito's `_estimate` explains itself as
`exp(mean + Σ factors)`, so the waterfall's rows multiply out to the
estimate exactly. The `why` below is the shape shared.aito.ai returned for
SKU-PT-0133 at €4.68 on 2026-10-12 (values rounded).
"""

import math

import pytest

from src.aito_client import AitoError
from src.lookup_errors import UnknownProductError
from src.price_what_if import get_price_what_if, waterfall

SKU = "SKU-PT-0133"
TERMS = {
    "price_eur": -0.7279, "season": 0.068, "brand": 0.00105, "category": -0.0764,
    "pet_type": -0.098, "units_last_month": 1.0906, "product_sku": 0.4069,
}
MEAN = 1.0995
ESTIMATE = math.exp(MEAN + sum(TERMS.values()))
WHERE = {"product_sku": SKU, "units_last_month": 23, "pet_type": "dog", "category": "wet-food",
         "brand": "Hill's Science Plan", "season": "spring", "price_eur": 4.68}


def regression_why(terms=TERMS, mean=MEAN, residual=0.0) -> dict:
    return {
        "type": "exponent",
        "base": {"type": "constant", "value": math.e},
        "power": {"type": "sum", "terms": [
            {"type": "input", "name": "residual", "value": residual},
            *[{"type": "regression", "proposition": {field: WHERE[field]}, "value": value}
              for field, value in terms.items()],
            {"type": "mean centering", "name": "mean", "value": mean},
        ]},
    }


class FakeClient:
    def __init__(self, why=None, products=None):
        self.why = why if why is not None else regression_why()
        self.products = products if products is not None else [
            {"sku": SKU, "name": "Lamb Dog Food 400g", "pet_type": "dog", "category": "wet-food",
             "brand": "Hill's Science Plan"}]
        self.estimates: list[dict] = []

    def search(self, table, *, where, limit=10, **_):
        if table == "products":
            return {"hits": [p for p in self.products if p["sku"] == where["sku"]]}
        if table == "inventory":
            return {"hits": [{"sku": SKU, "unit_cost_eur": 3.12}]}
        assert table == "monthly_sales"
        return {"hits": [{"month": "2026-04", "units_sold": 23, "pet_type": "dog", "category": "wet-food",
                          "brand": "Hill's Science Plan"}]}

    def estimate(self, table, where, estimate_field, *, model=None, with_why=True):
        self.estimates.append({"from": table, "where": where, "estimate": estimate_field, "model": model})
        return {"estimate": ESTIMATE, "why": self.why}


def test_the_factors_multiply_out_to_the_estimate():
    base, factors = waterfall(regression_why(), ESTIMATE)

    assert base == pytest.approx(math.exp(MEAN))
    assert base * math.prod(f.multiplier for f in factors) == pytest.approx(ESTIMATE)


def test_factors_that_change_less_than_half_a_percent_fold_into_one_row():
    # brand is ×1.001: shown alone it would read "+0.1 %", which looks like
    # evidence and isn't.
    _, factors = waterfall(regression_why(), ESTIMATE)

    assert "brand" not in [f.field for f in factors]
    assert factors[-1].field == "other"


def test_the_price_factor_is_labelled_with_the_price_asked_about():
    _, factors = waterfall(regression_why(), ESTIMATE)
    price = next(f for f in factors if f.field == "price_eur")

    assert price.label == "Price €4.68"
    assert price.multiplier == pytest.approx(math.exp(-0.7279))


def test_a_why_that_does_not_multiply_out_to_the_estimate_raises():
    with pytest.raises(AitoError, match="does not multiply out"):
        waterfall(regression_why(), ESTIMATE * 1.5)


def test_a_why_in_another_shape_raises_instead_of_drawing_a_wrong_chart():
    knn_shaped = {"type": "weightedAverage", "components": []}

    with pytest.raises(AitoError, match="unexpected"):
        waterfall(knn_shaped, ESTIMATE)


def test_what_if_asks_the_regression_model_at_the_chosen_price_and_adds_up_profit():
    client = FakeClient()

    result = get_price_what_if(client, SKU, 4.68)

    [asked] = client.estimates
    assert asked["model"] == "regression"
    assert asked["where"] == WHERE
    assert result.units == pytest.approx(ESTIMATE, abs=0.01)
    assert result.revenue_eur == pytest.approx(4.68 * result.units, abs=0.01)
    assert result.profit_eur == pytest.approx((4.68 - 3.12) * result.units, abs=0.01)


def test_an_unknown_sku_raises():
    with pytest.raises(UnknownProductError, match="SKU-NO-SUCH"):
        get_price_what_if(FakeClient(), "SKU-NO-SUCH", 4.0)


def test_a_price_that_is_not_positive_is_refused():
    with pytest.raises(ValueError, match="positive"):
        get_price_what_if(FakeClient(), SKU, 0)
