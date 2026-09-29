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


def _passing_models():
    return [_model(m, "pass") for m in smoke.MUST_PASS]


def test_evaluation_passes_with_every_held_model_passing_and_return_risk_failing():
    body = {"models": _passing_models() + [_model("return_risk", "fail", acc=0.975, base=0.975)]}
    assert "all pass" in smoke.check_evaluation(body)


def test_evaluation_fails_when_a_secondary_model_regresses():
    models = _passing_models()
    models[1]["verdict"] = "fail"
    with pytest.raises(AssertionError, match="dietary_from_name"):
        smoke.check_evaluation({"models": models})


def test_evaluation_fails_on_the_stale_snapshot():
    # 29.9: testSource {limit: 200} made pet type read 0.06 vs 0.0, verdict fail
    models = _passing_models()
    models[0] = _model("pet_type_from_name", "fail", acc=0.06, base=0.0)
    body = {"models": models, "last_run": "2026-09-23T04:28:11+00:00"}
    with pytest.raises(AssertionError, match="Stale snapshot"):
        smoke.check_evaluation(body)


def test_evaluation_fails_on_an_errored_model():
    body = {"models": _passing_models() + [_model("return_risk", "fail", error="400")]}
    with pytest.raises(AssertionError, match="errored"):
        smoke.check_evaluation(body)


def test_an_empty_driver_list_fails_churn():
    check = next(s.check for s in smoke.STEPS if s.name == "churn")
    with pytest.raises(AssertionError, match="drivers"):
        check({"at_risk": [{"customer_id": "c1"}], "drivers": []})
    assert "1 drivers" in check({"at_risk": [{"customer_id": "c1"}], "drivers": [{"factor": "x"}]})


def test_hidden_views_are_checked_for_shape_not_content():
    # ADR 0027: demand/winback/markdown/price/cart-completion are hidden; empty is fine
    for name, body in [("demand", {"top_movers": [], "seasonality": []}),
                       ("price", {"fair_bands": [], "sweet_spots": []}),
                       ("winback", {"targets": []})]:
        check = next(s.check for s in smoke.STEPS if s.name == name)
        assert "shape ok" in check(body)
        with pytest.raises(AssertionError):
            check({"error": "boom"})


def test_dashboard_needs_one_available_pattern():
    with pytest.raises(AssertionError, match="unavailable"):
        smoke.check_dashboard({"top_patterns": [{"available": False}], "segments": [{}]})
    assert "1/2" in smoke.check_dashboard(
        {"top_patterns": [{"available": False}, {"available": True}], "segments": [{}]})


def test_every_step_is_a_get(monkeypatch):
    methods = []

    class _Res:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"{}"

    def urlopen(req, timeout):
        methods.append(req.get_method())
        return _Res()
    monkeypatch.setattr(smoke.urllib.request, "urlopen", urlopen)
    for step in smoke.STEPS:
        smoke.fetch("http://x", step, 1)
    assert set(methods) == {"GET"} and len(methods) == len(smoke.STEPS)
