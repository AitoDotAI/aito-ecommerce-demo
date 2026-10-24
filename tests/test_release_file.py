"""The release file: the data a build was made for (ADR 0035).

`data/release-env.json` names the release env and the row count of each
table. These tests show how the counts are read from Aito (one `_search`
with `limit: 0` per table), how a file is validated, and how a
difference is reported. Offline: Aito is faked with `pytest-httpx`.
"""

from __future__ import annotations

import json

import pytest
from pytest_httpx import HTTPXMock

from src.aito_client import AitoClient
from src.config import Config
from src.release_file import (
    RELEASE_FILE,
    Release,
    ReleaseFileError,
    differences,
    load_release,
    read_counts,
    write_release,
)

BASE = "https://example.aito.app/env/observable/api/v2"


@pytest.fixture
def observable_client() -> AitoClient:
    return AitoClient(Config(
        aito_api_url="https://example.aito.app",
        aito_api_key="test-key",
        public_demo=False,
        use_v2=True,
        aito_env="observable",
    ))


# ── Reading the counts from Aito ──────────────────────────────────


def test_read_counts_counts_every_data_table_with_a_limit_zero_search(observable_client, httpx_mock: HTTPXMock):
    # The schema lists the env's tables; the two cache tables change while
    # the app runs, so they are not part of a release and are not counted.
    httpx_mock.add_response(url=f"{BASE}/schema", method="GET", json={"schema": {
        "customers": {}, "orders": {}, "prediction_cache": {}, "precompute_entries": {},
    }})
    httpx_mock.add_response(url=f"{BASE}/_search", method="POST",
                            match_json={"from": "customers", "limit": 0, "offset": 0},
                            json={"hits": [], "offset": 0, "total": 3000})
    httpx_mock.add_response(url=f"{BASE}/_search", method="POST",
                            match_json={"from": "orders", "limit": 0, "offset": 0},
                            json={"hits": [], "offset": 0, "total": 11909})

    assert read_counts(observable_client) == {"customers": 3000, "orders": 11909}


# ── Comparing ─────────────────────────────────────────────────────


def test_differences_is_empty_when_the_data_is_the_release():
    assert differences({"orders": 11909}, {"orders": 11909}) == []


def test_differences_names_each_table_that_differs():
    release = {"orders": 11909, "contexts": 12662}
    live = {"orders": 11919, "price_history": 15792}

    assert differences(release, live) == [
        "contexts: missing (release has 12662 rows)",
        "orders: 11919 rows, release has 11909",
        "price_history: not in the release (15792 rows)",
    ]


# ── The file ──────────────────────────────────────────────────────


def test_a_written_release_reads_back_the_same(tmp_path):
    path = tmp_path / "release-env.json"
    release = Release(env="observable", counts={"orders": 11909, "customers": 3000})

    write_release(release, path)

    assert load_release(path) == release
    # Sorted, so a regenerated file diffs only where a count changed.
    assert list(json.loads(path.read_text())["counts"]) == ["customers", "orders"]


def test_the_committed_release_file_is_valid():
    release = load_release(RELEASE_FILE)
    assert release.env
    assert "orders" in release.counts


@pytest.mark.parametrize("content, reason", [
    ("not json", "not valid JSON"),
    ('{"env": "observable"}', "exactly 'env' and 'counts'"),
    ('{"env": "observable", "counts": {}, "extra": 1}', "exactly 'env' and 'counts'"),
    ('{"env": "", "counts": {"orders": 1}}', "'env' must be a non-empty string"),
    ('{"env": "observable", "counts": {}}', "'counts' must be a non-empty object"),
    ('{"env": "observable", "counts": {"orders": "11909"}}', "count of 'orders'"),
    ('{"env": "observable", "counts": {"orders": true}}', "count of 'orders'"),
    ('{"env": "observable", "counts": {"orders": -1}}', "count of 'orders'"),
    ('{"env": "observable", "counts": {"prediction_cache": 3}}', "change while the app runs"),
])
def test_a_malformed_release_file_fails_loudly(tmp_path, content, reason):
    path = tmp_path / "release-env.json"
    path.write_text(content)

    with pytest.raises(ReleaseFileError, match=reason):
        load_release(path)


def test_a_missing_release_file_says_how_to_write_one(tmp_path):
    with pytest.raises(ReleaseFileError, match=r"\./do release-file <env>"):
        load_release(tmp_path / "release-env.json")
