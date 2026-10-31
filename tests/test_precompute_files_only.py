"""`./do precompute --files-only [--only a,b]`: refresh the committed snapshots without writing to the shared Aito.

A change to what a view computes (Supply's reorder quantities moved from a forecast to observed sales) must reach
the git snapshots, and the Overview that quotes Supply must be computed from the new Supply, not the old.
"""

from __future__ import annotations

import json

import pytest

from src import precompute
from src import precompute_store as store
from tests.test_precompute_as_master import FakeReleaseEnv


@pytest.fixture(autouse=True)
def _tmp_bootstrap_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_FALLBACK_DIR", tmp_path)
    store._l1.clear()
    yield
    store._l1.clear()
    store.set_namespace(None)


def _views(seen: list):
    def overview(client):
        seen.append(("overview reads supply", store.get("supply")["data"]))
        return {"headline": "from the new supply"}

    return [("demand", lambda c: {"d": 1}), ("supply", lambda c: {"reorder": "new"}), ("overview", overview)]


def test_the_overview_is_computed_after_the_views_it_quotes_and_reads_their_new_snapshots(monkeypatch):
    seen: list = []
    monkeypatch.setattr(precompute, "PRECOMPUTED_ENDPOINTS", _views(seen))

    precompute.precompute_all(FakeReleaseEnv(), verbose=False, files_only=True)

    assert seen == [("overview reads supply", {"reorder": "new"})]


def test_the_default_order_puts_the_overview_last():
    assert [name for name, _ in precompute.PRECOMPUTED_ENDPOINTS][-1] == "overview"


def test_files_only_writes_the_committed_json_and_nothing_to_aito(tmp_path, monkeypatch):
    monkeypatch.setattr(precompute, "PRECOMPUTED_ENDPOINTS", _views([]))
    client = FakeReleaseEnv()

    precompute.precompute_all(client, verbose=False, files_only=True)

    assert client.inserted == []
    assert json.loads((tmp_path / "v2-observable" / "supply.json").read_text())["data"] == {"reorder": "new"}


def test_only_refreshes_just_the_named_views(tmp_path, monkeypatch):
    monkeypatch.setattr(precompute, "PRECOMPUTED_ENDPOINTS", _views([]))

    precompute.precompute_all(FakeReleaseEnv(), verbose=False, files_only=True, only=("supply",))

    assert sorted(p.stem for p in (tmp_path / "v2-observable").glob("*.json")) == ["supply"]


def test_a_view_name_that_does_not_exist_is_refused(monkeypatch):
    monkeypatch.setattr(precompute, "PRECOMPUTED_ENDPOINTS", _views([]))

    with pytest.raises(ValueError, match="no such view.*nope"):
        precompute.precompute_all(FakeReleaseEnv(), verbose=False, files_only=True, only=("nope",))
