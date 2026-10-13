"""Shop analytics, baskets: category pairs bought together more or less
often than chance (ADR 0031).

The order-level co-occurrence query Basket Rules mines (ADR 0022), one
per anchor category:

    {"from": "orders", "where": {"line_categories": {"$match": "dog_dryfood"}},
     "relate": "line_categories"}

Product-level pairs (`orders.skus`) are left out: each pair shares only
3–8 orders (ADR 0031 findings).

A customer's orders repeat their basket, so orders are clustered by
customer, and how much depends on the anchor: one design effect per
anchor, from the share of each customer's orders that hold it
(`src/design_effect.py`). A + B and B + A have the same lift and count
once, from the anchor mined first.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.aito_compat import related_value
from src.basket_rules_service import MINED_ANCHORS, category_token, decode_token, humanise
from src.design_effect import customer_bodies, design_effect, rows_per_customer
from src.lift_rows import Candidate, Significance, judge, relate_hits
from src.shop_analytics_service import WINDOW_MONTHS
from src.timing import submit_in_request

# Above the number of category tokens (28 on 2026-10-13): a full page raises.
TOKEN_LIMIT = 100


@dataclass(frozen=True)
class BasketPair:
    first: str              # "Dog dry-food", the anchor
    second: str             # "Dog dental-treats"
    lift: float
    interval_low: float
    interval_high: float
    orders_with_both: int   # fOnCondition
    orders_with_first: int  # fCondition


@dataclass
class BasketSection:
    pairs: list[BasketPair]       # strongest first
    design_effects: dict[str, float]   # per anchor label
    significance: Significance
    queries_sent: int
    example_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def basket_body(anchor: tuple[str, str]) -> dict:
    return {"from": "orders", "where": {"line_categories": {"$match": category_token(*anchor)}},
            "relate": "line_categories", "limit": TOKEN_LIMIT}


def _candidates(anchor: tuple[str, str], hits: list[dict], deff: float) -> list[Candidate]:
    """One candidate per other token, labelled first = anchor, value = the other category."""
    anchor_token, first = category_token(*anchor), humanise(*anchor)
    out = []
    for hit in hits:
        token = related_value(hit, "line_categories")
        if token == anchor_token:
            continue   # the anchor itself: every order in the condition has it
        decoded = decode_token(token)
        if decoded is None:
            raise AitoError(f"line_categories token {token!r} is not <pet>_<category>")
        out.append(Candidate(first, humanise(*decoded), float(hit["lift"]), hit["fs"], deff))
    return out


def get_basket_section(client: AitoClient) -> BasketSection:
    pair_bodies = [basket_body(a) for a in MINED_ANCHORS]
    everyone_body, _ = customer_bodies("orders", "customer_id", {"month": {"$or": WINDOW_MONTHS}}, {})
    anchor_bodies = [{**everyone_body, "where": b["where"]} for b in pair_bodies]

    with ThreadPoolExecutor(max_workers=8) as pool:
        def submit(body):
            return submit_in_request(pool, relate_hits, client, body)

        pair_jobs = [submit(b) for b in pair_bodies]
        anchor_jobs = [submit(b) for b in anchor_bodies]
        everyone_hits = submit(everyone_body).result()
        pair_hits = [j.result() for j in pair_jobs]
        anchor_hits = [j.result() for j in anchor_jobs]

    everyone = rows_per_customer(everyone_hits, "customer_id")
    if sum(everyone.values()) != everyone_hits[0]["fs"]["n"]:
        raise AitoError(f"orders: the window's months cover {sum(everyone.values())} of {everyone_hits[0]['fs']['n']} orders")

    seen: set[frozenset] = set()
    candidates: list[Candidate] = []
    deffs: dict[str, float] = {}
    for anchor, hits, customers in zip(MINED_ANCHORS, pair_hits, anchor_hits):
        deff = design_effect(everyone, rows_per_customer(customers, "customer_id")).design_effect
        deffs[humanise(*anchor)] = deff
        for c in _candidates(anchor, hits, deff):
            if frozenset((c.field, c.value)) not in seen:
                seen.add(frozenset((c.field, c.value)))
                candidates.append(c)

    rows, significance = judge(candidates)
    pairs = [BasketPair(r.field, r.value, r.lift, r.interval_low, r.interval_high,
                        r.rows_with_value, r.condition_rows) for r in rows]
    return BasketSection(
        pairs=sorted(pairs, key=lambda p: p.lift, reverse=True), design_effects=deffs,
        significance=significance, queries_sent=len(pair_bodies) + len(anchor_bodies) + 1,
        example_query={"endpoint": "_relate", "body": pair_bodies[0]},
    )
