"""The Aito rankings of the personalised-search benchmark, each held out (ADR 0037 §3).

Every ranking that reads the impressions reads them through a nested
`from` that leaves the scored session out, the pattern of
`scripts/shop_query_sweep.py`: Aito never sees the purchase it is scored
on. `products` holds no session data, so the name search needs no
hold-out, and its answer is shared by every session with the same words.

- **BM25** (Smart Search's left column): `_search products` by
  `$similarity` over the name, the products holding a query word.
- **The Shop's search** (`src/shop_search.py`, as shipped): the products the
  words name, then the grid's `_recommend` restricted to them with the
  household's declared pets, the month and the cart, the household's rule
  as a filter; ranked by `$p` × the text lift. The top 12 get the Shop's
  just-bought re-ask, as the page does.
- **Household only**: the same `$p`, without the text lift.
- **The history form** (Smart Search's right column): one `_search
  impressions get product_sku` ordered by `$multiply [$p, $similarity]`,
  with `context.customer` (the shopper's id) as its `where`.
"""

from __future__ import annotations

from src.aito_client import AitoClient
from src.search_service import PersonaContext, predictive_blend_body
from src.shop_context import rule_filter, shopper_where
from src.shop_ranking import _p_true
from src.personalised_search.sessions import Session, load_products
from src.shop_search import RESULTS, _name_matches


def held_out(session_id: str) -> dict:
    """The impressions without this session's rows, as a nested `from`."""
    return {"from": "impressions", "where": {"$not": {"context": session_id}}}


_text_lift_cache: dict[str, dict[str, float]] = {}


def text_lift(client: AitoClient, query: str) -> dict[str, float]:
    """{sku: exp(θ·bm25)} for the products whose name holds a query word (the Shop's step 1)."""
    if query not in _text_lift_cache:
        _text_lift_cache[query] = _name_matches(client, query)
    return _text_lift_cache[query]


def bm25_ranking(client: AitoClient, session: Session) -> list[str]:
    """Smart Search's left column: the name matches by `$similarity`, ties by SKU."""
    lift = text_lift(client, session.query)
    return sorted(lift, key=lambda sku: (-lift[sku], sku))


def shop_context(session: Session) -> dict:
    """The Shop's `where` context for this session: declared pets, month, cart."""
    products = load_products()
    return shopper_where(session.pets, [products[s] for s in session.cart], session.month)


def shop_where(session: Session, candidates: list[str]) -> dict:
    """`ShopScope.where(only=candidates)` for a session instead of a persona."""
    where = {**shop_context(session), "just_bought": False}
    if (keeps_rule := rule_filter(session.rule)) is not None:
        where.update(keeps_rule)
    where["product_sku"] = {"$or": [s for s in candidates if s not in session.cart]}
    return where


def shop_search_p(client: AitoClient, session: Session, candidates: list[str]) -> dict[str, float]:
    """The Shop's step 2, held out: {sku: $p} over the candidates the rule and cart allow."""
    allowed = [s for s in candidates if s not in session.cart]
    if not allowed:
        return {}
    hits = client.recommend(held_out(session.session_id), shop_where(session, allowed), "product_sku",
                            {"purchased": True}, select=["sku", "$p"], limit=len(allowed))["hits"]
    return {h["sku"]: float(h["$p"]) for h in hits}


def shop_search_ranking(client: AitoClient, session: Session, p: dict[str, float]) -> list[str]:
    """`search_shop`'s order: by $p × text lift; the top 12 re-ranked after the just-bought re-ask."""
    lift = text_lift(client, session.query)
    ranked = sorted(p, key=lambda sku: (-p[sku] * lift[sku], sku))
    top, rest = ranked[:RESULTS], ranked[RESULTS:]
    p_now = dict(p)
    just = [sku for sku in top if sku in session.last_order]
    if just:
        context = shop_context(session)
        answers = client.batch([
            {"from": held_out(session.session_id), "where": {**context, "product_sku": sku, "just_bought": True},
             "predict": "purchased"}
            for sku in just])
        p_now.update({sku: _p_true(a, sku) for sku, a in zip(just, answers)})
    return sorted(top, key=lambda sku: (-p_now[sku] * lift[sku], sku)) + rest


def household_only_ranking(p: dict[str, float]) -> list[str]:
    """The Shop search's $p alone: how much the household explains without the text lift."""
    return sorted(p, key=lambda sku: (-p[sku], sku))


def history_form_ranking(client: AitoClient, session: Session, depth: int) -> list[str]:
    """Smart Search's right column for this shopper, held out, over the whole catalogue."""
    body = predictive_blend_body(session.query, PersonaContext(session.customer, session.customer, ""), depth)
    res = client.search(held_out(session.session_id), get=body["get"], where=body["where"],
                        order_by=body["orderBy"], select=["sku"], limit=depth)
    return [h["sku"] for h in res["hits"]]
