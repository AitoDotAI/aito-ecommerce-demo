"""Every number the README, the UI copy and the demo script state, looked up where it comes from.

`docs/verification/claims-checklist.md` lists each claim with its source and release. This file is the
offline half of that list: a claim is read from the page, its source is read from a committed file or a
constant in `src/`, and they must agree. A number that drifts, or a sentence that is edited so the number is no
longer found, fails here. `tests/test_claims_live.py` is the half that needs a running Aito.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.markdown_proposal import DISCOUNT_LEVELS_PCT, HORIZON_WEEKS
from src.price_bands import MIN_SWEET_SPOT_SUPPORT
from src.product_funnel import AD_SPEND_EUR
from src.sandbox_envs import MAX_AGE
from src.lift_rows import FAMILY_CONFIDENCE
from src.shop_rescore import RESCORED

ROOT = Path(__file__).resolve().parents[1]


def page(path: str) -> str:
    """A file's text with whitespace collapsed, so a claim that wraps across lines is still found."""
    text = (ROOT / path).read_text(encoding="utf-8")
    text = re.sub(r'"\s*\+\s*"', "", text)       # a string literal split across lines: "…the " + "time…"
    return re.sub(r"\s+", " ", text)


def says(path: str, text: str) -> bool:
    return text in page(path)


# ── README ───────────────────────────────────────────────────────────────


def test_readme_row_counts_are_the_releases():
    counts = json.loads((ROOT / "data" / "release-env.json").read_text(encoding="utf-8"))["counts"]
    ranked, unranked = counts["impressions"], counts["unranked_showings"]
    expected = (f"{counts['products']:,} products, {counts['customers']:,} customers, {counts['orders']:,} orders, "
                f"{counts['order_lines']:,} order lines, {ranked + unranked:,} impressions ({ranked:,} ranked and "
                f"{unranked:,} unranked showings), {counts['product_states']:,} product states, "
                f"{counts['reviews']:,} reviews, {counts['customer_actions']:,} recorded actions")

    assert says("README.md", expected), f"README does not say: {expected}"


def test_readmes_version_example_names_the_env_a_promoted_release_serves():
    """After a promote the app reads `master` (ADR 0035); prod's `GET /api/version` answers `v2@master`."""
    assert says("README.md", '`"api": "v2@master"`')


