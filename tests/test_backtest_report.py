"""The backtest report's wording rules (ADR 0036), one test per rule.

The rules: an interval for Aito − best baseline that spans 0 is "a tie";
the 0-prior-orders slice is "a fallback" when Aito equals popularity; no
sentence claims a win outside a slice whose interval excludes 0; a slice
under 30 buyers is "too few to read".
"""

from __future__ import annotations

import pytest

from src.backtest_dataset import BacktestDataset, HeldOutOrder, TrainOrder
from src.backtest_metrics import AITO, Interval, SliceResult
from src.backtest_report import render_report
from src.backtest_run import BacktestRun, ExampleBuyer
from src.backtest_wording import WIN_CLAIMS, Verdict, slice_sentence, verdict


def point(mean: float) -> Interval:
    return Interval(mean, mean - 0.03, mean + 0.03)


def a_slice(name="1–2", buyers=636, aito=0.31, best=0.15, diff=(0.16, 0.12, 0.20)):
    """A slice result whose best baseline is EASE, with Aito − EASE = diff (mean, low, high)."""
    hit1 = {AITO: point(aito), "popularity": point(best), "personal repeat": point(best), "EASE": point(best)}
    return SliceResult(name, buyers, hit1, {m: 0.1 for m in hit1}, 0.57, "EASE", Interval(*diff))


def test_an_interval_that_spans_zero_is_reported_as_a_tie():
    result = a_slice(name="3+", buyers=1708, aito=0.412, best=0.424, diff=(-0.012, -0.033, 0.008))

    assert verdict(result) is Verdict.TIE
    assert "a tie" in slice_sentence(result)


def test_an_interval_that_touches_zero_is_still_a_tie():
    assert verdict(a_slice(diff=(0.02, 0.0, 0.04))) is Verdict.TIE


def test_only_an_interval_that_excludes_zero_may_claim_a_win():
    win = a_slice(diff=(0.16, 0.12, 0.20))

    assert verdict(win) is Verdict.AITO_AHEAD
    assert slice_sentence(win).startswith("1–2 prior orders: Aito ahead of EASE")


@pytest.mark.parametrize("result", [
    a_slice(diff=(-0.05, -0.08, -0.02)),                                   # a loss
    a_slice(diff=(0.01, -0.02, 0.04)),                                     # a tie
    a_slice(buyers=12, diff=(0.30, 0.05, 0.55)),                           # excludes 0, but 12 buyers
    a_slice(name="0", buyers=630, aito=0.0587, best=0.0587, diff=(0.0, 0.0, 0.0)),
])
def test_no_other_slice_says_aito_wins(result):
    sentence = slice_sentence(result)

    assert not any(claim in sentence for claim in WIN_CLAIMS), sentence


def test_the_no_history_slice_is_a_fallback_when_aito_equals_popularity():
    result = a_slice(name="0", buyers=630, aito=0.0587, best=0.0587, diff=(0.0, 0.0, 0.0))

    assert verdict(result) is Verdict.FALLBACK
    assert "Aito equals popularity here" in slice_sentence(result)


def test_the_fallback_wording_needs_equal_point_estimates():
    result = a_slice(name="0", buyers=630, aito=0.07, best=0.0587, diff=(0.011, -0.01, 0.03))

    assert verdict(result) is Verdict.TIE


def test_a_slice_under_30_buyers_is_too_few_to_read_even_with_a_clear_interval():
    result = a_slice(buyers=29, diff=(0.30, 0.10, 0.50))

    assert verdict(result) is Verdict.TOO_FEW
    assert "too few to read" in slice_sentence(result)


def test_a_small_slice_is_too_few_to_read_even_when_aito_was_not_run():
    result = a_slice(buyers=13)
    offline = SliceResult(result.name, 13, {m: i for m, i in result.hit1.items() if m != AITO},
                          result.recall10, 0.57, "EASE", None)

    assert verdict(offline) is Verdict.TOO_FEW


def a_run(aito_ran: bool) -> BacktestRun:
    dataset = BacktestDataset("acme", "Shopify orders export orders_export.csv", "2024-05-01",
                              [TrainOrder("#1001", "c1", "2024-04", ("S1",))],
                              {"c1": HeldOutOrder("#1002", "2024-05-03", frozenset({"S1"}))},
                              {"cancelled order": 3}, {"code from Lineitem name (no SKU)": 2})
    slices = [a_slice(name="0", buyers=0), a_slice(), a_slice(name="3+", diff=(-0.01, -0.03, 0.01))]
    if not aito_ran:
        slices = [SliceResult(s.name, s.buyers, {m: i for m, i in s.hit1.items() if m != AITO},
                              s.recall10, s.recall10_ceiling, s.best_baseline, None) for s in slices]
    slices[0] = SliceResult("0", 0, {}, {}, 0.0, None, None)
    examples = [ExampleBuyer("c1", 1, "S1", "base 1.0%; ×9.00 when invoice.customer_id is c1; p 9.0%",
                             ["S1"], True)] if aito_ran else []
    return BacktestRun(dataset, slices, examples, aito_ran)


def test_the_report_shows_the_cutoff_dropped_rows_all_three_slices_and_the_best_baseline():
    report = render_report(a_run(aito_ran=True))

    assert "**Cutoff:** 2024-05-01" in report
    assert "cancelled order 3" in report and "code from Lineitem name (no SKU) 2" in report
    for label in ("0 prior orders", "1–2 prior orders", "3+ prior orders"):
        assert f"| {label} |" in report
    assert "| EASE | +0.1600 [+0.1200, +0.2000] | Aito ahead |" in report
    assert "3+ prior orders: a tie." in report
    assert "0 prior orders: no buyers in this slice." in report
    assert "×9.00 when invoice.customer_id is c1" in report


def test_an_offline_report_has_no_aito_column_and_says_aito_was_not_run():
    report = render_report(a_run(aito_ran=False))

    assert "| Aito |" not in report and "not run (offline)" in report
    assert not any(claim in report for claim in WIN_CLAIMS)
