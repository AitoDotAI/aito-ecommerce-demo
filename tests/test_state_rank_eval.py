"""The pure parts of the product-state evaluation (scripts/state_rank_eval.py)."""

import pytest

from scripts.state_rank_eval import FOLDS, brier_by_exposure, exposure_bucket, fold_of, held_out


def test_a_customer_stays_in_the_same_fold_and_folds_are_in_range():
    assert fold_of("CUST-00152") == fold_of("CUST-00152")
    assert {fold_of(f"CUST-{i:05d}") for i in range(300)} == set(range(FOLDS))


@pytest.mark.parametrize("showings, bucket", [(0, "thin"), (4, "thin"), (5, "mid"), (29, "mid"), (30, "well"), (900, "well")])
def test_a_state_is_thin_mid_or_well_shown_by_its_showings_outside_the_fold(showings, bucket):
    assert exposure_bucket(showings) == bucket


def test_the_held_out_population_is_every_other_fold():
    assert held_out(3) == {"from": "impressions", "where": {"context.fold": {"$not": 3}}}


def test_brier_is_the_mean_squared_error_per_exposure_bucket():
    terms = [("thin", 0.5), ("thin", 0.1), ("well", 0.02)]

    assert brier_by_exposure(terms) == pytest.approx({"thin": 0.3, "well": 0.02})
