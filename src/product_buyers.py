"""Product › For whom: which households buy this product more than others.

One `_relate` per declared customer field (ADR 0033: what a household
told the shop, and where it lives), over the product's order lines,
two links away. Fired in parallel: `_batch` runs its items one after
another on the server.

Each lift is a ratio of shares with no interval, so the page shows the
counts beside it and greys a lift on few lines. The Shop's shopper whose
declared profile matches the clearest lifts gets a "see it as this
shopper" link (ADR 0041).
"""

from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from src.aito_client import AitoClient, AitoError
from src.aito_compat import related_value
from src.shop_personas import SHOPPERS

CUSTOMERS_FILE = Path(__file__).resolve().parent.parent / "data" / "customers.json"

BUYER_FIELDS = [
    "order_id.customer_id.pets", "order_id.customer_id.dog_size",
    "order_id.customer_id.diet", "order_id.customer_id.region",
]

# A lift on fewer lines than this is shown, but ranked after the rest and
# never used for the shopper link: Aito smooths thin counts toward 1, and
# a few lines are not a finding.
MIN_SUPPORT_LINES = 10
# Within this of 1, a lift is "no difference" (the Churn drivers' band).
# Compared at two decimals, as shown: 0.85× is no difference.
NO_DIFFERENCE = 0.15
# Higher than any customer field's number of values, so a full page of
# hits means values may have been cut off.
RELATE_LIMIT = 50


@dataclass(frozen=True)
class BuyerRow:
    field: str             # "order_id.customer_id.pets", ...
    value: str             # "dog"
    lift: float            # share among this product's lines / share among all lines
    lines: int             # this product's order lines with this profile
    lines_total: int       # this product's order lines

    @property
    def is_clear(self) -> bool:
        return self.lines >= MIN_SUPPORT_LINES and round(abs(self.lift - 1.0), 2) > NO_DIFFERENCE


@dataclass(frozen=True)
class ShopperLink:
    """A Shop shopper whose declared profile matches the clearest lifts."""
    key: str               # /shop/?shopper=<key>
    name: str
    matches: list[str]     # the matched profile values, clearest first: ["dog", "large"]


def buyers_relate_body(sku: str, field: str) -> dict:
    # Aito's `_relate`: with the product as the condition, each hit's lift
    # is how much more common `field`'s value is among this product's
    # order lines than among all order lines.
    return {"from": "order_lines", "where": {"product_sku": sku}, "relate": field}


def get_buyers(client: AitoClient, sku: str) -> list[BuyerRow]:
    """Every value of every buyer field, well-supported lifts furthest from
    1 first."""
    with ThreadPoolExecutor(max_workers=len(BUYER_FIELDS)) as pool:
        rows = [row for rows in pool.map(lambda f: _buyer_rows(client, sku, f), BUYER_FIELDS) for row in rows]
    return sorted(rows, key=lambda b: (b.lines < MIN_SUPPORT_LINES, -abs(b.lift - 1.0)))


def _buyer_rows(client: AitoClient, sku: str, field: str) -> list[BuyerRow]:
    body = buyers_relate_body(sku, field)
    hits = client.relate(table=body["from"], where=body["where"], relate_field=field, limit=RELATE_LIMIT)["hits"]
    if len(hits) == RELATE_LIMIT:
        raise AitoError(f"{sku}: _relate {field} returned {RELATE_LIMIT} values, so some may have been cut off")
    return [
        BuyerRow(
            field=field,
            value=str(related_value(hit, field)),
            lift=round(float(hit["lift"]), 2),
            lines=int(hit["fs"]["fOnCondition"]),
            lines_total=int(hit["fs"]["fCondition"]),
        )
        for hit in hits
    ]


def shopper_for(buyers: list[BuyerRow]) -> ShopperLink | None:
    """The Shop shopper whose declared profile the clear lifts favour most:
    the sum of log-lifts over the rows their profile matches. None when no
    shopper matches more over- than under-represented values."""
    clear = [b for b in buyers if b.is_clear]
    best: tuple[float, ShopperLink] | None = None
    for shopper, profile in _shopper_profiles().items():
        matched = [b for b in clear if b.value in profile.get(b.field.rsplit(".", 1)[1], set())]
        score = sum(math.log(b.lift) for b in matched)
        if score > 0 and (best is None or score > best[0]):
            matches = [b.value for b in sorted(matched, key=lambda b: -b.lift)]
            best = (score, ShopperLink(shopper.key, shopper.name, matches))
    return best[1] if best else None


def _shopper_profiles() -> dict:
    """What each Shop shopper declared, as sets of values per customer
    field. `pets` is a Text field ("dog cat"): `_relate` answers per word."""
    customers = {c["customer_id"]: c for c in json.loads(CUSTOMERS_FILE.read_text())}
    profiles = {}
    for shopper in SHOPPERS:
        c = customers[shopper.customer_id]
        profiles[shopper] = {
            "pets": set(c.get("pets", "").split()),     # most customers declare no pets
            "dog_size": {c["dog_size"]} if c.get("dog_size") else set(),
            "diet": {c["diet"]} if c.get("diet") else set(),
            "region": {c["region"]},
        }
    return profiles
