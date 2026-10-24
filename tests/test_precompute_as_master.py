"""`./do precompute --as master`: compute on the release env, file as master.

A release's snapshots are computed before the cutover, on the release
env, but served after it from `master`, which by then holds the same
rows (ADR 0035). So the snapshots are written under master's namespace:
the committed JSON in `data/precomputed/v2-master/`, the Aito rows keyed
`v2@master|<view>` in the release env's `precompute_entries` (the promote
carries that table onto master).
"""

from __future__ import annotations

import json

import pytest

from src import precompute
from src import precompute_store as store
from src.config import Config


class FakeReleaseEnv:
    """An Aito client on env `observable` that records its writes."""

    def __init__(self):
        self._config = Config(aito_api_url="https://example.aito.app", aito_api_key="k",
                              public_demo=False, use_v2=True, aito_env="observable")
        self.inserted: list[dict] = []

    def check_connectivity(self):
        return True

    def get_schema(self):
        return {"schema": {store.PRECOMPUTE_TABLE: {}}}

    def _request(self, method, path, json=None):
        if path == f"/data/{store.PRECOMPUTE_TABLE}":
            self.inserted.append(json)
        return {}


@pytest.fixture(autouse=True)
def _one_view_and_a_tmp_bootstrap_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_FALLBACK_DIR", tmp_path)
    monkeypatch.setattr(precompute, "PRECOMPUTED_ENDPOINTS", [("churn", lambda c: {"at_risk": 42})])
    store._l1.clear()
    yield
    store._l1.clear()
    store.set_namespace(None)


def test_precompute_as_master_files_the_release_envs_snapshot_under_master(tmp_path):
    client = FakeReleaseEnv()

    precompute.precompute_all(client, verbose=False, write_as_env="master")

    snapshot = json.loads((tmp_path / "v2-master" / "churn.json").read_text())
    assert snapshot["data"] == {"at_risk": 42}
    assert [row["name"] for row in client.inserted] == ["v2@master|churn"]
    assert not (tmp_path / "v2-observable").exists()


def test_precompute_without_as_files_under_the_env_it_computed_on(tmp_path):
    client = FakeReleaseEnv()

    precompute.precompute_all(client, verbose=False)

    assert (tmp_path / "v2-observable" / "churn.json").is_file()
    assert [row["name"] for row in client.inserted] == ["v2@observable|churn"]
