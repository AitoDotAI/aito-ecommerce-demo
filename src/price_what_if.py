"""Price what-if: next month's units, revenue and profit at a price the
user chooses, and the factors behind the estimate (ADR 0029).

One `_estimate units_sold` with `model: "regression"`. That model explains
itself as one term per field in the `where`, around a mean, in one of two
forms, depending on the data:

- `exp(mean + Σ terms)`: a base (e^mean units) **multiplied** by one factor
  per field. Seen when every training row sold something.
- `mean + Σ terms`: a base **plus** one effect in units per field. Seen
  when the data has months with zero sales, which a log can't take.

Either way the rows chain to the estimate exactly, which the default k-NN
model's averaged neighbours can't do. `waterfall` checks that they do,
and raises if not.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.demand_forecast import last_month_units, price_where
from src.estimate_why import regression_terms, term_label
from src.lookup_errors import UnknownProductError

# A factor that moves the estimate by less than this share is folded into
# one "other factors" row: shown alone, "+0.1 %" looks like evidence.
MIN_SHOWN_CHANGE = 0.005


@dataclass(frozen=True)
class Factor:
    field: str          # the `where` field, or "other" / "residual"
    label: str          # what the row says, e.g. "Price €4.68"
    effect: float       # a multiplier (form "multiply") or units added (form "add")


@dataclass(frozen=True)
class PriceWhatIf:
    sku: str
    name: str
    price_eur: float
    cost_eur: float
    units: float
    # A linear model can go below zero at a high price; the page then shows
    # 0 units and says so, rather than a negative count.
    below_zero: bool
    revenue_eur: float
    profit_eur: float
    form: str           # "multiply" | "add": how the factors combine
    base_units: float
    factors: list[Factor]
    last_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def get_price_what_if(client: AitoClient, sku: str, price_eur: float) -> PriceWhatIf:
    # The endpoint refuses these with a 422; this guards other callers.
    if not (math.isfinite(price_eur) and price_eur > 0):
        raise ValueError(f"price must be a positive number, got {price_eur}")
    products = client.search("products", where={"sku": sku}, limit=1)["hits"]
    if not products:
        raise UnknownProductError(f"No product {sku} in the catalogue")
    product = products[0]
    inventory = client.search("inventory", where={"sku": sku}, limit=1)["hits"]
    if not inventory:
        raise AitoError(f"{sku} has no inventory row, so it has no unit cost")
    cost = float(inventory[0]["unit_cost_eur"])
    sales = client.search("monthly_sales", where={"product_sku": sku}, limit=200)["hits"]

    # The same evidence as the demand curve: the latest sales row's profile
    # (or the catalogue's for a SKU that never sold), last month's units, the price.
    profile = max(sales, key=lambda r: r["month"]) if sales else product
    where = price_where(sku, profile, last_month_units(sales), round(price_eur, 2))
    res = client.estimate("monthly_sales", where=where, estimate_field="units_sold", model="regression")
    if res.get("estimate") is None:
        raise AitoError(f"_estimate units_sold returned no estimate for {sku} at €{price_eur}: {res}")
    estimate = float(res["estimate"])
    form, base, factors = waterfall(res.get("why"), estimate)

    # Revenue and profit follow the units shown, so the three agree on screen.
    units = round(max(estimate, 0.0), 2)
    return PriceWhatIf(
        sku=sku,
        name=product["name"],
        price_eur=round(price_eur, 2),
        cost_eur=round(cost, 2),
        units=units,
        below_zero=estimate < 0,
        revenue_eur=round(price_eur * units, 2),
        profit_eur=round((price_eur - cost) * units, 2),
        form=form,
        base_units=base,   # unrounded: the page chains the factors onto it
        factors=factors,
        last_query={"endpoint": "_estimate", "body": {
            "from": "monthly_sales", "where": where, "estimate": "units_sold",
            "model": "regression", "select": ["estimate", "why"],
        }},
    )


def waterfall(why: object, estimate: float) -> tuple[str, float, list[Factor]]:
    """The form, the base and the factors of a regression `_estimate` why,
    largest effect first, small ones folded into "other factors"."""
    form, terms = regression_terms(why)
    mean = next((t["value"] for t in terms if t["type"] == "mean centering"), None)
    if mean is None:
        raise AitoError(f"unexpected _estimate why: no mean term in {why}")
    multiply = form == "multiply"
    base = math.exp(mean) if multiply else mean

    shown: list[Factor] = []
    folded = 1.0 if multiply else 0.0
    for term in terms:
        if term["type"] == "mean centering":
            continue
        factor = _factor(term, multiply)
        if factor is None:
            continue
        change = abs(factor.effect - 1) if multiply else abs(factor.effect) / max(abs(estimate), 1e-9)
        # The price row stays visible: it's the one the user is changing.
        if change < MIN_SHOWN_CHANGE and factor.field != "price_eur":
            folded = folded * factor.effect if multiply else folded + factor.effect
        else:
            shown.append(factor)
    shown.sort(key=lambda f: -abs(math.log(f.effect) if multiply else f.effect))
    if folded != (1.0 if multiply else 0.0):
        shown.append(Factor("other", "Other factors, each under 0.5 %", folded))

    if multiply:
        chained = base * math.prod(f.effect for f in shown)
        if not math.isclose(chained, estimate, rel_tol=1e-6):
            raise AitoError(f"the why does not multiply out to the estimate: {chained} vs {estimate}")
    else:
        chained = base + sum(f.effect for f in shown)
        if not math.isclose(chained, estimate, rel_tol=1e-6, abs_tol=1e-6):
            raise AitoError(f"the why does not add up to the estimate: {chained} vs {estimate}")
    return form, base, shown


def _factor(term: dict, multiply: bool) -> Factor | None:
    def effect(value: float) -> float:
        return math.exp(value) if multiply else value

    if term["type"] == "input" and term.get("name") == "residual":
        # 0 when the regression explains the estimate fully; kept visible
        # otherwise, so the rows still chain to the estimate.
        if term["value"] == 0:
            return None
        return Factor("residual", "Not explained by the fields", effect(term["value"]))
    if term["type"] != "regression":
        raise AitoError(f"unexpected term in _estimate why: {term}")
    proposition = term.get("proposition")
    if not (isinstance(proposition, dict) and len(proposition) == 1):
        raise AitoError(f"unexpected regression term, expected one field: {term}")
    [(field, value)] = proposition.items()
    return Factor(field, term_label(field, value), effect(term["value"]))

