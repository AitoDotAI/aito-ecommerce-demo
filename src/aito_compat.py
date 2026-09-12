"""Normalise API v2 (Rep2) responses back to v1 field names — ADR 0025.

The app is written against v1's vocabulary. Pointing it at v2 without
this layer does not raise: both versions answer `200`, so a renamed key
surfaces as `None` at the point of use, which is silent and arrives as a
blank cell in the UI rather than an error. Hence one normalisation at
the transport chokepoint, and none in the service modules.

Two rules keep this honest:

  * **Additive.** Aliases are *added*; the v2 key is never deleted. A
    reader that already speaks v2 keeps working, and nothing is
    discarded on the way through (CLAUDE.md prime directive #2).
  * **Structural.** Shapes are detected by looking at the payload (does
    it carry a `{kind, data}` envelope?), never by matching on the
    endpoint name — endpoint-name branching rots the moment a new route
    returns an existing shape.

Ported from aito-demo's `src/aito-compat.js`, whose transforms were
measured against a live v2 env (`docs/rep2-migration.md`).
"""

from __future__ import annotations

from typing import Any

from src.schema import SCHEMAS

# `select` entries v2 rejects with a 400. Nothing in this demo reads
# them; if that changes, the drop must become a real port, not a silent
# omission.
_V2_UNSUPPORTED_SELECT = ("$matches",)


def adapt_request(path: str, body: Any, *, use_v2: bool) -> Any:
    """Rewrite a v1-shaped request body into one v2 accepts.

    Version-gated, unlike `normalize_response`: the replacements are not
    valid on v1, so this must only run when actually talking to v2.
    Returns the body unchanged on v1.
    """
    if not use_v2 or not isinstance(body, dict):
        return body

    adapted = dict(body)

    # v1 asks for a non-exclusive prediction with `exclusiveness: false`;
    # v2 400s on that and spells it as a `$feature` sub-selector on the
    # predicted field instead.
    if adapted.pop("exclusiveness", None) is False:
        predict = adapted.get("predict")
        if isinstance(predict, str) and not predict.endswith(".$feature"):
            adapted["predict"] = f"{predict}.$feature"

    # v1 expands a link column automatically: `_recommend product_sku`
    # returns every column of `products` flattened onto the hit
    # (`name`, `pet_type`, ...). v2 returns only `{$p, $value}` — the
    # bare id — so every caller reading `hit["name"]` gets None while
    # the query still answers 200. The capability is not missing, only
    # the default: an explicit `select` returns the same columns. So
    # reconstruct v1's implicit default here, and nowhere else, rather
    # than teaching each service about v2 (ADR 0025).
    if "select" not in adapted:
        linked = _linked_columns(adapted.get("from"), adapted.get("recommend") or adapted.get("predict"))
        if linked:
            adapted["select"] = ["$p", "$value", *linked]

    # v2 wants `relate` as a list of fields. The array form is accepted by
    # BOTH versions, so this is safe to send either way.
    relate = adapted.get("relate")
    if isinstance(relate, str):
        adapted["relate"] = [relate]

    select = adapted.get("select")
    if isinstance(select, list):
        kept = [s for s in select if s not in _V2_UNSUPPORTED_SELECT]
        if len(kept) != len(select):
            adapted["select"] = kept

    return adapted


def normalize_response(payload: Any, *, request_body: Any = None) -> Any:
    """Alias a v2 response onto v1's vocabulary.

    Safe to apply unconditionally: every transform is guarded on the v2
    shape actually being present, so a v1 payload passes through
    untouched.
    """
    payload = _unwrap_envelope(payload)
    if not isinstance(payload, dict):
        return payload

    hits = payload.get("hits")
    if isinstance(hits, list):
        predicted_field = None
        if isinstance(request_body, dict):
            predict = request_body.get("predict")
            if isinstance(predict, str):
                # Undo the `.$feature` suffix adapt_request may have added,
                # so `field` reads the same on both versions.
                predicted_field = predict.removesuffix(".$feature")
        for hit in hits:
            _normalize_hit(hit, predicted_field)

    return payload


def _unwrap_envelope(payload: Any) -> Any:
    """v2 wraps some results as `{"kind": ..., "data": ...}`.

    Detected structurally — an envelope is a two-key dict with exactly
    `kind` and `data` — so it applies wherever v2 uses it
    (`_aggregate`, `_estimate`, `_evaluate`) without naming endpoints.
    """
    if (
        isinstance(payload, dict)
        and set(payload.keys()) == {"kind", "data"}
        and isinstance(payload.get("kind"), str)
    ):
        return payload["data"]
    return payload


def _normalize_hit(hit: Any, predicted_field: str | None) -> None:
    """Add v1 aliases to one hit, in place. Never removes a v2 key."""
    if not isinstance(hit, dict):
        return

    # v2 renamed the predicted value `feature` -> `$value`.
    if "feature" not in hit and "$value" in hit:
        hit["feature"] = hit["$value"]

    # v2 drops `field` from prediction hits; restore it from the request
    # so callers that group by field keep working.
    if "field" not in hit and predicted_field:
        hit["field"] = predicted_field

    # `_relate`'s `related` is `{"$has": v}` on v1 but sometimes a bare
    # value on v2. Wrap so readers can index it uniformly.
    related = hit.get("related")
    if related is not None and not isinstance(related, (dict, list)):
        hit["related"] = {"$has": related}


def _linked_columns(from_table: Any, field: Any) -> list[str]:
    """Columns of the table `from_table.field` links to, or [] if it is
    not a link.

    Read from the declared schema rather than fetched from Aito: the link
    graph is already the demo's source of truth, and a per-query schema
    round-trip would add latency to exactly the call this exists to fix.
    """
    if not isinstance(from_table, str) or not isinstance(field, str):
        return []
    # `predict` may carry the v2 `.$feature` suffix adapt_request adds.
    field = field.removesuffix(".$feature")
    column = SCHEMAS.get(from_table, {}).get("columns", {}).get(field, {})
    link = column.get("link") if isinstance(column, dict) else None
    if not isinstance(link, str) or "." not in link:
        return []
    linked_table = link.split(".", 1)[0]
    return sorted(SCHEMAS.get(linked_table, {}).get("columns", {}))
