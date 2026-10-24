"""Patterns, baskets: category pairs bought together more or less often
than chance, as rules with a direction (ADRs 0022, 0031, 0041).

One order-level co-occurrence `_relate` per anchor category:

    {"from": "orders", "where": {"line_categories": {"$match": "dog_dryfood"}},
     "relate": "line_categories"}

`orders.line_categories` holds one token per (pet type, category) in the
order, `<pet>_<category without hyphens>` (ADR 0008). Each hit's `fs`
gives the whole rule, order-granular (verified live, 2026-10-24: they
match `_search` counts of the same orders):

    fCondition    orders with the anchor A        4,325 dog dry-food
    f             orders with the other token B   3,008 dental treats
    fOnCondition  orders with both                2,911
    n             all orders                     11,909

    confidence A → B = fOnCondition / fCondition   67 %
    confidence B → A = fOnCondition / f            97 %
    support          = fOnCondition / n            24 %

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
from src.design_effect import customer_bodies, design_effect, rows_per_customer
from src.lift_rows import Candidate, LiftRow, Significance, judge, relate_hits
from src.shop_analytics_service import WINDOW_MONTHS
from src.timing import submit_in_request

# The anchors mined: the catalogue's high-volume (pet type, category)
# pairs, so every anchor has the support to yield real pairs. Pairwise
# rules only, not an itemset enumeration (ADR 0022, out of scope).
MINED_ANCHORS: list[tuple[str, str]] = [
    ("dog", "dry-food"), ("dog", "wet-food"), ("dog", "treats"),
    ("dog", "dental-treats"), ("dog", "accessories"),
    ("cat", "dry-food"), ("cat", "wet-food"), ("cat", "litter"),
    ("cat", "treats"),
    ("aquarium", "aquarium"),
]
# Above the number of category tokens (28 on 2026-10-13): a full page raises.
TOKEN_LIMIT = 100

_CATEGORIES = ("dry-food", "wet-food", "treats", "dental-treats", "litter",
               "accessories", "health", "grooming", "toys", "aquarium")
_HYPHENATED = {c.replace("-", ""): c for c in _CATEGORIES}


def category_token(pet_type: str, category: str) -> str:
    """`("dog", "dry-food")` → `"dog_dryfood"`."""
    return f"{pet_type}_{category.replace('-', '')}"


def decode_token(token: str) -> tuple[str, str] | None:
    """`"dog_dryfood"` → `("dog", "dry-food")`. Splits on the last `_`,
    because `small_animal` carries one."""
    pet, _, clean_category = token.rpartition("_")
    if not clean_category:
        return None
    return pet, _HYPHENATED.get(clean_category, clean_category)


def humanise(pet_type: str, category: str) -> str:
    if pet_type == "aquarium" and category == "aquarium":
        return "Aquarium products"
    label_pet = "Aquarium" if pet_type == "aquarium" else pet_type.replace("_", " ").capitalize()
    return f"{label_pet} {category}"


@dataclass(frozen=True)
class BasketPair:
    first: str                  # "Dog dry-food", the anchor
    second: str                 # "Dog dental-treats"
    first_id: str               # "dog_dryfood", the token
    second_id: str              # "dog_dentaltreats"
    lift: float
    interval_low: float
    interval_high: float
    orders_with_both: int       # fOnCondition
    orders_with_first: int      # fCondition
    orders_with_second: int     # f
    orders: int                 # n
    confidence: float           # first → second: orders_with_both / orders_with_first
    reverse_confidence: float   # second → first: orders_with_both / orders_with_second
    support: float              # orders_with_both / orders


@dataclass
class BasketSection:
    pairs: list[BasketPair]            # strongest first
    anchors: list[dict]                # [{id: token, label}], the anchor filter's options
    design_effects: dict[str, float]   # per anchor label
    significance: Significance
    queries_sent: int
    example_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def basket_body(anchor: tuple[str, str]) -> dict:
    return {"from": "orders", "where": {"line_categories": {"$match": category_token(*anchor)}},
            "relate": "line_categories", "limit": TOKEN_LIMIT}


def _candidates(anchor: tuple[str, str], hits: list[dict], deff: float) -> list[tuple[Candidate, str]]:
    """One candidate per other token (field = the anchor's label, value =
    the other category's), with that token."""
    anchor_token, first = category_token(*anchor), humanise(*anchor)
    out = []
    for hit in hits:
        token = related_value(hit, "line_categories")
        if token == anchor_token:
            continue   # the anchor itself: every order in the condition has it
        decoded = decode_token(token)
        if decoded is None:
            raise AitoError(f"line_categories token {token!r} is not <pet>_<category>")
        out.append((Candidate(first, humanise(*decoded), float(hit["lift"]), hit["fs"], deff), token))
    return out


def _pair(row: LiftRow, first_id: str, second_id: str, fs: dict) -> BasketPair:
    both, first, second, orders = (int(fs[k]) for k in ("fOnCondition", "fCondition", "f", "n"))
    return BasketPair(
        first=row.field, second=row.value, first_id=first_id, second_id=second_id,
        lift=row.lift, interval_low=row.interval_low, interval_high=row.interval_high,
        orders_with_both=both, orders_with_first=first, orders_with_second=second, orders=orders,
        confidence=round(both / first, 3), reverse_confidence=round(both / second, 3),
        support=round(both / orders, 3),
    )


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

    candidates: dict[frozenset, tuple[Candidate, tuple[str, str]]] = {}   # one per unordered pair
    deffs: dict[str, float] = {}
    for anchor, hits, customers in zip(MINED_ANCHORS, pair_hits, anchor_hits):
        deff = design_effect(everyone, rows_per_customer(customers, "customer_id")).design_effect
        deffs[humanise(*anchor)] = deff
        for c, token in _candidates(anchor, hits, deff):
            candidates.setdefault(frozenset((c.field, c.value)), (c, (category_token(*anchor), token)))

    rows, significance = judge([c for c, _ in candidates.values()])
    pairs = []
    for row in rows:
        candidate, (first_id, second_id) = candidates[frozenset((row.field, row.value))]
        pairs.append(_pair(row, first_id, second_id, candidate.fs))
    return BasketSection(
        pairs=sorted(pairs, key=lambda p: p.lift, reverse=True),
        anchors=[{"id": category_token(*a), "label": humanise(*a)} for a in MINED_ANCHORS],
        design_effects=deffs, significance=significance,
        queries_sent=len(pair_bodies) + len(anchor_bodies) + 1,
        example_query={"endpoint": "_relate", "body": pair_bodies[0]},
    )
