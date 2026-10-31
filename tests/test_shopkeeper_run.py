"""The stored win-back run (ADR 0052): it says what the retention snapshot says, and it is recomputable."""

import json
from collections import Counter

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.shopkeeper_board import board_for
from src.shopkeeper_gate import ACT, NEVER_AUTO, QUIET, SUGGEST, GateSettings
from src.shopkeeper_routes import router
from src.shopkeeper_run import (RETENTION_SNAPSHOT, build_winback_run, decide_steps, load_run, release_env,
                                rows_by_situation, tally)


@pytest.fixture(scope="module")
def run():
    return load_run("winback")


def test_the_stored_run_is_what_the_retention_snapshot_builds_today():
    """Regenerate with scripts/generate_agent_runs.py when the snapshot changes."""
    snapshot = json.loads(RETENTION_SNAPSHOT.read_text())["data"]

    assert build_winback_run(snapshot, rows_by_situation(), release_env()) == load_run("winback")


def test_the_stored_run_belongs_to_the_data_release_the_app_serves(run):
    assert run["release"] == release_env()


def test_every_step_is_a_customer_retention_lists_with_the_action_retention_ranks_first(run):
    snapshot = json.loads(RETENTION_SNAPSHOT.read_text())["data"]
    listed = {c["customer_id"]: c["actions"]["options"][0] for c in snapshot["at_risk"]}

    assert {s["customer_id"] for s in run["steps"]} == set(listed)
    for step in run["steps"]:
        assert step["best"]["label"] == listed[step["customer_id"]]["label"]
        assert step["best"]["net_vs_none_eur"] == listed[step["customer_id"]]["net_vs_none_eur"]


def test_the_run_is_labelled_simulated(run):
    assert run["simulated"] is True


def test_the_headline_euros_are_the_sum_of_the_steps_that_made_each_group(run):
    decided = decide_steps(run, GateSettings())
    summary = tally(decided)

    for outcome in (ACT, SUGGEST, NEVER_AUTO):
        expected = round(sum(s["best"]["net_vs_none_eur"] for s in decided if s["outcome"] == outcome), 2)
        assert summary[outcome]["expected_net_eur"] == expected
    assert sum(g["steps"] for g in summary.values()) == len(run["steps"])


def test_the_recommended_settings_give_the_run_every_outcome_but_suggest_on_the_stored_customers(run):
    outcomes = Counter(s["outcome"] for s in decide_steps(run, GateSettings()))

    assert outcomes[ACT] > 0 and outcomes[NEVER_AUTO] > 0 and outcomes[QUIET] > 0, outcomes


def test_a_step_with_no_rows_of_its_action_in_its_situation_stays_quiet(run):
    decided = decide_steps(run, GateSettings())

    for step in decided:
        if step["rows"] < GateSettings().min_rows:
            assert step["outcome"] == QUIET, step["customer_id"]


def test_the_board_names_the_thin_evidence_and_what_to_do_about_it(run):
    kinds = {item["kind"] for item in board_for(run, GateSettings())}

    assert {"evidence", "approval", "root_cause"} <= kinds


def test_the_board_no_longer_lists_an_approval_load_when_nothing_needs_a_person(run):
    settings = GateSettings(never_auto=frozenset())

    assert "approval" not in {item["kind"] for item in board_for(run, settings)}


def test_a_stored_run_never_names_a_prospect_or_a_price_list(run):
    text = json.dumps(run).lower()

    for word in ("ambientia", "mycashflow", "cartman", "matkahuolto"):
        assert word not in text


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_the_overview_lists_board_routines_and_conversations(api):
    body = api.get("/api/shopkeeper").json()

    assert body["board"] and body["simulated"] is True
    assert [c["id"] for c in body["conversations"]] == ["winback"]
    assert {r["id"]: r["built"] for r in body["routines"]}["winback"] is True
    assert body["settings"]["in_force"] == body["settings"]["recommended"]


def test_a_run_is_judged_under_the_thresholds_the_request_names(api):
    default = api.get("/api/shopkeeper/runs/winback").json()["tally"]
    strict = api.get("/api/shopkeeper/runs/winback", params={"act_lift": 0.9, "suggest_lift": 0.9}).json()["tally"]

    assert strict[ACT]["steps"] < default[ACT]["steps"]
    assert strict[ACT]["steps"] == 0


def test_an_empty_never_auto_list_lets_the_agent_act_on_every_kind(api):
    body = api.get("/api/shopkeeper/runs/winback", params={"never_auto": ""}).json()

    assert body["tally"][NEVER_AUTO]["steps"] == 0


def test_nonsense_thresholds_answer_400(api):
    assert api.get("/api/shopkeeper/runs/winback", params={"act_lift": 0.01, "suggest_lift": 0.5}).status_code == 400


def test_an_unknown_run_answers_404(api):
    assert api.get("/api/shopkeeper/runs/nope").status_code == 404


def test_the_demo_script_says_what_the_stored_run_says_at_the_recommended_settings(run):
    from pathlib import Path
    summary = tally(decide_steps(run, GateSettings()))
    script = (Path(__file__).resolve().parent.parent / "docs" / "demo-script.md").read_text()
    section = script.split("## 5b. The shopkeeper agent")[1].split("## 6.")[0]

    acted = f"I acted on {summary[ACT]['steps']}, expecting € {summary[ACT]['expected_net_eur']:.0f}"
    waiting = summary[SUGGEST]["steps"] + summary[NEVER_AUTO]["steps"]
    waiting_eur = summary[SUGGEST]["expected_net_eur"] + summary[NEVER_AUTO]["expected_net_eur"]

    assert acted in section
    assert f"{waiting} are waiting for you, holding € {waiting_eur:.0f} expected" in section
    assert f"I stayed quiet on {summary[QUIET]['steps']}" in section
