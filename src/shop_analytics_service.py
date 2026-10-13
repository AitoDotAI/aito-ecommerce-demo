"""Shop analytics — the shop owner's view of the patterns (ADR 0031).

Four sections, each a set of `_relate` queries sent in parallel:

  1. What goes with a click and a purchase — field-form `_relate` on
     `impressions`, `where {purchased: true}` (or `{clicked: true}`),
     one per product, shopper, context and recency field.
  2. Who buys what, and when — `_relate` on `order_lines` over the
     product's category and dietary line, for one segment, diet rule or
     season.
  3. Baskets — category pairs from `orders.line_categories`, the query
     Basket Rules mines (ADR 0022). Product-level pairs are too thin
     (3–8 shared orders per pair; ADR 0031 findings).
  4. Search words — see `src/search_words.py`.

Every lift is shown with its counts and 95 % interval, and a lift whose
interval includes 1 is left out (`src/lift_rows.py`). A field that keeps
no row is listed as "checked, no effect", as the Churn drivers do.

Not cached: the ~24 queries answer in about a second in parallel
(measured on `shoppers`, 2026-10-13), under the ~3 s at which the
heavier views are precomputed.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.aito_compat import related_value
# Basket Rules' anchors and token codec, so both views mine the same pairs.
from src.basket_rules_service import _ANCHORS, _decode, _humanise, _token
from src.demand_service import season_months
from src.lift_rows import LiftRow, by_strength, lift_row, real_lift_rows, relate_hits
from src.search_words import SearchWords, search_words_bodies, search_words_from_hits
from src.timing import submit_in_request


KPIS = ("purchased", "clicked")

# Related to the KPI on `impressions`. `product_category` is left out: it is
# the denormalised copy of `product_sku.category`, and the two return the
# same hits (probe, 2026-10-13), so it would show every row twice.
FUNNEL_FIELDS = [
    "product_sku.rating_band", "product_sku.category",
    "customer_segment", "customer_lifestyle", "customer_diet_rule",
    "just_bought", "surface",
]
# Above any of these fields' number of values: a full page raises.
FUNNEL_LIMIT = 50

# Related over the chosen group's order lines. `dietary` shows a diet rule
# being kept (grain-free households buy grain-free food), which the
# category alone can't.
WHO_FIELDS = ["product_sku.category", "product_sku.dietary"]
WHO_LIMIT = 30

# (id, label, group, where). The id is what the page keeps in the URL
# (`?who=grain-free`); the values of the three groups don't overlap.
_SEGMENTS = ["dog_owner", "cat_owner", "multi_pet", "small_animal_owner", "aquarium_owner"]
_DIET_RULES = ["grain-free", "sensitive", "senior", "puppy"]
_SEASONS = ["spring", "summer", "autumn", "winter"]
WHO_OPTIONS: list[tuple[str, str, str, dict]] = (
    [(s, s.capitalize(), "Season", {"order_id.month": {"$or": season_months(s)}}) for s in _SEASONS]
    + [(s, s.replace("_", " ").capitalize(), "Segment", {"customer_segment": s}) for s in _SEGMENTS]
    + [(d, f"{d.capitalize()} diet rule", "Diet rule", {"customer_diet_rule": d}) for d in _DIET_RULES]
)
DEFAULT_WHO = "summer"
BASKET_LIMIT = 30


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
class ShopAnalytics:
    kpi: str
    funnel_rows: list[LiftRow]
    funnel_fields_without_effect: list[str]
    who: str
    who_options: list[dict]
    who_rows: list[LiftRow]
    who_fields_without_effect: list[str]
    basket_pairs: list[BasketPair]
    search_words: SearchWords
    last_query: dict        # one body that was sent, and how many were

    def to_dict(self) -> dict:
        return asdict(self)


def funnel_body(kpi: str, field: str) -> dict:
    # With the KPI as the condition, a hit's lift is how much more common
    # the field's value is among clicked (or purchased) impressions than
    # among all impressions.
    return {"from": "impressions", "where": {kpi: True}, "relate": field, "limit": FUNNEL_LIMIT}


def who_body(where: dict, field: str) -> dict:
    return {"from": "order_lines", "where": where, "relate": field, "limit": WHO_LIMIT}


def basket_body(pet_type: str, category: str) -> dict:
    return {"from": "orders", "where": {"line_categories": {"$match": _token(pet_type, category)}},
            "relate": "line_categories", "limit": BASKET_LIMIT}


def _basket_pairs(anchor: tuple[str, str], hits: list[dict]) -> list[BasketPair]:
    anchor_token = _token(*anchor)
    pairs = []
    for hit in hits:
        token = related_value(hit, "line_categories")
        if token == anchor_token:
            continue   # the anchor itself: every order in the condition has it
        decoded = _decode(token)
        if decoded is None:
            raise AitoError(f"line_categories token {token!r} is not <pet>_<category>")
        row = lift_row("line_categories", token, float(hit["lift"]), hit["fs"])
        if row is not None:
            pairs.append(BasketPair(
                first=_humanise(*anchor), second=_humanise(*decoded), lift=row.lift,
                interval_low=row.interval_low, interval_high=row.interval_high,
                orders_with_both=row.rows_with_value, orders_with_first=row.condition_rows,
            ))
    return pairs


def _once_per_pair(pairs: list[BasketPair]) -> list[BasketPair]:
    # A → B and B → A have the same lift; show the pair once, from the
    # anchor mined first.
    seen: set[frozenset] = set()
    kept = []
    for pair in pairs:
        key = frozenset((pair.first, pair.second))
        if key not in seen:
            seen.add(key)
            kept.append(pair)
    return kept


def _without_effect(fields: list[str], rows: list[LiftRow]) -> list[str]:
    shown = {r.field for r in rows}
    return [f for f in fields if f not in shown]


def get_shop_analytics(client: AitoClient, kpi: str = "purchased", who: str = DEFAULT_WHO) -> ShopAnalytics:
    if kpi not in KPIS:
        raise ValueError(f"Unknown kpi {kpi!r}; expected one of {KPIS}")
    who_where = next((where for option_id, _, _, where in WHO_OPTIONS if option_id == who), None)
    if who_where is None:
        raise ValueError(f"Unknown who {who!r}; expected one of {[o[0] for o in WHO_OPTIONS]}")

    funnel_bodies = [funnel_body(kpi, f) for f in FUNNEL_FIELDS]
    who_bodies = [who_body(who_where, f) for f in WHO_FIELDS]
    basket_bodies = [basket_body(*anchor) for anchor in _ANCHORS]
    words_bodies = search_words_bodies()

    # Eight at a time: the shared instance also serves live demos.
    with ThreadPoolExecutor(max_workers=8) as pool:
        def submit(fn, body):
            return submit_in_request(pool, fn, client, body)

        funnel_jobs = [submit(real_lift_rows, b) for b in funnel_bodies]
        who_jobs = [submit(real_lift_rows, b) for b in who_bodies]
        basket_jobs = [submit(relate_hits, b) for b in basket_bodies]
        words_jobs = [submit(relate_hits, b) for b in words_bodies]
        funnel_rows = [row for job in funnel_jobs for row in job.result()]
        who_rows = [row for job in who_jobs for row in job.result()]
        basket_hits = [job.result() for job in basket_jobs]
        bought_words, shown_words = (job.result() for job in words_jobs)

    pairs = [p for anchor, hits in zip(_ANCHORS, basket_hits) for p in _basket_pairs(anchor, hits)]
    sent = funnel_bodies + who_bodies + basket_bodies + list(words_bodies)
    return ShopAnalytics(
        kpi=kpi,
        funnel_rows=by_strength(funnel_rows),
        funnel_fields_without_effect=_without_effect(FUNNEL_FIELDS, funnel_rows),
        who=who,
        who_options=[{"id": i, "label": label, "group": group} for i, label, group, _ in WHO_OPTIONS],
        who_rows=by_strength(who_rows),
        who_fields_without_effect=_without_effect(WHO_FIELDS, who_rows),
        basket_pairs=sorted(_once_per_pair(pairs), key=lambda p: p.lift, reverse=True),
        search_words=search_words_from_hits(bought_words, shown_words),
        last_query={"endpoint": "_relate", "body": funnel_bodies[0], "of": len(sent)},
    )
