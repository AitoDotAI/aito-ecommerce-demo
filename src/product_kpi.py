"""Product KPIs explained by the product's properties (ADR 0048): how likely a shopper shown a
product is to click it, and to buy it, and which of its properties that comes from.

One `_predict` per KPI on `impressions`, with the product's *properties* in the `where`, not its SKU:

    {"product_sku.brand": "PetNord", "product_sku.category": "treats", "product_sku.pet_type": "dog",
     "product_state.discount_band": "15-20", "product_state.rating_band": "4", ...}

`product_sku` and `product_state` are links, so each property is evidence like any other field, and
a property the product never had (an offer it has not run, a star band it has not reached) still
gets an answer. That is what makes the answer editable. The product's own history is not in the
query: for an existing product the `discount_what_if` (SKU in the `where`) is the better
estimate. This one says what the *properties* are worth.

Aito's `$why` for the `true` answer is the base rate, its normalisers and one lift per property
(sometimes one lift for a group of correlated properties). `kpi_estimate` raises when they don't
multiply out to `$p`. Beside each estimate, what actually happened: showings of products with exactly
these properties, and of this product, and how many ended in a click or a purchase.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.lookup_errors import UnknownProductError

KPIS = ("clicked", "purchased")
FIXED = {"brand": "product_sku.brand", "category": "product_sku.category", "pet_type": "product_sku.pet_type"}
# What the owner can change: the columns of the product's state that month.
EDITABLE = {"discount_band": "product_state.discount_band", "rating_band": "product_state.rating_band",
            "label": "product_state.label", "age": "product_state.age", "stock": "product_state.stock",
            "rival_launched": "product_state.rival_launched",
            # ADR 0049, 0050: the list price and how the shop lists the product.
            "list_price_index": "product_state.list_price_band", "image_count": "product_state.image_count",
            "description_quality": "product_state.description_quality", "ad_level": "product_state.ad_level"}


# The values each property takes in the data. `_predict` answers the base rate, with a 200, for a value it has
# never seen, so a typo would read as an estimate: refuse it.
KNOWN_VALUES = {
    "discount_band": {"none", "10-15", "15-20", "20+"}, "rating_band": {"unrated", "1-2", "3", "4", "5"},
    "label": {"none", "popular", "recommended", "staff_pick"}, "age": {"new", "established"},
    "stock": {"in_stock", "low"}, "rival_launched": {True, False},
    "image_count": {"0-1", "2-3", "4+"}, "description_quality": {"thin", "ok", "rich"},
    "ad_level": {"none", "search", "banner"},
}
LIST_PRICE_BANDS = {str(pct) for pct in range(85, 120, 5)}


def check_changes(changes: dict[str, object]) -> None:
    """Refuse a property that is not editable, or a value the data has never held for it."""
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        raise ValueError(f"Not an editable property: {sorted(unknown)}; the editable ones are {sorted(EDITABLE)}")
    for name, value in changes.items():
        if name in KNOWN_VALUES and value not in KNOWN_VALUES[name]:
            raise ValueError(f"{value!r} is not a value of {name} in the data; it has {sorted(KNOWN_VALUES[name], key=str)}")


@dataclass(frozen=True)
class Factor:
    fields: list[str]       # the property's short name; several when Aito gave one lift for a group
    values: list[object]
    lift: float


@dataclass(frozen=True)
class KpiEstimate:
    kpi: str
    p: float                # Aito's `$p` that a shopper shown a product with these properties does it
    base_p: float           # the rate over all impressions
    normaliser: float
    factors: list[Factor]   # the lifts, as Aito gave them; the page orders them by impact
    similar_shown: int      # impressions of products with exactly these properties
    similar_hits: int       # ... of which ended in the KPI
    product_shown: int      # impressions of this product, ever
    product_hits: int


@dataclass(frozen=True)
class ProductKpis:
    sku: str
    month: str
    properties: dict[str, object]       # as asked: the state's, with the owner's changes
    changed: list[str]                  # the properties the owner changed
    no_data: str | None                 # why a list price asked was left out: no price point of the data holds it
    estimates: dict[str, KpiEstimate]   # by KPI
    last_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def where_for(product: dict, state: dict, changes: dict[str, object]) -> dict:
    """The `where` for a product's properties in a month's state, with `changes` (by short name) applied."""
    check_changes(changes)
    return {**{path: product[name] for name, path in FIXED.items()},
            **{path: _evidence(name, changes.get(name, state[name])) for name, path in EDITABLE.items()}}


def _evidence(name: str, value: object) -> object:
    """The value `_predict` conditions on. The list price goes in as its band: a decimal index only matches
    impressions whose state has the same cents, so an index between price points would fall back to the base rate."""
    return list_price_band(float(value)) if name == "list_price_index" else value


def list_price_band(list_price_index: float) -> str:
    """The same rule as the data's (data/catalogue_events.py): percent of the original list, to the nearest 5."""
    return str(round(list_price_index * 100 / 5) * 5)


