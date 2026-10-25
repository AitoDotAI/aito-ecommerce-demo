"""The tools "Ask the store" gives its agent (ADR 0042).

Each tool wraps a service the owner views already call, so the agent and the views can't disagree,
and returns only fields of that service's result: the agent does no arithmetic of its own. All of
them read. A result names the `view` that shows the same numbers, and a what-if flags a band the
rule below calls thin.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.aito_client import AitoClient
from src.discount_what_if import get_discount_what_if
from src.price_what_if import get_price_what_if
from src.shop_history import LATEST_MONTH

# A discount band shown fewer times than this is too thin to act on (ADR 0042).
THIN_BELOW_SHOWINGS = 30
LISTED = 10                    # rows of a list a tool returns; the view has the rest

PRODUCT_FIELDS = ["sku", "name", "brand", "category", "pet_type", "price_eur", "avg_rating"]


@dataclass(frozen=True)
class AskTool:
    name: str
    description: str
    input_schema: dict
    run: Callable[[dict], dict]

    def definition(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


def _schema(**properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


SKU = {"type": "string", "description": "A product's SKU, e.g. SKU-PT-0563 (find it with find_products)"}


def build_tools(reader: AitoClient, supply: Callable[[], dict], retention: Callable[[], dict]) -> list[AskTool]:
    """The tools, over `reader` (PetNord's database or a sandbox branch) and the two snapshot views."""

    def find_products(args: dict) -> dict:
        hits = reader.search("products", where={"name": {"$match": args["text"]}}, limit=LISTED,
                             select=PRODUCT_FIELDS)["hits"]
        return {"products": hits, "listed": len(hits)}

    def offer_what_if(args: dict) -> dict:
        what_if = get_discount_what_if(reader, args["sku"], LATEST_MONTH).to_dict()
        bands = [{**b, "thin": b["shown"] < THIN_BELOW_SHOWINGS} for b in what_if["bands"]]
        return {"sku": args["sku"], "name": what_if["name"], "month": what_if["month"],
                "current_band": what_if["current_band"], "bands": bands,
                "thin_rule": f"a band shown under {THIN_BELOW_SHOWINGS} times is thin",
                "view": f"/product/?sku={args['sku']}&tab=what-if"}

    def price_what_if(args: dict) -> dict:
        what_if = get_price_what_if(reader, args["sku"], float(args["price_eur"])).to_dict()
        keep = ("sku", "name", "price_eur", "cost_eur", "units", "revenue_eur", "profit_eur", "below_zero")
        return {**{k: what_if[k] for k in keep}, "view": f"/product/?sku={args['sku']}&tab=what-if"}

    def reorder_queue(_: dict) -> dict:
        view = supply()
        keep = ("sku", "name", "current_stock", "reorder_point", "forecast_units", "order_qty",
                "order_cost_eur", "revenue_at_risk_eur")
        return {"month": view["forecast_month"], "summary": view["reorder"],
                "top": [{k: r[k] for k in keep} for r in view["reorder_queue"][:LISTED]],
                "listed": min(LISTED, len(view["reorder_queue"])), "of": len(view["reorder_queue"]),
                "view": "/supply/"}

    def overstock(_: dict) -> dict:
        view = supply()
        keep = ("sku", "name", "current_stock", "excess_units", "tied_capital_eur")
        return {"summary": view["overstock_decision"],
                "top": [{k: r[k] for k in keep} for r in view["overstock"][:LISTED]],
                "listed": min(LISTED, len(view["overstock"])), "of": len(view["overstock"]),
                "view": "/supply/"}

    def at_risk_customers(_: dict) -> dict:
        view = retention()
        keep = ("customer_id", "name", "pets", "risk", "spend_12m_eur", "last_order_month")
        top = [{**{k: r[k] for k in keep}, "offer": r["offer"] and {k: r["offer"][k] for k in ("name", "expected_return_eur")}}
               for r in view["at_risk"][:LISTED]]
        return {"as_of_month": view["as_of_month"], "decision": view["decision"], "counts": view["counts"],
                "top": top, "listed": len(top), "of": len(view["at_risk"]), "view": "/retention/"}

    return [
        AskTool("find_products", "Find products whose name holds the words. Returns SKU, name, brand, category, price, stars.",
                _schema(text={"type": "string", "description": "Words from the product's name"}), find_products),
        AskTool("offer_what_if", "A product's chance of being bought when shown, per discount band (none, 10-15, 15-20, 20+), "
                "with the band's lift (shop-wide) and the product's own, and how often it was shown and bought per band. "
                "A band marked thin has too little evidence.", _schema(sku=SKU), offer_what_if),
        AskTool("price_what_if", "Next month's units, revenue and profit for a product at a price, from a regression on "
                "its sales and price.", _schema(sku=SKU, price_eur={"type": "number", "description": "A price in euros"}),
                price_what_if),
        AskTool("reorder_queue", "The products to reorder now: stock, forecast, order quantity and cost, and the "
                "revenue at risk without the order.", _schema(), reorder_queue),
        AskTool("overstock", "The overstocked products: excess units and tied-up capital, with the total.", _schema(), overstock),
        AskTool("at_risk_customers", "The customers most likely to stop ordering, most valuable first, with their "
                "last-12-month spend and the best win-back offer.", _schema(), at_risk_customers),
    ]
