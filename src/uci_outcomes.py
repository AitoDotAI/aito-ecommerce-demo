"""What each UCI buyer actually ordered next: kept beside the app, never in Aito.

`./do uci-prepare` writes `data/uci/outcomes.json`: for every customer
with an invoice before the cutoff (the customers loaded into Aito), their
count of those invoices and their next order, the first invoice on or
after the cutoff (None if they never ordered again). The Business
reorders page marks which drafted codes were in it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

UCI_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "uci"


@dataclass(frozen=True)
class NextOrder:
    invoice: str
    date: str
    codes: frozenset[str]


@dataclass(frozen=True)
class BuyerOutcome:
    customer_id: str
    prior_invoices: int
    next_order: NextOrder | None


@cache
def load_outcomes() -> dict[str, BuyerOutcome]:
    path = UCI_DATA_DIR / "outcomes.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing. Run `./do uci-prepare` (reads the UCI xlsx, writes data/uci/).")
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return {customer: _outcome(customer, row) for customer, row in raw.items()}


def _outcome(customer_id: str, row: dict) -> BuyerOutcome:
    nxt = row["next_order"]
    return BuyerOutcome(
        customer_id=customer_id,
        prior_invoices=row["prior_invoices"],
        next_order=None if nxt is None else NextOrder(nxt["invoice"], nxt["date"], frozenset(nxt["codes"])),
    )
