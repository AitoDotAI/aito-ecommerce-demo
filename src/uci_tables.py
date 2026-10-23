"""Turn the cleaned UCI lines into the rows loaded into Aito, and the outcomes.

The split is the benchmark's: invoices dated before TRAIN_BEFORE are the
training data and are loaded; later invoices are held out. For each
buyer, the first held-out invoice is "their next order", the basket the
benchmark scored Aito's top suggestion against (`retail2_run.targets`).

Row shapes and ids follow Aito core's loader (`retail2_aito.load_db`)
byte for byte, so the env reproduces the benchmark's numbers.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from src.uci_cleaning import CleanLine

TRAIN_BEFORE = "2011-09-01"

# What the benchmark reports for this file. uci_prepare and uci_load
# assert them: a different count means a different dataset, and the
# demo's 31 % would no longer be the benchmark's.
EXPECTED_COUNTS = {
    "invoices": 36_975,               # all, before the split
    "customers": 5_881,               # all, before the split
    "train invoices": 29_854,         # loaded
    "lines": 603_034,                 # loaded: one per (training invoice, code)
    "test invoices": 7_121,           # held out
    "scored customers": 2_974,        # with at least one held-out invoice
    "scored with 1-2 prior invoices": 636,
    "scored with 0 prior invoices": 630,  # new buyers: the backtest's 0 slice (ADR 0036)
}


@dataclass(frozen=True)
class Invoice:
    invoice: str
    customer_id: str
    date: str
    codes: frozenset[str]     # a set: a code on two lines of one invoice counts once


def group_invoices(lines: list[CleanLine]) -> dict[str, Invoice]:
    codes: dict[str, set[str]] = defaultdict(set)
    header: dict[str, tuple[str, str]] = {}
    for line in lines:
        seen = header.setdefault(line.invoice, (line.customer_id, line.date))
        if seen != (line.customer_id, line.date):
            raise ValueError(f"Invoice {line.invoice} has lines for {seen} and "
                             f"{(line.customer_id, line.date)}")
        codes[line.invoice].add(line.code)
    return {i: Invoice(i, *header[i], frozenset(codes[i])) for i in header}


def split(invoices: dict[str, Invoice]) -> tuple[list[str], list[str]]:
    """Training and held-out invoice ids, each sorted (the loader's row order)."""
    train = sorted(i for i, inv in invoices.items() if inv.date < TRAIN_BEFORE)
    test = sorted(i for i, inv in invoices.items() if inv.date >= TRAIN_BEFORE)
    return train, test


def aito_rows(invoices: dict[str, Invoice], train: list[str]) -> dict[str, list[dict]]:
    """`customers`, `invoices` and `lines`: the benchmark's training data."""
    lines = []
    for invoice_id in train:
        for code in sorted(invoices[invoice_id].codes):
            lines.append({"line_id": f"L{len(lines) + 1:07d}", "invoice": invoice_id, "code": code})
    return {
        "customers": [{"customer_id": c} for c in sorted({invoices[i].customer_id for i in train})],
        # `month` is the date's "YYYY-MM": evidence the benchmark's Aito
        # used. A full date, or no month, measures a different model.
        "invoices": [{"invoice": i, "customer_id": invoices[i].customer_id,
                      "month": invoices[i].date[:7]} for i in train],
        "lines": lines,
    }


def product_rows(lines: list[CleanLine]) -> list[dict]:
    """One row per code sold in the training period: its most frequent
    description (ties: alphabetically first) and its unit price on its
    latest training line (ties within a timestamp: the later row)."""
    descriptions: dict[str, Counter] = defaultdict(Counter)
    latest: dict[str, CleanLine] = {}
    for line in lines:
        if line.date >= TRAIN_BEFORE:
            continue
        if line.description:
            descriptions[line.code][line.description] += 1
        if line.code not in latest or line.timestamp >= latest[line.code].timestamp:
            latest[line.code] = line
    return [
        {"code": code,
         "description": _most_frequent(descriptions[code], code),
         "last_price_gbp": round(latest[code].price_gbp, 2)}
        for code in sorted(latest)
    ]


def basket_rows(invoices: dict[str, Invoice], train: list[str]) -> list[dict]:
    """One row per training invoice, its codes as one Text value, for `_relate`."""
    return [{"invoice": i, "customer_id": invoices[i].customer_id, "month": invoices[i].date[:7],
             "codes": " ".join(sorted(basket_token(c) for c in invoices[i].codes))}
            for i in train]


def basket_token(code: str) -> str:
    """A code as one whitespace-free token. One code, "BANK CHARGES", holds
    a space, which the Text analyzer would split into two tokens."""
    if "_" in code:
        raise ValueError(f"StockCode {code!r} holds '_', which basket tokens use for spaces")
    return code.replace(" ", "_")


def code_of_token(token: str) -> str:
    return token.replace("_", " ")


def outcomes(invoices: dict[str, Invoice], train: list[str], test: list[str]) -> dict[str, dict]:
    """Per training customer: their count of training invoices, and their
    next order (the first held-out invoice; ties on the date go to the
    lowest invoice id, as in the benchmark), or None if they never returned."""
    prior = Counter(invoices[i].customer_id for i in train)
    next_order = _first_held_out_invoices(invoices, test)
    return {
        customer: {
            "prior_invoices": count,
            "next_order": _order_row(next_order[customer]) if customer in next_order else None,
        }
        for customer, count in sorted(prior.items())
    }


def new_buyer_orders(invoices: dict[str, Invoice], train: list[str], test: list[str]) -> dict[str, dict]:
    """The first held-out invoice of each buyer with NO training invoice.

    `outcomes` covers only the customers loaded into Aito; the backtest
    (ADR 0036) also scores these buyers, its "0 prior orders" slice."""
    known = {invoices[i].customer_id for i in train}
    first = _first_held_out_invoices(invoices, test)
    return {customer: _order_row(first[customer]) for customer in sorted(first) if customer not in known}


def _first_held_out_invoices(invoices: dict[str, Invoice], test: list[str]) -> dict[str, Invoice]:
    """Per buyer, their first invoice in `test` (sorted ids): on a tied date
    the lowest id wins, as in the benchmark's `retail2_run.targets`."""
    first: dict[str, Invoice] = {}
    for invoice_id in test:
        inv = invoices[invoice_id]
        if inv.customer_id not in first or inv.date < first[inv.customer_id].date:
            first[inv.customer_id] = inv
    return first


def _order_row(invoice: Invoice) -> dict:
    return {"invoice": invoice.invoice, "date": invoice.date, "codes": sorted(invoice.codes)}


def split_counts(invoices: dict[str, Invoice], train: list[str], test: list[str],
                 rows: dict[str, list[dict]]) -> dict[str, int]:
    """The counts EXPECTED_COUNTS pins, computed from the prepared data."""
    prior = Counter(invoices[i].customer_id for i in train)
    scored = {invoices[i].customer_id for i in test}
    return {
        "invoices": len(invoices),
        "customers": len({inv.customer_id for inv in invoices.values()}),
        "train invoices": len(train),
        "lines": len(rows["lines"]),
        "test invoices": len(test),
        "scored customers": len(scored),
        "scored with 1-2 prior invoices": sum(1 for c in scored if 1 <= prior[c] <= 2),
        "scored with 0 prior invoices": sum(1 for c in scored if prior[c] == 0),
    }


def _most_frequent(counter: Counter, code: str) -> str:
    if not counter:
        raise ValueError(f"StockCode {code} has no description on any training line")
    top = max(counter.values())
    return min(d for d, n in counter.items() if n == top)
