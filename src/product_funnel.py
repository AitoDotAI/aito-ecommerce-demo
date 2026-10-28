"""A product's funnel for a month: impressions → clicks → purchases → profit (ADR 0050).

Every step is Aito's estimate for the product as its properties say, so the funnel moves when the owner
changes one (the offer, the list price, the stars, the pictures, the description, the advertising):

- impressions: the product's mean showings before the month × `_estimate showings_index` (regression, on
  `monthly_sales`: the product, its offer and its advertising). Showings are what the ranker gives it, and
  an offer or an advertisement is what moves them (placement, ADR 0045);
- clicks: impressions × `_predict clicked` on the product's properties (src/product_kpi.py);
- purchases: clicks × `_predict purchased` on the same properties given `clicked: true`, so a purchase is a
  click that went on (the data is monotone: purchased ⇒ clicked) and never exceeds the clicks;
- Aito learns both over the ranked showings only. The product's own history carries them to all its showings:
  both rates are moved in odds from the ranked showings' level to its own, so they stay below 1. Aito says
  how the properties move the chance, the product's history its level;
- a purchase buys 1, 2 or 3 units, in the shares the product's own order lines have (`sizes`, tallest first:
  in the page the width is purchases, the height the units each buys). Units it also sells without a showing
  (a re-order from the order history) come to `other_units` a month, the product's own and not moved by its
  properties;
- profit: units × (price − unit cost) − the month's ad spend.

`check_units` is the same quantity by another route, `_estimate units_index` at the
price × the mean units (src/product_pricing.py); a gap of more than CHECK_GAP is reported, not hidden.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.demand_forecast import LATEST_MONTH
from src.lookup_errors import ProductNotOnSaleError, UnknownProductError
from src.product_decision import BAND_DISCOUNT_PCT
from src.product_kpi import LIST_PRICE_BANDS, check_changes, get_product_kpis, list_price_band, where_for
from src.product_pricing import RANGE_MARGIN, estimate_units_index

# What an advertisement costs the shop a month, by level. The shop declares its own; these are ours until it
# does (ADR 0050), so advertising does not win the profit line for nothing.
AD_SPEND_EUR = {"none": 0.0, "search": 60.0, "banner": 180.0}
CHECK_GAP = 0.25


@dataclass(frozen=True)
class PurchaseSize:
    units_each: int
    purchases: float


@dataclass(frozen=True)
class ActualMonth:
    """What the month's data says happened: the same steps, counted, to set the estimate against."""
    impressions: int
    clicks: int
    purchases: int
    units: int
    price_eur: float
    revenue_eur: float
    gross_profit_eur: float
    ad_spend_eur: float         # the assumed spend for the month's advertising level
    profit_eur: float


@dataclass(frozen=True)
class Funnel:
    impressions: float
    clicks: float
    purchases: float            # showings that ended in a purchase: at most the clicks
    sizes: list[PurchaseSize]   # the purchases by the units each buys, tallest first
    other_units: float          # units sold without a showing, a month
    units: float                # what the purchases buy, and the other units
    price_eur: float
    revenue_eur: float
    gross_profit_eur: float     # units × (price − unit cost)
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
    units_per_purchase: float   # the mean units a purchase buys, from the product's order lines
    own_ctr: float              # its click rate over all its showings, and purchased ÷ clicked, all months
    own_conversion: float       # purchased ÷ clicked
    no_data: str | None         # why the list price asked was left out, when it is beyond the prices tried
    unit_cost_eur: float
    now: Funnel                 # the product's properties as they are
    asked: Funnel               # ... with the owner's changes
    changed: list[str]
    check_units: float | None   # units by `_estimate units_index` at the asked price
    check_gap: float | None     # (funnel units − check units) ÷ check units
    check_ok: bool | None
    last_month: dict            # what happened in `month`: showings, units
    notes: list[str]            # steps Aito's properties cannot move for this product, and why
    actual: ActualMonth | None  # the month's own funnel, counted; none when it has no sales row yet
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
    check_changes(changes)
    products = client.search("products", where={"sku": sku}, limit=1)["hits"]
    if not products:
        raise UnknownProductError(f"No product {sku} in the catalogue")
    product = products[0]
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

    no_data = _drop_list_price_beyond_the_data(changes, state, sales, reference)
    history = _history(client, sku, sales)
    now = _funnel(client, sku, month, {}, product, state, reference, unit_cost, mean_showings, history)
    asked = _funnel(client, sku, month, changes, product, state, reference, unit_cost, mean_showings, history) if changes else now
    check_units = check_gap = check_ok = None
    if mean_units is not None:
        index = float(_property(changes, state, "list_price_index"))
        offer = _offer_pct(state, _property(changes, state, "discount_band"))
        check_units = estimate_units_index(client, sku, round(index * (1 - offer / 100), 3)) * mean_units
        check_gap = (asked.units - check_units) / check_units if check_units else None
        check_ok = None if check_gap is None else abs(check_gap) <= CHECK_GAP
    this_month = next((r for r in sales if r["month"] == month), None)
    band, ad = _property(changes, state, "discount_band"), _property(changes, state, "ad_level")
    return ProductFunnel(
        sku=sku, month=month, mean_showings=round(mean_showings, 2),
        mean_units=None if mean_units is None else round(mean_units, 2), units_per_purchase=round(sum(q * s for q, s in history.size_shares.items()), 2),
        own_ctr=round(history.ctr, 4), own_conversion=round(history.conversion, 4), no_data=no_data,
        unit_cost_eur=round(unit_cost, 2), now=now, asked=asked, changed=sorted(changes), check_units=None if check_units is None else round(check_units, 2),
        check_gap=None if check_gap is None else round(check_gap, 3), check_ok=check_ok,
        notes=_notes(history), actual=None if this_month is None else _actual(client, state, this_month, unit_cost),
        last_month={} if this_month is None else {"showings": this_month["showings"], "units": this_month["units_sold"]},
        showings_support=len(earlier), ad_spend_assumed=AD_SPEND_EUR,
        last_query={"endpoint": "_estimate", "body": showings_body(sku, band, ad)})