def with_list_price_index(state: dict, changes: dict[str, object]) -> dict[str, object]:
    """`changes` with a `list_price_eur` the owner typed turned into the `list_price_index` the data holds:
    the new list price against the product's reference list price (this month's list price ÷ its index)."""
    if "list_price_eur" not in changes:
        return changes
    reference = float(state["list_price_eur"]) / float(state["list_price_index"])
    rest = {name: value for name, value in changes.items() if name != "list_price_eur"}
    return {**rest, "list_price_index": round(float(changes["list_price_eur"]) / reference, 3)}


def predict_body(kpi: str, where: dict) -> dict:
    return {"from": "impressions", "where": where, "predict": kpi, "select": ["$p", "feature", "$why"]}


def get_product_kpis(client: AitoClient, sku: str, month: str, changes: dict[str, object]) -> ProductKpis:
    products = client.search("products", where={"sku": sku}, limit=1)["hits"]
    if not products:
        raise UnknownProductError(f"No product {sku} in the catalogue")
    states = client.search("product_states", where={"product_sku": sku, "month": month}, limit=1)["hits"]
    if not states:
        raise UnknownProductError(f"{sku} has no state in {month}")
    changes = with_list_price_index(states[0], changes)
    check_changes(changes)
    no_data = None
    if "list_price_index" in changes and list_price_band(float(changes["list_price_index"])) not in LIST_PRICE_BANDS:
        no_data = (f"A list price {float(changes['list_price_index']):.2f} times the original list is beyond the price "
                   "points the shop has held (0.85–1.15), so the estimates keep today's list price.")
        changes = {name: value for name, value in changes.items() if name != "list_price_index"}
    where = where_for(products[0], states[0], changes)

    counts = [{"from": "impressions", "where": {**scope, **hit}, "limit": 0}
              for scope in (where, {"product_sku": sku})
              for hit in ({}, *({kpi: True} for kpi in KPIS))]
    answers = client.batch([*(predict_body(kpi, where) for kpi in KPIS), *counts])
    predictions, totals = answers[:len(KPIS)], [a["total"] for a in answers[len(KPIS):]]
    similar, own = totals[:3], totals[3:]

    estimates = {kpi: kpi_estimate(kpi, answer, similar_shown=similar[0], similar_hits=similar[1 + i],
                                   product_shown=own[0], product_hits=own[1 + i])
                 for i, (kpi, answer) in enumerate(zip(KPIS, predictions))}
    shown = {**{name: where[path] for name, path in FIXED.items()},
             **{name: changes.get(name, states[0][name]) for name in EDITABLE}}
    return ProductKpis(sku=sku, month=month, properties=shown, changed=sorted(changes), no_data=no_data, estimates=estimates,
                       last_query={"endpoint": "_predict", "body": predict_body("clicked", where)})


def kpi_estimate(kpi: str, answer: dict, **seen: int) -> KpiEstimate:
    """`$p` of the `true` answer and its `$why`, read into one estimate."""
    hit = next((h for h in answer.get("hits", []) if h.get("feature") is True), None)
    if hit is None:
        raise AitoError(f"_predict {kpi} had no `true` hit: {str(answer)[:300]}")
    why = hit.get("$why")
    if not (isinstance(why, dict) and why.get("type") == "product"):
        raise AitoError(f"_predict {kpi}: unexpected $why {str(why)[:300]}")

    base_p, normaliser, factors = None, 1.0, []
    for factor in why["factors"]:
        match factor["type"]:
            case "baseP":
                base_p = factor["value"]
            case "product":
                for inner in factor["factors"]:
                    if inner["type"] not in ("normalizer", "calibration"):
                        raise AitoError(f"_predict {kpi}: unexpected factor in $why: {inner}")
                    normaliser *= inner["value"]
            case "relatedPropositionLift":
                proposition = factor["proposition"]
                parts = proposition["$group"] if list(proposition) == ["$group"] else [proposition]
                named = [next(iter(part.items())) for part in parts]
                factors.append(Factor(fields=[path.split(".")[-1] for path, _ in named],
                                      values=[value for _, value in named], lift=factor["value"]))
            case _:
                raise AitoError(f"_predict {kpi}: unexpected factor in $why: {factor}")
    if base_p is None:
        raise AitoError(f"_predict {kpi}: $why has no base rate: {str(why)[:300]}")

    chained = base_p * normaliser * math.prod(f.lift for f in factors)
    if not math.isclose(chained, hit["$p"], rel_tol=1e-6):
        raise AitoError(f"_predict {kpi}: $why multiplies to {chained}, but $p is {hit['$p']}")
    return KpiEstimate(kpi=kpi, p=hit["$p"], base_p=base_p, normaliser=normaliser, factors=factors, **seen)
