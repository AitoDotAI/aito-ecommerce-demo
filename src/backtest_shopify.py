"""Read a Shopify orders export (Admin → Orders → Export, CSV) into orders (ADR 0036).

One CSV row per line item. Order = `Name`; customer = `Email`, hashed with
a secret salt before anything is kept; date = `Created at`; code =
`Lineitem sku`, or `Lineitem name` when the SKU is empty (counted); a
basket is the set of its codes.

Shopify's documentation spells two headers differently from many real
exports: `Canceled at` and `Lineitem SKU`. Both spellings are accepted;
a file with neither refuses, naming the column.

Shopify leaves many fields blank on an order's second and later rows
("Many of the fields are left blank to indicate that multiple items were
purchased on the same order", help.shopify.com, Exporting orders). So for
the order-level fields a blank on a later row inherits the order's first
row; a different non-blank value stops the adapter.

Dropped rows are counted by reason, never dropped silently.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.uci_tables import Invoice

SALT_VARIABLE = "BACKTEST_EMAIL_SALT"

# Our name → the spellings accepted in the header.
COLUMNS = {
    "Name": ("Name",),
    "Email": ("Email",),
    "Created at": ("Created at",),
    "Financial Status": ("Financial Status",),
    "Cancelled at": ("Cancelled at", "Canceled at"),
    "Lineitem quantity": ("Lineitem quantity",),
    "Lineitem name": ("Lineitem name",),
    "Lineitem sku": ("Lineitem sku", "Lineitem SKU"),
}
ORDER_FIELDS = ("Email", "Created at", "Financial Status", "Cancelled at")


@dataclass(frozen=True)
class ShopifyOrders:
    invoices: dict[str, Invoice]       # the kept orders; customer ids are salted hashes
    dropped_rows: Counter              # rows, by reason
    notes: Counter                     # kept rows worth knowing about


def read_shopify_export(path: Path) -> ShopifyOrders:
    salt = _salt()
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = _resolve_columns(reader.fieldnames or [], path)
        rows = [{ours: raw[theirs].strip() for ours, theirs in columns.items()} for raw in reader]

    first_rows: dict[str, dict] = {}
    codes: dict[str, set[str]] = {}
    dropped, notes = Counter(), Counter()
    for row in rows:
        order = row["Name"]
        if not order:
            raise ValueError(f"{path}: a row has no Name (order number): {row}")
        first = first_rows.setdefault(order, row)
        _inherit_order_fields(row, first, order)

        reason = _drop_reason(row, order)
        if reason:
            dropped[reason] += 1
            continue
        if not row["Lineitem sku"]:
            if not row["Lineitem name"]:
                raise ValueError(f"Order {order}: a line item has neither a SKU nor a name")
            notes["code from Lineitem name (no SKU)"] += 1
        codes.setdefault(order, set()).add(row["Lineitem sku"] or row["Lineitem name"])

    invoices = {
        order: Invoice(order, customer_hash(first_rows[order]["Email"], salt),
                       _order_date(first_rows[order]["Created at"], order), frozenset(order_codes))
        for order, order_codes in codes.items()
    }
    return ShopifyOrders(invoices, dropped, notes)


def customer_hash(email: str, salt: bytes) -> str:
    """A salted HMAC of the address. Case and outer spaces are ignored, so
    one buyer typing their address differently stays one buyer."""
    return hmac.new(salt, email.strip().lower().encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _salt() -> bytes:
    salt = os.environ.get(SALT_VARIABLE, "")
    if not salt:
        raise SystemExit(f"Refusing: {SALT_VARIABLE} is not set. Set it to a secret of your own "
                         f"(the same one for every export of this shop), never commit it.")
    return salt.encode("utf-8")


def _resolve_columns(header: list[str], path: Path) -> dict[str, str]:
    resolved, missing = {}, []
    for ours, spellings in COLUMNS.items():
        present = [s for s in spellings if s in header]
        if len(present) > 1:
            raise ValueError(f"{path}: the header holds both {present}; which one is meant is unclear")
        if not present:
            missing.append(" or ".join(repr(s) for s in spellings))
            continue
        resolved[ours] = present[0]
    if missing:
        raise ValueError(f"{path} is not a Shopify orders export: no column {', '.join(missing)}")
    return resolved


def _inherit_order_fields(row: dict, first: dict, order: str) -> None:
    for name in ORDER_FIELDS:
        if not row[name]:
            row[name] = first[name]
        elif row[name] != first[name]:
            raise ValueError(f"Order {order}: its line items disagree on {name} "
                             f"({first[name]!r} and {row[name]!r})")


def _drop_reason(row: dict, order: str) -> str | None:
    if row["Cancelled at"]:
        return "cancelled order"
    if row["Financial Status"] == "refunded":
        return "fully refunded"
    try:
        quantity = int(row["Lineitem quantity"])
    except ValueError as exc:
        raise ValueError(f"Order {order}: Lineitem quantity {row['Lineitem quantity']!r} "
                         f"is not a whole number") from exc
    if quantity < 0:
        raise ValueError(f"Order {order}: Lineitem quantity {quantity} is negative")
    if quantity == 0:
        return "zero quantity"
    if not row["Email"]:
        return "no customer (guest checkout)"
    return None


def _order_date(created_at: str, order: str) -> str:
    """The order's date as written in the export (the shop's own time zone)."""
    for parse in (lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z"), datetime.fromisoformat):
        try:
            return parse(created_at).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Order {order}: Created at {created_at!r} is not a date Shopify writes")
