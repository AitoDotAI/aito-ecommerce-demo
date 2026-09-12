"""API v1/v2 toggle + response normalisation — ADR 0025.

These are the tests that make the migration safe to land while the demo
still serves v1: they pin that (a) the toggle rewrites the base path for
every call, and (b) the compat layer is a NO-OP on v1, so shipping it
cannot change what the live demo returns.

Pure functions and config — no Aito calls.
"""

from __future__ import annotations

from src.aito_compat import adapt_request, normalize_response
from src.config import Config


def _cfg(**kw) -> Config:
    base = dict(
        aito_api_url="https://shared.aito.ai/db/aito-ecommerce-demo",
        aito_api_key="k",
        public_demo=False,
    )
    base.update(kw)
    return Config(**base)


# ── The one switch ───────────────────────────────────────────────────


def test_default_base_is_v1_against_master():
    """The live demo's path. `master` is unprefixed."""
    assert _cfg().api_base == "https://shared.aito.ai/db/aito-ecommerce-demo/api/v1"


def test_v2_base_targets_the_v2_env():
    """Named envs take an `/env/<name>` prefix, and the version moves with them."""
    cfg = _cfg(use_v2=True, aito_env="v2")
    assert cfg.api_base == (
        "https://shared.aito.ai/db/aito-ecommerce-demo/env/v2/api/v2"
    )


def test_env_name_is_overridable_for_a_sandbox_env():
    cfg = _cfg(use_v2=True, aito_env="pr-42")
    assert cfg.api_base.endswith("/env/pr-42/api/v2")


# ── Request adaptation is v2-only ────────────────────────────────────


def test_request_is_untouched_on_v1():
    """The guarantee that lets this ship ahead of the migration."""
    body = {"from": "products", "predict": "category", "exclusiveness": False}
    assert adapt_request("/_predict", body, use_v2=False) == body


def test_v2_rewrites_non_exclusive_predict_to_feature_selector():
    """v1's `exclusiveness: false` 400s on v2; it is spelled `field.$feature`."""
    out = adapt_request(
        "/_predict",
        {"from": "products", "predict": "tags", "exclusiveness": False},
        use_v2=True,
    )
    assert out["predict"] == "tags.$feature"
    assert "exclusiveness" not in out


def test_v2_sends_relate_as_an_array():
    out = adapt_request("/_relate", {"from": "o", "relate": "plan"}, use_v2=True)
    assert out["relate"] == ["plan"]


def test_v2_drops_select_entries_it_rejects():
    out = adapt_request(
        "/_search", {"from": "p", "select": ["name", "$matches"]}, use_v2=True
    )
    assert out["select"] == ["name"]


# ── Response normalisation is structural, and additive ───────────────


def test_v1_response_passes_through_unchanged():
    """No-op on v1 — the property that makes this safe to ship now."""
    v1 = {"hits": [{"$p": 0.9, "feature": "dry-food", "field": "category"}]}
    assert normalize_response(v1, request_body={"predict": "category"}) == v1


def test_v2_envelope_is_unwrapped_structurally():
    """`{kind, data}` is detected by shape, not by endpoint name."""
    assert normalize_response({"kind": "aggregate", "data": {"total": 3}}) == {
        "total": 3
    }


def test_a_two_key_dict_that_is_not_an_envelope_is_left_alone():
    payload = {"kind": "x", "data": 1, "extra": True}
    assert normalize_response(payload) == payload


def test_v2_value_is_aliased_to_feature_without_discarding_it():
    out = normalize_response(
        {"hits": [{"$p": 0.9, "$value": "dry-food"}]},
        request_body={"predict": "category"},
    )
    hit = out["hits"][0]
    assert hit["feature"] == "dry-food"
    assert hit["$value"] == "dry-food", "the v2 key must survive — aliases are additive"


def test_missing_field_is_restored_from_the_request():
    out = normalize_response(
        {"hits": [{"$p": 0.9, "$value": "dry-food"}]},
        request_body={"predict": "category"},
    )
    assert out["hits"][0]["field"] == "category"


def test_restored_field_undoes_the_v2_feature_suffix():
    """`adapt_request` may have rewritten `predict`; `field` must still read
    as the plain column name the caller asked about."""
    out = normalize_response(
        {"hits": [{"$p": 0.4, "$value": "x"}]},
        request_body={"predict": "tags.$feature"},
    )
    assert out["hits"][0]["field"] == "tags"


def test_bare_related_value_is_wrapped_like_v1():
    out = normalize_response({"hits": [{"related": "Free", "lift": 1.4}]})
    assert out["hits"][0]["related"] == {"$has": "Free"}


def test_already_wrapped_related_is_left_alone():
    out = normalize_response({"hits": [{"related": {"$has": "Free"}}]})
    assert out["hits"][0]["related"] == {"$has": "Free"}


# ── v2 env staging ───────────────────────────────────────────────────


def test_tables_to_migrate_covers_every_loader_table():
    """Derived from SCHEMAS so a table added to the demo can never be
    silently left behind on the old engine — a half-migrated env answers
    200 for every query while quietly running two different engines."""
    from src.data_loader import SCHEMAS
    from src.v2_env import tables_to_migrate

    assert tables_to_migrate() == sorted(SCHEMAS)
    assert len(tables_to_migrate()) == len(SCHEMAS)


def test_v2_select_reconstructs_v1s_implicit_link_expansion():
    """v1 expands a link column automatically — `_recommend product_sku`
    returns every column of `products` on the hit. v2 returns only
    `{$p, $value}`, so `hit["name"]` is None while the query still
    answers 200. The compat layer restores the v1 default by asking for
    the linked table's columns explicitly."""
    out = adapt_request(
        "/_recommend",
        {"from": "impressions", "recommend": "product_sku", "goal": {"purchased": True}},
        use_v2=True,
    )
    assert out["select"][:2] == ["$p", "$value"]
    for column in ("name", "pet_type", "sku", "brand"):
        assert column in out["select"], column


def test_an_explicit_select_is_never_overridden():
    body = {"from": "impressions", "recommend": "product_sku", "select": ["$p"]}
    assert adapt_request("/_recommend", body, use_v2=True)["select"] == ["$p"]


def test_a_non_link_recommend_target_gets_no_injected_select():
    """Only link columns expanded implicitly on v1, so only they need
    reconstructing — injecting a select elsewhere would silently narrow
    the response."""
    body = {"from": "impressions", "predict": "purchased"}
    assert "select" not in adapt_request("/_predict", body, use_v2=True)


def test_unknown_table_is_not_guessed_at():
    body = {"from": "prediction_cache", "recommend": "cache_key"}
    assert "select" not in adapt_request("/_recommend", body, use_v2=True)