def _actual(client: AitoClient, state: dict, sales_row: dict, unit_cost: float) -> ActualMonth:
    """The month's showings, clicks and purchases, counted on the product's state of the month in both
    showing tables, with the units and money that followed."""
    where = {"product_state": state["product_state_id"]}
    counts = [{"from": table, "where": {**where, **outcome}, "limit": 0}
              for table in ("impressions", "unranked_showings")
              for outcome in ({}, {"clicked": True}, {"purchased": True})]
    r_shown, r_clicked, r_purchased, u_shown, u_clicked, u_purchased = (a["total"] for a in client.batch(counts))
    units, price = sales_row["units_sold"], float(state["price_eur"])
    gross = units * (price - unit_cost)
    spend = AD_SPEND_EUR[state["ad_level"]]
    return ActualMonth(impressions=r_shown + u_shown, clicks=r_clicked + u_clicked,
                       purchases=r_purchased + u_purchased, units=units, price_eur=price,
                       revenue_eur=round(units * price, 2), gross_profit_eur=round(gross, 2), ad_spend_eur=spend,
                       profit_eur=round(gross - spend, 2))


def _property(changes: dict, state: dict, name: str):
    return changes.get(name, state[name])


def _drop_list_price_beyond_the_data(changes: dict, state: dict, sales: list[dict], reference: float) -> str | None:
    """A list price whose price paid is beyond what the product has sold at (plus RANGE_MARGIN) has no data
    behind it: `_predict` falls back to the base rate for a band it has never seen. It is left out of `changes`
    and the reason returned, so the other changes still show."""
    if "list_price_index" not in changes:
        return None
    changes_price = changes["list_price_index"] * reference
    paid = changes["list_price_index"] * (1 - _offer_pct(state, _property(changes, state, "discount_band")) / 100)
    indexes = [float(r["price_index"]) for r in sales]
    low, high = min(indexes) - RANGE_MARGIN, max(indexes) + RANGE_MARGIN
    if low <= paid <= high and list_price_band(changes["list_price_index"]) in LIST_PRICE_BANDS:
        return None
    del changes["list_price_index"]
    return (f"A list price of €{changes_price:.2f} is outside what this product has sold at "
            f"(€{min(indexes) * reference:.2f}–€{max(indexes) * reference:.2f} paid), so the funnel keeps today's list price.")


@dataclass(frozen=True)
class History:
    """The product's own months: its click and purchase rates over all its showings, the same over the ranked
    ones Aito learns from, and the units a purchase buys."""
    ctr: float
    purchase_rate: float
    conversion: float           # purchased ÷ clicked
    ranked_ctr: float | None            # None when no ranked showing of the product was clicked / purchased:
    ranked_conversion: float | None     # Aito has nothing of the product's own to scale
    size_shares: dict[int, float]       # share of the product's order lines buying 1, 2, 3 units
    other_units: float                  # units a month sold without a showing
    never_sold: bool = False            # no units in any month: every step is 0


QUANTITIES = (1, 2, 3)      # the most a line buys in the data


def _history(client: AitoClient, sku: str, sales: list[dict]) -> History:
    counts = [{"from": table, "where": {"product_sku": sku, **outcome}, "limit": 0}
              for table in ("impressions", "unranked_showings")
              for outcome in ({}, {"clicked": True}, {"purchased": True})]
    lines = [{"from": "order_lines", "where": {"product_sku": sku, **qty}, "limit": 0}
             for qty in ({}, *({"qty": q} for q in QUANTITIES))]
    answers = [a["total"] for a in client.batch([*counts, *lines])]
    r_shown, r_clicked, r_purchased, u_shown, u_clicked, u_purchased, n_lines, *by_qty = answers
    shown, clicked, purchased = r_shown + u_shown, r_clicked + u_clicked, r_purchased + u_purchased
    units = sum(r["units_sold"] for r in sales)
    if not units:
        return History(0.0, 0.0, 0.0, None, None, {1: 1.0}, 0.0, never_sold=True)     # the funnel shows no purchases
    if not (shown and clicked and purchased):
        raise AitoError(f"{sku} sold {units} units but has {shown} showings, {clicked} clicked and "
                        f"{purchased} purchased: no rate of its own to scale the funnel by")
    if sum(by_qty) != n_lines:
        raise AitoError(f"{sku} has {n_lines} order lines but {sum(by_qty)} of them buy {QUANTITIES} units")
    mean_qty = sum(q * n for q, n in zip(QUANTITIES, by_qty)) / n_lines
    other = units - purchased * mean_qty
    if other < -0.5:
        raise AitoError(f"{sku}: {purchased} purchased showings at {mean_qty:.2f} units are more than the {units} units sold")
    return History(ctr=clicked / shown, purchase_rate=purchased / shown, conversion=purchased / clicked,
                   ranked_ctr=r_clicked / r_shown if r_clicked else None,
                   ranked_conversion=r_purchased / r_clicked if r_purchased else None,
                   size_shares={q: n / n_lines for q, n in zip(QUANTITIES, by_qty) if n},
                   other_units=max(other, 0.0) / len(sales))


