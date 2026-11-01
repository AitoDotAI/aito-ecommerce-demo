"""The stock routine (ADR 0057): a rule over the Supply snapshot, with a gate of its own. It orders nothing."""

import json

import pytest

from src.shopkeeper_gate import ACT, NEVER_AUTO, QUIET, SUGGEST
from src.shopkeeper_run import release_env
from src.shopkeeper_stock import SUPPLY_SNAPSHOT, StockSettings, build_stock_run, decide_stock_steps, load_stock_run, tally_stock


def reorder(sku="S1", stock=2, point=30, units=40, qty=20, cost=100.0, risk=150.0) -> dict:
    return {"sku": sku, "name": f"Product {sku}", "category": "dry-food", "supplier": "S-1", "lead_time_days": 7, "current_stock": stock,
            "reorder_point": point, "recent_units": units, "order_qty": qty, "order_cost_eur": cost, "revenue_at_risk_eur": risk}


def overstock(sku="O1", action="markdown") -> dict:
    return {"sku": sku, "name": f"Product {sku}", "category": "toys", "current_stock": 40, "reorder_point": 3, "excess_units": 30, "unit_cost_eur": 10.0,
            "tied_capital_eur": 300.0, "markdown": {"action": action, "discount_pct": 15, "price_eur": 12.0, "weeks_to_clear": 9.0, "units_cleared": 25,
                                                      "capital_freed_eur": 250.0, "margin_given_up_eur": 20.0}}


def snapshot(reorders=(), overstocks=()) -> dict:
    return {"planning_month": "2026-05", "reorder_queue": list(reorders), "overstock": list(overstocks)}


def judged(step_rows, settings=StockSettings()):
    run = build_stock_run(snapshot(*step_rows), "release3b")
    return decide_stock_steps(run, settings)


def test_a_reorder_with_sales_behind_it_inside_the_limit_and_nearly_out_of_stock_is_acted_on():
    [step] = judged(([reorder(stock=2, point=30)], []))

    assert step["outcome"] == ACT and "40 units" in step["reason"]


def test_a_reorder_that_is_not_yet_urgent_is_suggested():
    [step] = judged(([reorder(stock=25, point=30)], []))

    assert step["outcome"] == SUGGEST


def test_an_order_above_the_limit_always_needs_a_person_however_good_the_evidence():
    [step] = judged(([reorder(units=500, cost=900.0)], []))

    assert step["outcome"] == NEVER_AUTO and "500" in step["reason"]


def test_a_product_with_too_few_observed_sales_stays_quiet_even_when_it_is_out_of_stock():
    [step] = judged(([reorder(stock=0, units=2)], []))

    assert step["outcome"] == QUIET and "2 units" in step["reason"] and "5" in step["reason"]


def test_a_markdown_that_clears_the_excess_is_suggested_and_one_that_would_not_is_left_alone():
    marked, kept, hold = judged(([], [overstock("O1", "markdown"), overstock("O2", "wont_clear"), overstock("O3", "hold")]))

    assert marked["outcome"] == SUGGEST and "15 %" in marked["reason"]
    assert kept["outcome"] == QUIET and "would not clear" in kept["reason"]
    assert hold["outcome"] == QUIET and "hold" in hold["reason"].lower()


def test_the_settings_move_the_outcomes_without_rebuilding_the_run():
    run = build_stock_run(snapshot([reorder(units=8, cost=300.0)], []), "release3b")

    assert decide_stock_steps(run, StockSettings())[0]["outcome"] == ACT
    assert decide_stock_steps(run, StockSettings(min_recent_units=10))[0]["outcome"] == QUIET
    assert decide_stock_steps(run, StockSettings(order_limit_eur=200.0))[0]["outcome"] == NEVER_AUTO


def test_settings_that_make_no_sense_are_refused():
    with pytest.raises(ValueError, match="urgent_share"):
        StockSettings(urgent_share=1.5)
    with pytest.raises(ValueError, match="order_limit"):
        StockSettings(order_limit_eur=-1)


def test_the_tally_counts_steps_and_what_each_group_would_order_and_protect():
    decided = judged(([reorder("A", cost=100.0, risk=150.0), reorder("B", stock=25, cost=50.0, risk=80.0)], []))

    tally = tally_stock(decided)

    assert tally[ACT] == {"steps": 1, "order_cost_eur": 100.0, "revenue_at_risk_eur": 150.0}
    assert tally[SUGGEST]["steps"] == 1 and tally[QUIET]["steps"] == 0


def test_the_stored_run_is_what_the_supply_snapshot_builds_today():
    """Regenerate with ./do agent-runs when the snapshot changes."""
    snap = json.loads(SUPPLY_SNAPSHOT.read_text())["data"]

    assert build_stock_run(snap, release_env()) == load_stock_run()


def test_the_run_says_it_is_simulated_and_where_its_numbers_come_from():
    run = load_stock_run()

    assert run["simulated"] is True and "supply.json" in run["source"] and run["routine"] == "stock"


def api():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.shopkeeper_routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_the_stock_run_is_served_judged_under_the_settings_the_request_names():
    default = api().get("/api/shopkeeper/runs/stock").json()
    strict = api().get("/api/shopkeeper/runs/stock", params={"min_recent_units": 1000}).json()

    assert default["tally"][ACT]["steps"] == 45 and default["tally"][SUGGEST]["steps"] + default["tally"][NEVER_AUTO]["steps"] > 0
    assert strict["tally"][ACT]["steps"] == 0
    assert default["settings"]["recommended"] == {"min_recent_units": 5, "order_limit_eur": 500.0, "urgent_share": 0.5}


def test_the_overview_lists_the_stock_run_and_its_routine_as_built():
    body = api().get("/api/shopkeeper").json()

    assert {r["id"]: r["built"] for r in body["routines"]}["stock"] is True
    assert next(r for r in body["runs"] if r["id"] == "stock")["routine"] == "stock"
    assert body["board"] and all(item["raised_by"] == "winback" for item in body["board"]), "the Board still holds the win-back's findings only"


def test_a_setting_that_makes_no_sense_is_a_400():
    assert api().get("/api/shopkeeper/runs/stock", params={"urgent_share": 3}).status_code == 400
