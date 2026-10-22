"""A business buyer's next order, drafted by Aito, on real data (ADR 0034).

One `_predict` per buyer, the exact query Aito core benchmarked on UCI
Online Retail II:

    {"from": "lines", "where": {"invoice.customer_id": id},
     "predict": "code", "limit": 10, "select": ["$p", "$value"]}

`lines` holds one row per (invoice, StockCode) before 2011-09-01, and
`invoice.customer_id` reaches through the `lines.invoice` link to the
invoice's buyer. So the ranking is P(code | a line of this buyer's): the
buyer's own history, plus what buyers like them ordered.

The draft is then set against what the buyer really ordered next (their
first invoice on or after the cutoff, which Aito never saw). The first
line's mark is the benchmark's hit@1 for this buyer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.uci_outcomes import BuyerOutcome, load_outcomes
from src.uci_products import lookup_products

DRAFT_LENGTH = 10


class UnknownBuyerError(LookupError):
    """The customer id has no invoice before the cutoff, so Aito has no history for them."""


@dataclass(frozen=True)
class DraftLine:
    code: str
    description: str
    probability: float        # Aito's $p for this code
    last_price_gbp: float
    ordered_next: bool        # in the buyer's next order (Aito never saw it)


@dataclass(frozen=True)
class DraftOrder:
    customer_id: str
    prior_invoices: int
    lines: list[DraftLine]
    draft_value_gbp: float    # the lines' last prices, one unit each
    next_order_date: str | None
    next_order_size: int      # distinct codes in the next order; 0 if none
    query: dict

    @property
    def top_suggestion_ordered(self) -> bool:
        """The benchmark's hit@1: was the first line in the next order?"""
        return bool(self.lines) and self.lines[0].ordered_next

    def to_dict(self) -> dict:
        return {**asdict(self), "top_suggestion_ordered": self.top_suggestion_ordered}


def draft_query(customer_id: str, limit: int = DRAFT_LENGTH) -> dict:
    """The `_predict` body, exactly as sent, for the page's query panel."""
    return {"from": "lines", "where": {"invoice.customer_id": customer_id},
            "predict": "code", "limit": limit, "select": ["$p", "$value"]}


def predicted_codes(client: AitoClient, customer_id: str, limit: int = DRAFT_LENGTH) -> list[tuple[str, float]]:
    """(code, $p) pairs, most probable first."""
    body = draft_query(customer_id, limit)
    response = client.predict_rows(body["from"], body["predict"], where=body["where"],
                                   limit=body["limit"], select=body["select"])
    hits = response["hits"]
    if not hits:
        raise AitoError(f"_predict returned no codes for customer {customer_id}: {response}")
    # The value is in `$value` because the query selects it by that name.
    for hit in hits:
        if "$value" not in hit or "$p" not in hit:
            raise AitoError(f"_predict hit for customer {customer_id} lacks $value or $p: {hit}")
    return [(hit["$value"], float(hit["$p"])) for hit in hits]


def draft_order(client: AitoClient, customer_id: str, limit: int = DRAFT_LENGTH) -> DraftOrder:
    outcome = _outcome(customer_id)
    codes = predicted_codes(client, customer_id, limit)
    products = lookup_products(client, [code for code, _ in codes])
    ordered = outcome.next_order.codes if outcome.next_order else frozenset()
    lines = [
        DraftLine(code=code, description=products[code].description, probability=round(p, 4),
                  last_price_gbp=products[code].last_price_gbp, ordered_next=code in ordered)
        for code, p in codes
    ]
    return DraftOrder(
        customer_id=customer_id,
        prior_invoices=outcome.prior_invoices,
        lines=lines,
        draft_value_gbp=round(sum(line.last_price_gbp for line in lines), 2),
        next_order_date=outcome.next_order.date if outcome.next_order else None,
        next_order_size=len(ordered),
        query=draft_query(customer_id, limit),
    )


def _outcome(customer_id: str) -> BuyerOutcome:
    outcome = load_outcomes().get(customer_id)
    if outcome is None:
        raise UnknownBuyerError(f"No customer {customer_id!r} with an order before 2011-09-01")
    return outcome
