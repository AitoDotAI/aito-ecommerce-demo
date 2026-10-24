"""Supply's price column: a list price against the prices the product sold at.

The band is mean ± 1.5σ of the realised prices (`product_states`). An
outlier is flagged only on enough observations: the old Price view once
opened on an "outlier" whose band came from two sales.
"""

from src.price_bands import MIN_OUTLIER_OBSERVATIONS, price_band


def test_a_list_price_above_what_the_product_usually_sold_at_is_an_outlier():
    band = price_band([3.0, 3.1, 2.9, 3.0, 3.05, 2.95, 3.0, 3.0], list_price=4.0)

    assert band.outlier
    assert band.band_low_eur < band.mean_price_eur < band.band_high_eur < 4.0
    assert band.observations == 8


def test_a_list_price_inside_the_band_is_not_flagged():
    assert not price_band([10.0] * 7 + [9.0], list_price=10.0).outlier


def test_two_sales_are_never_a_band_to_be_outside_of():
    band = price_band([3.0, 3.01], list_price=9.0)

    assert band.observations < MIN_OUTLIER_OBSERVATIONS
    assert not band.outlier
