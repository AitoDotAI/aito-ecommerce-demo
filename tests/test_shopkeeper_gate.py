"""The gate's rules (ADR 0052), one per test: what makes the agent act, ask a person, or stay quiet."""

import pytest

from src.shopkeeper_gate import ACT, NEVER_AUTO, QUIET, SUGGEST, GateSettings, decide


def judge(action="ad", lift=0.18, net=20.0, rows=30, settings=GateSettings()):
    return decide(action, action.title(), lift, net, rows, settings).outcome


def test_a_confident_lift_on_enough_rows_is_acted_on():
    assert judge(lift=0.18, rows=30) == ACT


def test_a_lift_between_the_bars_is_suggested_to_a_person():
    assert judge(lift=0.10) == SUGGEST


def test_a_lift_below_the_lower_bar_stays_quiet():
    assert judge(lift=0.03) == QUIET


def test_thin_evidence_stays_quiet_however_large_the_lift():
    assert judge(lift=0.40, rows=5) == QUIET


def test_enough_rows_is_the_minimum_itself_and_above():
    assert judge(rows=10) == ACT and judge(rows=9) == QUIET


def test_a_kind_the_store_always_asks_about_is_never_acted_on_whatever_the_lift():
    assert judge(action="voucher", lift=0.40) == NEVER_AUTO


def test_thin_evidence_wins_over_the_never_auto_kind():
    """Nothing is queued for a person to approve when the agent has no evidence to put in front of them."""
    assert judge(action="voucher", lift=0.40, rows=2) == QUIET


def test_an_action_that_does_not_pay_for_itself_stays_quiet():
    assert judge(lift=0.40, net=-0.5) == QUIET


def test_no_action_is_always_quiet():
    assert judge(action="none") == QUIET


def test_the_store_can_take_a_kind_off_the_never_auto_list():
    settings = GateSettings(never_auto=frozenset())

    assert judge(action="voucher", lift=0.40, settings=settings) == ACT


def test_moving_the_bar_moves_the_outcome():
    assert judge(lift=0.18, settings=GateSettings(act_lift=0.25)) == SUGGEST


def test_every_decision_says_why():
    assert "30 rows" in decide("ad", "Ad", 0.18, 20.0, 30, GateSettings()).reason


@pytest.mark.parametrize("act,suggest,rows", [(0.05, 0.15, 10), (1.5, 0.1, 10), (0.15, -0.1, 10), (0.15, 0.05, -1)])
def test_settings_that_make_no_sense_are_refused(act, suggest, rows):
    with pytest.raises(ValueError):
        GateSettings(act_lift=act, suggest_lift=suggest, min_rows=rows)
