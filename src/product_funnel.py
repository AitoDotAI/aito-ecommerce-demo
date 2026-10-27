"""A product's funnel for a month: impressions → clicks → purchases → profit (ADR 0050).

Every step is Aito's estimate for the product as its properties say, so the funnel moves when the owner
changes one (the offer, the list price, the stars, the pictures, the description, the advertising):

- impressions: the product's mean showings before the month × `_estimate showings_index` (regression, on
  `monthly_sales`: the product, its offer and its advertising). Showings are what the ranker gives it, and
  an offer or an advertisement is what moves them (placement, ADR 0045);
- clicks, purchases: impressions × the chance a showing ends in one, from `src/product_kpi.py`'s
  `_predict clicked` / `purchased` on the product's properties;
- purchases are units: the showings that end in a purchase × the product's own units per purchased showing
  (`units_per_purchase`: a customer buys two bags, or re-orders from the order history without a showing);
- profit: purchases × (price − unit cost) − the month's ad spend.

Purchases come from the showing, not from clicks × a conversion, so the steps cannot disagree with the way
the data counts them. `check_units` is the same quantity by another route, `_estimate units_index` at the
price × the mean units (src/product_pricing.py); a gap of more than CHECK_GAP is reported, not hidden.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.demand_forecast import LATEST_MONTH
from src.lookup_errors import ProductNotOnSaleError, UnknownProductError
from src.product_decision import BAND_DISCOUNT_PCT
from src.product_kpi import get_product_kpis
from src.product_pricing import estimate_units_index

# What an advertisement costs the shop a month, by level. The shop declares its own; these are ours until it
# does (ADR 0050), so advertising does not win the profit line for nothing.
AD_SPEND_EUR = {"none": 0.0, "search": 60.0, "banner": 180.0}
CHECK_GAP = 0.25


@dataclass(frozen=True)
class Funnel:
    impressions: float
    clicks: float
    purchases: float
    price_eur: float
    revenue_eur: float
    gross_profit_eur: float     # purchases × (price − unit cost)
    ad_spend_eur: float
    profit_eur: float           # after the ad spend
    ctr: float                  # P(click | shown) for the properties
    purchase_rate: float        # P(purchase | shown)
    showings_index: float       # Aito's estimate, floored at 0


@dataclass(frozen=True)
class ProductFunnel:
    sku: str
    month: str
    mean_showings: float        # the product's showings a month before `month`
    mean_units: float | None
    units_per_purchase: float   # the product's units sold ÷ its showings that ended in a purchase, all months
    unit_cost_eur: float
    now: Funnel                 # the product's properties as they are
    asked: Funnel               # ... with the owner's changes
    changed: list[str]
    check_units: float | None   # units by `_estimate units_index` at the asked price
    check_gap: float | None     # (funnel units − check units) ÷ check units
    check_ok: bool | None
    last_month: dict            # what happened in `month`: showings, units
    showings_support: int       # past product-months the showings estimate rests on
    ad_spend_assumed: dict[str, float]
    last_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def showings_body(sku: str, discount_band: str, ad_level: str) -> dict:
    return {"from": "monthly_sales", "where": {"product_sku": sku, "discount_band": discount_band, "ad_level": ad_level},
            "estimate": "showings_index", "model": "regression"}


def get_product_funnel(client: AitoClient, sku: str, month: str = LATEST_MONTH,
                       changes: dict[str, object] | None = None, list_price_eur: float | None = None) -> ProductFunnel:
    """`changes`: the properties the owner changed (src/product_kpi.py's EDITABLE); `list_price_eur`: a new list price."""
    changes = dict(changes or {})
    states = client.search("product_states", where={"product_sku": sku, "month": month}, limit=1)["hits"]
    if not states:
        raise ProductNotOnSaleError(f"{sku} has no state in {month}")
    state = states[0]
    inventory = client.search("inventory", where={"sku": sku}, limit=1)["hits"]
    if not inventory:
        raise AitoError(f"{sku} has no inventory row, so it has no unit cost")
    sales = sorted(client.search("monthly_sales", where={"product_sku": sku}, limit=200)["hits"],
                   key=lambda r: r["month"])
    if not sales:
        raise UnknownProductError(f"{sku} has no monthly sales")
    earlier = [r for r in sales if r["month"] < month]
    mean_showings = sum(r["showings"] for r in earlier) / len(earlier) if earlier else 0.0
    mean_units = (sum(r["units_sold"] for r in earlier) / len(earlier)) if earlier and sum(
        r["units_sold"] for r in earlier) else None
    if not mean_showings:
        raise AitoError(f"{sku} was never shown before {month}: the funnel has no impressions to scale")

    reference = float(state["list_price_eur"]) / float(state["list_price_index"])
    unit_cost = float(inventory[0]["unit_cost_eur"])
    if list_price_eur is not None:
        changes["list_price_index"] = round(list_price_eur / reference, 3)

    units_per_purchase = _units_per_purchase(client, sku, sales)
    now = _funnel(client, sku, month, {}, state, reference, unit_cost, mean_showings, units_per_purchase)
    asked = (_funnel(client, sku, month, changes, state, reference, unit_cost, mean_showings, units_per_purchase)
             if changes else now)
    check_units = check_gap = check_ok = None
    if mean_units is not None:
        index = float(_property(changes, state, "list_price_index"))
        offer = _offer_pct(state, _property(changes, state, "discount_band"))
        check_units = estimate_units_index(client, sku, round(index * (1 - offer / 100), 3)) * mean_units
        check_gap = (asked.purchases - check_units) / check_units if check_units else None
        check_ok = None if check_gap is None else abs(check_gap) <= CHECK_GAP
    this_month = next((r for r in sales if r["month"] == month), None)
    band, ad = _property(changes, state, "discount_band"), _property(changes, state, "ad_level")
    return ProductFunnel(
        sku=sku, month=month, mean_showings=round(mean_showings, 2),
        mean_units=None if mean_units is None else round(mean_units, 2), units_per_purchase=round(units_per_purchase, 2),
        unit_cost_eur=round(unit_cost, 2), now=now, asked=asked, changed=sorted(changes), check_units=None if check_units is None else round(check_units, 2),
        check_gap=None if check_gap is None else round(check_gap, 3), check_ok=check_ok,
        last_month={} if this_month is None else {"showings": this_month["showings"], "units": this_month["units_sold"]},
        showings_support=len(earlier), ad_spend_assumed=AD_SPEND_EUR,
        last_query={"endpoint": "_estimate", "body": showings_body(sku, band, ad)})


def _property(changes: dict, state: dict, name: str):
    return changes.get(name, state[name])


def _units_per_purchase(client: AitoClient, sku: str, sales: list[dict]) -> float:
    """Units sold ÷ showings that ended in a purchase. Above 1 when buyers take several and when the product
    also sells to re-orders that start from the order history, not from a showing."""
    purchased = client.search("impressions", where={"product_sku": sku, "purchased": True}, limit=0)["total"]
    units = sum(r["units_sold"] for r in sales)
    if not purchased:
        if units:
            raise AitoError(f"{sku} sold {units} units but none from a showing, so its units per purchase are undefined")
        return 1.0
    return units / purchased


def _funnel(client: AitoClient, sku: str, month: str, changes: dict[str, object], state: dict, reference: float,
            unit_cost: float, mean_showings: float, units_per_purchase: float) -> Funnel:
    kpis = get_product_kpis(client, sku, month, changes)
    band, ad = _property(changes, state, "discount_band"), _property(changes, state, "ad_level")
    answer = client.estimate("monthly_sales", showings_body(sku, band, ad)["where"], "showings_index",
                             model="regression", with_why=False)
    if answer.get("estimate") is None:
        raise AitoError(f"_estimate showings_index returned no estimate for {sku} ({band}, {ad}): {answer}")
    showings_index = max(float(answer["estimate"]), 0.0)
    impressions = mean_showings * showings_index
    ctr, rate = (kpis.estimates[k].p for k in ("clicked", "purchased"))
    list_price = reference * float(_property(changes, state, "list_price_index"))
    offer = _offer_pct(state, band)
    price = round(list_price * (1 - offer / 100), 2)
    purchases = impressions * rate * units_per_purchase
    gross = purchases * (price - unit_cost)
    ad_spend = AD_SPEND_EUR[ad]
    return Funnel(impressions=round(impressions, 2), clicks=round(impressions * ctr, 2), purchases=round(purchases, 2),
                  price_eur=price, revenue_eur=round(purchases * price, 2), gross_profit_eur=round(gross, 2),
                  ad_spend_eur=ad_spend, profit_eur=round(gross - ad_spend, 2), ctr=ctr, purchase_rate=rate,
                  showings_index=round(showings_index, 3))


def _offer_pct(state: dict, band: str) -> float:
    """The month's own offer for its band; another band the owner picked stands for its typical discount."""
    if band == state["discount_band"]:
        return float(state["discount_pct"]) if state["on_offer"] else 0.0
    return float(BAND_DISCOUNT_PCT[band])
