"""Shop analytics — the shop owner's view of the patterns (ADR 0031).

Four sections, each served by its own endpoint so that changing the KPI
re-asks only its section:

  1. What goes with a click and a purchase — field-form `_relate` on
     `impressions`, `where {purchased: true}` (or `{clicked: true}`),
     one per product, product-state, shopper, context and recency field.
     (This module.)
  2. Who buys what, and when — `_relate` on `order_lines` over the
     product's category and dietary line, for one season, segment or
     diet rule. (This module.)
  3. Baskets — `src/basket_pairs.py`.
  4. Search words — `src/search_words.py`.

Each section also sends two `_relate`s on the customer column to measure
how clustered its rows are (`src/design_effect.py`), and every lift is
judged by the rules in `src/lift_rows.py`: clustering, support, and a
Bonferroni level for the section's number of tests. A field that keeps
no row is listed as "no clear effect".

Each section answers in 1.5–3 s alone, 4–8 s when the page asks all
four at once (`shoppers`, 2026-10-13), so the endpoints cache them for
30 minutes as Product Insights does (`src/app.py`).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.demand_service import season_months
from src.design_effect import DesignEffect, customer_bodies, design_effect, rows_per_customer
from src.lift_rows import (LiftRow, Significance, candidates_from_hits, fields_without_clear_effect,
                           judge, relate_hits)
from src.timing import submit_in_request


KPIS = ("purchased", "clicked")

# Related to the KPI on `impressions`. `product_category` is left out: it is
# the denormalised copy of `product_sku.category`, and the two return the
# same hits (probe, 2026-10-13), so it would show every row twice.
FUNNEL_FIELDS = [
    "product_sku.rating_band", "product_sku.category",
    # ADR 0032: the product as it was that month (one link, as product_sku.*).
    "product_state.on_offer", "product_state.discount_band", "product_state.age",
    "product_state.rival_launched", "product_state.price_change",
    # ADR 0033: the shopper only as a shop knows them, through the context:
    # what they declared, and where they were shown the product.
    "context.customer.pets", "context.customer.diet", "context.surface",
    "just_bought",
]
# Related over the chosen group's order lines. `dietary` shows a diet rule
# being kept (grain-free households buy grain-free food), which the
# category alone can't.
WHO_FIELDS = ["product_sku.category", "product_sku.dietary"]
# Above any of these fields' number of values: a full page raises.
FIELD_LIMIT = 50

_SEASONS = ["spring", "summer", "autumn", "winter"]
_PETS = ["dog", "cat", "small_animal", "aquarium", "bird"]
_DIETS = ["grain-free", "sensitive", "senior", "puppy"]
# (id, label, group, where). The id is what the page keeps in the URL
# (`?who=grain-free`); the values of the three groups don't overlap.
WHO_OPTIONS: list[tuple[str, str, str, dict]] = (
    [(s, s.capitalize(), "Season", {"order_id.month": {"$or": season_months(s)}}) for s in _SEASONS]
    # Declared by the customer (ADR 0033), two links from the order line.
    + [(p, f"{p.replace('_', ' ').capitalize()} households", "Declared pets",
        {"order_id.customer_id.pets": {"$match": p}}) for p in _PETS]
    + [(d, f"{d.capitalize()} diet", "Declared diet", {"order_id.customer_id.diet": d}) for d in _DIETS]
)
DEFAULT_WHO = "summer"

# Every month of the data window. As a `where` it selects every row, which
# gives each customer's row count; the services check that it does.
WINDOW_MONTHS = sorted({m for s in _SEASONS for m in season_months(s)})


@dataclass
class LiftSection:
    selected: str                   # the KPI, or the who/when id
    options: list[dict]             # the who/when picker; empty for the KPI
    rows: list[LiftRow]
    fields_without_clear_effect: list[str]
    clustering: DesignEffect
    significance: Significance
    queries_sent: int
    example_query: dict             # one body that was sent

    def to_dict(self) -> dict:
        return asdict(self)


def field_body(table: str, where: dict, field: str) -> dict:
    # With `where` as the condition, a hit's lift is how much more common
    # the field's value is among the condition's rows than among all rows.
    return {"from": table, "where": where, "relate": field, "limit": FIELD_LIMIT}


# A visitor's showings before their first order (ADR 0040) belong to no customer, so the
# clustering below can only see the identified ones. Those are all we cluster on; the
# anonymous visits are 1-3 sessions each and close to independent.
IDENTIFIED = {"context.customer": {"$exists": True}}


def lift_section(client: AitoClient, *, table: str, customer_field: str, month_field: str,
                  condition: dict, fields: list[str], selected: str, options: list[dict]) -> LiftSection:
    identified = IDENTIFIED if customer_field == "context.customer" else {}
    condition = {**condition, **identified}
    field_bodies = [field_body(table, condition, f) for f in fields]
    population = {month_field: {"$or": WINDOW_MONTHS}, **identified}
    everyone_body, condition_body = customer_bodies(table, customer_field, population, condition)

    with ThreadPoolExecutor(max_workers=8) as pool:
        field_jobs = [submit_in_request(pool, relate_hits, client, b) for b in field_bodies]
        everyone_job, condition_job = (submit_in_request(pool, relate_hits, client, b)
                                       for b in (everyone_body, condition_body))
        hits_by_field = [job.result() for job in field_jobs]
        everyone_hits, condition_hits = everyone_job.result(), condition_job.result()

    everyone = rows_per_customer(everyone_hits, customer_field)
    population_rows = client.search(table, where=population, limit=0)["total"]
    if sum(everyone.values()) != population_rows:
        raise AitoError(f"{table}: the customers' rows in {WINDOW_MONTHS[0]}…{WINDOW_MONTHS[-1]} cover "
                        f"{sum(everyone.values())} of {population_rows} rows")
    clustering = design_effect(everyone, rows_per_customer(condition_hits, customer_field))

    candidates = [c for field, hits in zip(fields, hits_by_field)
                  for c in candidates_from_hits(field, hits, clustering.design_effect)]
    rows, significance = judge(candidates)
    return LiftSection(
        selected=selected, options=options, rows=rows,
        fields_without_clear_effect=fields_without_clear_effect(fields, rows),
        clustering=clustering, significance=significance,
        queries_sent=len(field_bodies) + 2, example_query={"endpoint": "_relate", "body": field_bodies[0]},
    )


def get_funnel_section(client: AitoClient, kpi: str = "purchased") -> LiftSection:
    if kpi not in KPIS:
        raise ValueError(f"Unknown kpi {kpi!r}; expected one of {KPIS}")
    return lift_section(client, table="impressions", customer_field="context.customer", month_field="context.month",
                         condition={kpi: True}, fields=FUNNEL_FIELDS, selected=kpi, options=[])


def get_who_section(client: AitoClient, who: str = DEFAULT_WHO) -> LiftSection:
    where = next((w for option_id, _, _, w in WHO_OPTIONS if option_id == who), None)
    if where is None:
        raise ValueError(f"Unknown who {who!r}; expected one of {[o[0] for o in WHO_OPTIONS]}")
    options = [{"id": i, "label": label, "group": group} for i, label, group, _ in WHO_OPTIONS]
    return lift_section(client, table="order_lines", customer_field="order_id.customer_id",
                         month_field="order_id.month", condition=where, fields=WHO_FIELDS,
                         selected=who, options=options)