def test_readme_sandbox_branch_lives_as_long_as_the_code_lets_it():
    hours = int(MAX_AGE.total_seconds() // 3600)

    assert says("README.md", f"deleted after {hours} hours")


def test_readme_names_the_month_a_lever_writes():
    assert says("README.md", "next month's state** (May 2026)")


def test_readme_says_how_many_cards_the_sandbox_shop_re_scores():
    assert says("README.md", f"top {RESCORED} by Aito's shop-wide lifts")


# ── The real-data claim: README, the Evidence copy, the demo script and ADR 0034 ──────────────

# The benchmark's counts, pinned by tests/test_backtest_uci_reproduction.py (hits in the 1–2 slice, n = 636)
# and by the live uci-check (Aito's 197 of 636).
UCI_BUYERS, UCI_AITO_HITS, UCI_EASE_HITS = 636, 197, 98
UCI_CLAIM = ("For buyers with 1–2 earlier orders, Aito's top suggestion was in their next orders "
             "31 % of the time, against 15 % for the strongest of five classical baselines.")


def test_the_uci_claim_is_what_its_counts_round_to():
    assert round(UCI_AITO_HITS / UCI_BUYERS * 100) == 31
    assert round(UCI_EASE_HITS / UCI_BUYERS * 100) == 15


@pytest.mark.parametrize("path", ["README.md", "frontend/components/business-reorders/ClaimBox.tsx",
                                  "docs/adr/0034-business-reorders-on-real-data.md"])
def test_the_uci_claim_is_worded_the_same_wherever_it_is_quoted(path):
    assert says(path, UCI_CLAIM), path


def test_the_demo_scripts_uci_row_gives_the_same_counts():
    assert says("docs/demo-script.md", f"31 %: {UCI_AITO_HITS} of {UCI_BUYERS} buyers")
    assert says("docs/demo-script.md", "15 %: EASE, 15.4 %")


# ── UI copy against the constants it describes ───────────────────────────


def test_supply_says_the_markdown_range_and_horizon_the_code_tests():
    low, high = min(p for p in DISCOUNT_LEVELS_PCT if p > 0), max(DISCOUNT_LEVELS_PCT)

    assert says("frontend/app/supply/page.tsx", f"Markdowns are tested at {low}–{high} % off")
    assert says("frontend/app/supply/page.tsx", f"a quarter ({HORIZON_WEEKS} weeks)")
    assert says("frontend/app/supply/page.tsx", f"even at {high} % off")


def test_the_lift_panel_says_the_support_and_confidence_it_requires():
    assert says("frontend/lib/panel-content.ts", f"rests on {MIN_SWEET_SPOT_SUPPORT} or more")
    assert says("frontend/lib/panel-content.ts", f"excludes 1 at {round(FAMILY_CONFIDENCE * 100)} %")


# ── The demo script's Supply section against the release's snapshot ─────────────


@pytest.fixture(scope="module")
def supply() -> dict:
    return json.loads((ROOT / "data" / "precomputed" / "v2-master" / "supply.json").read_text(encoding="utf-8"))["data"]


def test_the_demo_scripts_supply_headline_numbers_are_the_snapshots(supply):
    reorder, overstock = supply["reorder"], supply["overstock_decision"]

    assert says("docs/demo-script.md", f"Reorder these {reorder['skus']} now")
    assert says("docs/demo-script.md", f"if May sells like the last three months, about €{reorder['revenue_at_risk_eur']:,.0f} of its sales")
    assert says("docs/demo-script.md", f"{reorder['units']:,} units, €{reorder['order_cost_eur']:,.0f} at cost")
    assert says("docs/demo-script.md", f"€{overstock['tied_capital_eur']:,.0f} tied up in {overstock['skus']} overstocked products")
    assert says("docs/demo-script.md", f"{overstock['wont_clear']} won't clear")


def test_the_demo_scripts_check_first_line_agrees_with_its_own_table(supply):
    """The pre-flight tells the presenter which number to expect. It once named release 3a's."""
    assert says("docs/demo-script.md", f"the page shows {supply['reorder']['units']} units")


def test_the_demo_script_quotes_the_recovery_rate_the_report_gives():
    assert says("docs/verification/action-recovery.md", "81 % of customers")
    assert says("docs/demo-script.md", "the generator's best for 81 % of customers")


def test_the_demo_scripts_advertising_assumptions_are_the_funnels():
    search, banner = AD_SPEND_EUR["search"], AD_SPEND_EUR["banner"]

    assert AD_SPEND_EUR["none"] == 0
    assert says("docs/demo-script.md", f"(none, search €{search:.0f}, banner €{banner:.0f} a month)")


def test_the_held_out_calibration_figure_says_which_release_it_was_measured_on():
    """The 6 % came from release 2 (117,026 impressions). Release 3b has fewer, so the figure must say it is not 3b's."""
    assert says("docs/demo-script.md", "within 6 % of what shoppers then did")
    assert says("docs/demo-script.md", "measured on release 2 data and has not been re-run on release 3b")


# ── The Supply page's claim about the forecast against the simple rule ──────────


def test_the_supply_card_names_the_baseline_the_forecast_test_uses_and_says_what_the_snapshot_shows():
    """The card once said the forecast 'tied' a last-three-months rule; the test compares ranges against last month's."""
    evaluation = json.loads((ROOT / "data" / "precomputed" / "v2-master" / "demand.json").read_text(encoding="utf-8"))["data"]["evaluation"]

    assert evaluation["accuracy"] <= evaluation["naive_accuracy"], "the card says Aito did not beat the simple rule"
    assert says("frontend/app/supply/page.tsx", 'against "the same range as last month"')
    assert says("frontend/app/supply/page.tsx", "It did not beat it")
    assert not says("frontend/app/supply/page.tsx", "It tied")
