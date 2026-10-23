"""Scoring, slicing and splitting in the reorder backtest (ADR 0036).

Read top to bottom, these show what the backtest measures: hit@1 on the
buyer's next order, recall@10 beside its ceiling, three slices by prior
orders, paired 95 % intervals, and the cutoff rule for a merchant's data.
"""

from __future__ import annotations

import pytest

from src.backtest_baselines import EASE, PersonalRepeat, Popularity
from src.backtest_dataset import BacktestDataset, HeldOutOrder, TrainOrder
from src.backtest_metrics import (
    AITO, hit_at_1, mean_interval, recall_at_10, recall_ceiling, slice_of, slice_results,
)
from src.backtest_split import cutoff_date, split_orders
from src.uci_tables import Invoice

# ── Per buyer ─────────────────────────────────────────────────────


def test_hit_at_1_asks_only_whether_the_top_code_was_in_the_next_order():
    assert hit_at_1(["A", "B"], frozenset({"A"})) == 1.0
    assert hit_at_1(["B", "A"], frozenset({"A"})) == 0.0     # second place earns nothing
    assert hit_at_1([], frozenset({"A"})) == 0.0


def test_recall_at_10_is_capped_by_the_basket_size_and_the_ceiling_shows_by_how_much():
    ordered = frozenset(f"C{i}" for i in range(20))          # a 20-code wholesale order
    ranked = [f"C{i}" for i in range(10)]                     # a perfect list

    assert recall_at_10(ranked, ordered) == 0.5
    assert recall_ceiling(ordered) == 0.5                     # the most any 10-slot list can reach


@pytest.mark.parametrize("prior, expected", [(0, "0"), (1, "1–2"), (2, "1–2"), (3, "3+"), (40, "3+")])
def test_buyers_are_sliced_by_their_orders_before_the_cutoff(prior, expected):
    assert slice_of(prior) == expected


# ── Intervals and the best baseline ───────────────────────────────


def test_an_interval_is_the_mean_plus_minus_1_96_standard_errors():
    interval = mean_interval([1.0, 0.0] * 50)                 # p = 0.5, n = 100

    assert interval.mean == 0.5
    assert interval.high - interval.mean == pytest.approx(1.96 * (0.25 * 100 / 99 / 100) ** 0.5)


def test_one_buyer_has_no_interval_and_comparing_it_with_zero_fails_loudly():
    with pytest.raises(ValueError):
        mean_interval([1.0]).spans_zero()


def rankings_for(tops: dict[str, list[str]], customers: list[str]) -> dict[str, dict[str, list[str]]]:
    """Each method recommends one code to every buyer."""
    return {method: dict(zip(customers, ([code] for code in codes))) for method, codes in tops.items()}


def test_every_slice_is_reported_even_an_empty_one_and_the_best_baseline_is_per_slice():
    customers = ["a", "b", "c", "d"]
    test_codes = {c: frozenset({"X"}) for c in customers}
    prior = {"a": 1, "b": 2, "c": 5, "d": 6}                  # nobody new: the 0 slice is empty
    rankings = rankings_for({
        AITO:              ["X", "X", "Y", "Y"],
        "popularity":      ["Y", "Y", "Y", "Y"],
        "personal repeat": ["Y", "Y", "X", "X"],
        "EASE":            ["X", "Y", "Y", "Y"],
    }, customers)

    zero, few, many = slice_results(rankings, test_codes, prior)

    assert (zero.name, zero.buyers, zero.best_baseline) == ("0", 0, None)
    assert few.best_baseline == "EASE" and many.best_baseline == "personal repeat"
    # Aito − best, buyer by buyer: (1-1, 1-0) in 1–2 and (0-1, 0-1) in 3+.
    assert few.aito_minus_best.mean == 0.5 and many.aito_minus_best.mean == -1.0


def test_tied_baselines_name_the_simplest_so_a_fallback_is_called_popularity():
    customers = ["a", "b"]
    rankings = rankings_for({"popularity": ["X", "Y"], "personal repeat": ["X", "Y"], "EASE": ["X", "Y"]},
                            customers)

    (zero, _, _) = slice_results(rankings, {c: frozenset({"X"}) for c in customers}, {"a": 0, "b": 0})

    assert zero.best_baseline == "popularity"


# ── The baselines, as copied from the benchmark ──────────────────


def fit_inputs():
    meta = {"o1": ("u1", "2011-01"), "o2": ("u2", "2011-02"), "o3": ("u1", "2011-03")}
    basket = {"o1": ("A", "B"), "o2": ("B", "C"), "o3": ("C", "D")}
    return ["o1", "o2", "o3"], meta, basket


def test_popularity_breaks_equal_counts_by_first_seen():
    model = Popularity().fit(*fit_inputs())

    assert model.recommend("anyone", [], 4) == ["B", "C", "A", "D"]   # B, C twice; then A before D


def test_personal_repeat_weighs_recent_months_more_and_fills_from_popularity():
    fit_ids, meta, basket = fit_inputs()
    model = PersonalRepeat(6).fit(fit_ids, meta, basket)
    history = [("2011-01", ("A", "B"), "o1"), ("2011-03", ("C", "D"), "o3")]

    assert model.recommend("u1", history, 5) == ["C", "D", "A", "B"]   # March before January; codes alike tie by code


def test_ease_falls_back_to_popularity_for_a_buyer_with_no_history():
    model = EASE(250).fit(*fit_inputs())

    assert model.recommend("new", [], 2) == ["B", "C"]


# ── The split of a merchant's orders ─────────────────────────────


def test_the_cutoff_is_the_first_of_the_month_holding_the_75th_percentile_order():
    dates = ["2024-01-10", "2024-02-03", "2024-03-15", "2024-03-20", "2024-04-02",
             "2024-05-09", "2024-06-30", "2024-07-01"]     # 8 orders: the 6th is the 75th percentile

    assert cutoff_date(dates) == "2024-05-01"


def test_test_is_each_buyers_first_order_on_or_after_the_cutoff_and_train_is_everything_before():
    invoices = {i.invoice: i for i in [
        Invoice("#1001", "u1", "2024-04-30", frozenset({"A"})),
        Invoice("#1003", "u1", "2024-05-02", frozenset({"B"})),
        Invoice("#1002", "u1", "2024-05-02", frozenset({"C"})),     # same day: the lower id is first
        Invoice("#1004", "u1", "2024-06-01", frozenset({"D"})),
        Invoice("#1005", "u2", "2024-05-10", frozenset({"A"})),     # new after the cutoff
    ]}

    dataset = split_orders("shop", "test", invoices, "2024-05-01", {}, {})

    assert dataset.train == [TrainOrder("#1001", "u1", "2024-04", ("A",))]
    assert dataset.test_orders == {"u1": HeldOutOrder("#1002", "2024-05-02", frozenset({"C"})),
                                   "u2": HeldOutOrder("#1005", "2024-05-10", frozenset({"A"}))}
    assert dataset.prior_orders() == {"u1": 1, "u2": 0}


def test_a_dataset_with_no_scored_buyer_refuses():
    with pytest.raises(ValueError, match="no buyer"):
        BacktestDataset("shop", "test", "2024-05-01", [TrainOrder("#1", "u1", "2024-04", ("A",))], {})
