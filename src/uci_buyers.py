"""The buyers the Business reorders page offers (ADR 0034).

UCI holds no names, so a buyer is their customer id. The list is chosen
by a fixed rule from the outcomes, not by how well Aito did for them:

- the first FEW_ORDERS_SHOWN customers, by id, with 1-2 invoices before
  the cutoff and a next order after it (the benchmark's claim is about
  these buyers);
- the first REGULARS_SHOWN customers, by id, with REGULAR_MIN_INVOICES or
  more invoices before the cutoff and a next order after it.

A buyer with no next order is left out: the page could not show what
they ordered next.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.uci_outcomes import BuyerOutcome, load_outcomes

FEW_ORDERS_SHOWN = 4
REGULARS_SHOWN = 2
REGULAR_MIN_INVOICES = 6


@dataclass(frozen=True)
class Buyer:
    customer_id: str
    prior_invoices: int
    group: str                # "1-2 earlier orders" or "regular buyer"
    next_order_date: str

    def to_dict(self) -> dict:
        return asdict(self)


def pick_buyers(outcomes: dict[str, BuyerOutcome] | None = None) -> list[Buyer]:
    outcomes = load_outcomes() if outcomes is None else outcomes
    returning = [o for _, o in sorted(outcomes.items()) if o.next_order is not None]
    few = [o for o in returning if 1 <= o.prior_invoices <= 2][:FEW_ORDERS_SHOWN]
    regulars = [o for o in returning if o.prior_invoices >= REGULAR_MIN_INVOICES][:REGULARS_SHOWN]
    return ([_buyer(o, "1-2 earlier orders") for o in few]
            + [_buyer(o, "regular buyer") for o in regulars])


def _buyer(outcome: BuyerOutcome, group: str) -> Buyer:
    return Buyer(outcome.customer_id, outcome.prior_invoices, group, outcome.next_order.date)
