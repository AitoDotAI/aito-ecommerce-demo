"""`scripts/next_basket_eval.py`: does a customer's history predict their next basket (ADR 0027).

A fake Aito holds four customers with three orders each. One declared no pets, so its row has no
`pets` key, as on release 3b where the column is nullable. The script runs end to end against it.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "next_basket_eval.py"


@pytest.fixture
def next_basket_eval():
    spec = importlib.util.spec_from_file_location("next_basket_eval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CUSTOMERS = [
    {"customer_id": "C1", "pets": "dog"},
    {"customer_id": "C2", "pets": "dog"},
    {"customer_id": "C3", "pets": "cat dog"},
    {"customer_id": "C4"},                      # declared no pets: the key is absent
]
ORDERS = [{"order_id": f"{c}-O{i}", "customer_id": c, "month": f"2026-0{i}"}
          for c in ("C1", "C2", "C3", "C4") for i in (1, 2, 3)]
LINES = [{"order_id": o["order_id"], "product_sku": "SKU-A" if o["order_id"].endswith(("O1", "O3")) else "SKU-B"}
         for o in ORDERS]


class FakeAito:
    def __init__(self):
        self.predict_bodies: list[dict] = []
        self._config = SimpleNamespace(aito_env="test")

    def search(self, table, limit=10, offset=0, **_):
        rows = {"orders": ORDERS, "order_lines": LINES, "customers": CUSTOMERS}[table]
        return {"hits": rows[offset:offset + limit]}

    def _request(self, method, path, json=None):
        assert (method, path) == ("POST", "/_predict")
        self.predict_bodies.append(json)
        return {"hits": [{"feature": "SKU-A"}, {"feature": "SKU-B"}]}


@pytest.fixture
def run(next_basket_eval, monkeypatch, capsys):
    fake = FakeAito()
    monkeypatch.setattr(next_basket_eval, "AitoClient", lambda config: fake)
    monkeypatch.setattr(next_basket_eval, "load_config", lambda: SimpleNamespace(aito_env="test"))
    next_basket_eval.main()
    return fake, capsys.readouterr().out


def test_a_customer_with_no_declared_pets_is_scored_not_a_crash(run):
    fake, output = run

    assert "model (own history)" in output
    assert len(fake.predict_bodies) == 8, "four customers, the model and the control each"


def test_the_model_never_reads_any_held_out_last_order_like_the_popularity_baseline(run):
    fake, _ = run
    held_out = {"C1-O3", "C2-O3", "C3-O3", "C4-O3"}

    for body in fake.predict_bodies:
        excluded = body["from"]["where"]["$not"]["order_id"]["$or"]
        assert set(excluded) == held_out, "the model's population must leave out every held-out order"


def test_households_with_the_same_pets_are_one_group_whatever_the_order(next_basket_eval):
    assert next_basket_eval.household_group({"pets": "dog cat"}) == next_basket_eval.household_group({"pets": "cat dog"})


def test_a_household_that_declared_no_pets_is_its_own_named_group(next_basket_eval):
    assert next_basket_eval.household_group({"customer_id": "C4"}) == next_basket_eval.NO_DECLARED_PETS
    assert next_basket_eval.household_group({"pets": None}) == next_basket_eval.NO_DECLARED_PETS
