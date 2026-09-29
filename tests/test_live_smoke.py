"""The live smoke's content checks (scripts/live_smoke.py), offline.

The failing shapes are what ecommerce.aito.ai served on 29.9 (before #37 was
deployed and precompute re-run).
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "live_smoke", Path(__file__).resolve().parents[1] / "scripts" / "live_smoke.py")
smoke = importlib.util.module_from_spec(_spec)
sys.modules["live_smoke"] = smoke          # @dataclass looks its module up here
_spec.loader.exec_module(smoke)


def _model(id_, verdict, error=None, n=200, acc=0.85, base=0.4):
    return {"id": id_, "verdict": verdict, "error": error, "n": n, "accuracy": acc, "base_accuracy": base}


def test_evaluation_passes_with_the_headline_model_passing_and_return_risk_failing():
    body = {"models": [_model("pet_type_from_name", "pass"), _model("return_risk", "fail", acc=0.975, base=0.975)]}
    assert "pet_type_from_name 0.85 vs 0.4" in smoke.check_evaluation(body)


def test_evaluation_fails_on_the_stale_snapshot():
    # 29.9: testSource {limit: 200} made pet type read 0.06 vs 0.0, verdict fail
    body = {"models": [_model("pet_type_from_name", "fail", acc=0.06, base=0.0)],
            "last_run": "2026-09-23T04:28:11+00:00"}
    with pytest.raises(AssertionError, match="stale snapshot"):
        smoke.check_evaluation(body)


def test_evaluation_fails_on_an_errored_model():
    body = {"models": [_model("pet_type_from_name", "pass"), _model("dietary_from_name", "pass", error="400")]}
    with pytest.raises(AssertionError, match="errored"):
        smoke.check_evaluation(body)


def test_an_empty_driver_list_fails_churn():
    check = next(s.check for s in smoke.STEPS if s.name == "churn")
    with pytest.raises(AssertionError, match="drivers"):
        check({"at_risk": [{"customer_id": "c1"}], "drivers": []})
    assert "1 drivers" in check({"at_risk": [{"customer_id": "c1"}], "drivers": [{"factor": "x"}]})


def test_price_does_not_require_sweet_spots():
    # empty sweet_spots is legitimate (#37: support >= 30 and a 95% interval)
    check = next(s.check for s in smoke.STEPS if s.name == "price")
    assert "fair_bands" in check({"fair_bands": [{"sku": "S"}], "sweet_spots": []})


def test_every_step_is_a_get():
    assert all(not hasattr(s, "body") or s.body is None for s in smoke.STEPS)
