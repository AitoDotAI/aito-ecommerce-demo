"""The Experiments route serves the stored evidence, and the evidence says what the page needs."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.experiments_routes import router

app = FastAPI()
app.include_router(router)
KINDS = {"offer", "title", "image"}


def body() -> dict:
    return TestClient(app).get("/api/experiments").json()


def test_every_experiment_has_a_status_and_a_drafts_arms_have_no_showings_and_no_verdict():
    experiments = body()["experiments"]
    assert len(experiments) == 12 and {e["status"] for e in experiments} == {"draft", "running", "decided"}
    for e in experiments:
        assert e["kind"] in KINDS and len(e["arms"]) == 2 and e["arms"][0]["is_control"] and not e["arms"][1]["is_control"]
        if e["status"] == "draft":
            assert e["verdict"] is None and all(a["showings"] == 0 for a in e["arms"])
        else:
            assert e["verdict"] in {"second arm better", "control better", "no clear difference"} and e["difference"]["interval"][0] <= e["difference"]["delta"]


def test_an_offer_arm_has_a_lower_margin_per_sale_than_the_list_price_and_a_title_arm_the_same():
    for e in body()["experiments"]:
        control, second = e["arms"]
        assert (second["margin_eur"] < control["margin_eur"]) == (e["kind"] == "offer")


def test_each_kind_says_whether_choosing_per_person_pays_with_an_interval_and_what_a_perfect_signal_would_earn():
    per_person = body()["per_person"]
    assert set(per_person) == KINDS
    for kind, result in per_person.items():
        assert result["verdict"] in {"choose per person", "small gain", "keep the plain winner"}
        low, high = result["interval_percent"]
        assert low <= result["gain_percent"] <= high
        assert result["ceiling_gain_percent"] >= result["gain_percent"], kind
        assert result["levels"] and result["held_out_month"] == body()["held_out_month"]


def test_the_plan_route_answers_for_a_running_experiment_and_refuses_a_draft_and_a_bad_split():
    client = TestClient(app)
    running = next(e for e in body()["experiments"] if e["status"] == "running")["experiment_id"]
    draft = next(e for e in body()["experiments"] if e["status"] == "draft")["experiment_id"]
    ok = client.get(f"/api/experiments/{running}/plan", params={"allocation": 0.3, "floor": 0.1, "guardrail": 10})
    assert ok.status_code == 200 and {"testing", "decided", "all_control", "months_to_clear", "guardrail"} <= set(ok.json())
    assert client.get(f"/api/experiments/{draft}/plan").status_code == 400
    assert client.get(f"/api/experiments/{running}/plan", params={"allocation": 1.5}).status_code == 400
    assert client.get("/api/experiments/EXP-99/plan").status_code == 404
