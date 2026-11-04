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