def _notes(history: History) -> list[str]:
    notes = []
    if history.never_sold:
        return notes
    if history.ranked_ctr is None:
        notes.append("None of this product's ranked showings was clicked, so Aito has nothing of its own to scale: "
                     "its click rate is its own, and changing a property does not move it.")
    if history.ranked_conversion is None:
        notes.append("None of this product's ranked clicks became a purchase (it sells through checkout and re-orders), "
                     "so its conversion is its own, and changing a property does not move it.")
    return notes


def _carry(aito: float, ranked: float, own: float) -> float:
    """Aito's rate for the properties (a click rate or a conversion), moved from the ranked showings' level to
    the product's own, in odds so the result stays inside (0, 1). A conversion of exactly 0 or 1 has no odds and is kept as it is."""
    if not (0 < aito < 1 and 0 < ranked < 1 and 0 < own < 1):
        return aito
    odds = own / (1 - own) * (aito / (1 - aito)) / (ranked / (1 - ranked))
    return odds / (1 + odds)


def _funnel(client: AitoClient, sku: str, month: str, changes: dict[str, object], product: dict, state: dict, reference: float,
            unit_cost: float, mean_showings: float, history: History) -> Funnel:
    kpis = get_product_kpis(client, sku, month, changes)
    band, ad = _property(changes, state, "discount_band"), _property(changes, state, "ad_level")
    answer = client.estimate("monthly_sales", showings_body(sku, band, ad)["where"], "showings_index",
                             model="regression", with_why=False)
    if answer.get("estimate") is None:
        raise AitoError(f"_estimate showings_index returned no estimate for {sku} ({band}, {ad}): {answer}")
    showings_index = max(float(answer["estimate"]), 0.0)
    impressions = mean_showings * showings_index
    # Aito's rates are over ranked showings; the product's own history carries them to all its showings.
    # With no ranked click (or purchase) of its own, Aito's rate has nothing to be scaled by: the product's own
    # rate stands, and a property the owner changes does not move that step (ProductFunnel.notes says so).
    ctr = history.ctr if history.ranked_ctr is None else _carry(kpis.estimates["clicked"].p, history.ranked_ctr, history.ctr)
    conversion = history.conversion if history.ranked_conversion is None else _carry(
        _conversion(client, product, state, changes), history.ranked_conversion, history.conversion)
    rate = ctr * conversion
    list_price = reference * float(_property(changes, state, "list_price_index"))
    offer = _offer_pct(state, band)
    price = round(list_price * (1 - offer / 100), 2)
    purchases = impressions * rate
    sizes = [PurchaseSize(q, round(purchases * share, 2)) for q, share in sorted(history.size_shares.items(), reverse=True)]
    units = purchases * sum(q * s for q, s in history.size_shares.items()) + history.other_units
    gross = units * (price - unit_cost)
    ad_spend = AD_SPEND_EUR[ad]
    return Funnel(impressions=round(impressions, 2), clicks=round(impressions * ctr, 2), purchases=round(purchases, 2),
                  sizes=sizes, other_units=round(history.other_units, 2), units=round(units, 2), price_eur=price, revenue_eur=round(units * price, 2), gross_profit_eur=round(gross, 2),
                  ad_spend_eur=ad_spend, profit_eur=round(gross - ad_spend, 2), ctr=ctr, purchase_rate=rate,
                  showings_index=round(showings_index, 3))


def _conversion(client: AitoClient, product: dict, state: dict, changes: dict[str, object]) -> float:
    """`_predict purchased` for the product's properties among showings that were clicked."""
    where = {**where_for(product, state, changes), "clicked": True}
    answer = client.predict("impressions", where, "purchased")
    hit = next((h for h in answer.get("hits", []) if h.get("feature") is True), None)
    if hit is None:
        raise AitoError(f"_predict purchased given clicked had no `true` hit: {str(answer)[:300]}")
    return float(hit["$p"])


def _offer_pct(state: dict, band: str) -> float:
    """The month's own offer for its band; another band the owner picked stands for its typical discount."""
    if band == state["discount_band"]:
        return float(state["discount_pct"]) if state["on_offer"] else 0.0
    return float(BAND_DISCOUNT_PCT[band])
