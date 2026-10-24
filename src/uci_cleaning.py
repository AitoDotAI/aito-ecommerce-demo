"""Clean UCI Online Retail II's raw rows exactly as Aito core's benchmark did.

The demo quotes that benchmark's number, so the rules here are the
benchmark's (retail2_prepare.py), not improvements on them:

- an invoice id starting "C" is a credit note (a cancellation): dropped;
- a non-positive or unparseable quantity: dropped;
- no Customer ID (22 % of rows, guest and till traffic): dropped;
- an empty invoice id, StockCode or date: dropped;
- the StockCode is stripped and upper-cased, and EVERY code is kept,
  including non-products such as "POST" (postage) and "M" (manual).

An invoice's items are a set (see `uci_tables.py`), so a code entered on
two lines of one invoice counts once.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from src.uci_xlsx import excel_date


@dataclass(frozen=True)
class CleanLine:
    invoice: str
    customer_id: str
    date: str                # YYYY-MM-DD
    timestamp: float         # the Excel serial with its time of day, to order lines within a day
    code: str
    description: str
    price_gbp: float


def clean_lines(rows: Iterable[dict[str, str]]) -> tuple[list[CleanLine], Counter]:
    """The kept lines, and a count of rows per reason (seen, dropped, kept)."""
    kept: list[CleanLine] = []
    counts: Counter = Counter()
    for row in rows:
        counts["rows seen"] += 1
        reason = _drop_reason(row)
        if reason:
            counts[reason] += 1
            continue
        kept.append(_clean_line(row))
    counts["lines kept"] = len(kept)
    return kept, counts


def _drop_reason(row: dict[str, str]) -> str | None:
    """Why the benchmark drops this row, or None to keep it. The checks
    run in the benchmark's order, so the per-reason counts match its log."""
    invoice = row["invoice"].strip()
    if invoice.startswith("C"):
        return "dropped: credit note"
    try:
        if float(row["quantity"] or "0") <= 0:
            return "dropped: quantity not positive"
    except ValueError:
        return "dropped: quantity not a number"
    if not row["customer_id"].strip():
        return "dropped: no customer id"
    if not (invoice and row["stock_code"].strip() and excel_date(row["invoice_date"])):
        return "dropped: no invoice, code or date"
    return None


def _clean_line(row: dict[str, str]) -> CleanLine:
    invoice = row["invoice"].strip()
    try:
        price = float(row["price"])
    except ValueError as exc:
        # The benchmark never read the price, so it kept such a row; the
        # demo shows prices, and a kept line without one is a surprise.
        raise ValueError(f"Invoice {invoice}: price {row['price']!r} is not a number") from exc
    return CleanLine(
        invoice=invoice,
        customer_id=row["customer_id"].strip(),
        date=excel_date(row["invoice_date"]),
        timestamp=float(row["invoice_date"]),
        code=row["stock_code"].strip().upper(),
        description=row["description"].strip(),
        price_gbp=price,
    )
