"""What a wholesaler's buyers order with a product: `_relate` over `baskets`.

The pet shop's Bought Together pattern (cheatsheet: "Order-level
co-occurrence" and "A Text column of SKUs"), on UCI's training invoices:

    {"from": "baskets", "where": {"codes": {"$match": "85123A"}},
     "relate": ["codes"], "limit": 50}

`baskets.codes` is an invoice's StockCodes as whitespace-separated
tokens, so each hit is another code, its lift (how much more often it is
on an invoice holding the chosen code than on any invoice) and the counts
behind it (`fs`).

To be probed on env `uci` before merge: that hits read as
`related.codes.$has` with the code's case kept, and which hits a limit of
50 returns out of the ~4,400 codes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.aito_client import AitoClient
from src.aito_compat import related_value
from src.uci_products import Product, find_product, lookup_products
from src.uci_tables import basket_token, code_of_token

RELATE_LIMIT = 50
# A lift on a handful of invoices is noise (the cheatsheet's Basket Rules
# gate is the same idea), so a code must share this many invoices.
MIN_SHARED_INVOICES = 20
SHOWN = 10


@dataclass(frozen=True)
class BoughtWith:
    code: str
    description: str
    lift: float
    shared_invoices: int      # fOnCondition: invoices holding both codes
    invoices_with_code: int   # f: invoices holding this code


@dataclass(frozen=True)
class BoughtTogether:
    product: Product
    invoices_with_product: int    # fCondition: invoices holding the chosen code
    bought_with: list[BoughtWith]
    query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def bought_together_query(code: str) -> dict:
    return {"from": "baskets", "where": {"codes": {"$match": basket_token(code)}},
            "relate": ["codes"], "limit": RELATE_LIMIT}


def bought_together(client: AitoClient, code: str) -> BoughtTogether:
    product = find_product(client, code)
    body = bought_together_query(code)
    hits = client.relate(body["from"], body["where"], body["relate"], limit=body["limit"])["hits"]

    anchor = basket_token(code)
    others = [h for h in hits if related_value(h, "codes") != anchor]   # the code itself, lift 1/p
    if len(others) == len(hits):
        raise ValueError(f"_relate for {code} has no hit for the code itself: the $match "
                         f"and the tokens disagree. First hit: {hits[:1]}")
    common = [h for h in others if h["fs"]["fOnCondition"] >= MIN_SHARED_INVOICES]
    common.sort(key=lambda h: h["lift"], reverse=True)
    shown = common[:SHOWN]

    codes = [code_of_token(related_value(h, "codes")) for h in shown]
    products = lookup_products(client, codes) if codes else {}
    return BoughtTogether(
        product=product,
        invoices_with_product=hits[0]["fs"]["fCondition"],
        bought_with=[
            BoughtWith(code=c, description=products[c].description, lift=round(float(h["lift"]), 2),
                       shared_invoices=h["fs"]["fOnCondition"], invoices_with_code=h["fs"]["f"])
            for c, h in zip(codes, shown)
        ],
        query=body,
    )
