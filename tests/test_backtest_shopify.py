"""Reading a Shopify orders export for the reorder backtest (ADR 0036).

Each test writes a small export by hand, in Shopify's layout: one row per
line item, with the order's own fields left blank on its later rows.
"""

from __future__ import annotations

import csv
import json

import pytest

from src.backtest_prepared import load_prepared, prepare_shopify
from src.backtest_shopify import SALT_VARIABLE, customer_hash, read_shopify_export

HEADER = ["Name", "Email", "Financial Status", "Created at", "Lineitem quantity", "Lineitem name",
          "Lineitem sku", "Cancelled at", "Total"]


@pytest.fixture(autouse=True)
def salt(monkeypatch):
    monkeypatch.setenv(SALT_VARIABLE, "test-salt-not-a-secret")


def line(name, sku, *, email="", status="", created="", quantity="1", item="", cancelled="") -> dict:
    """A line item row; order-level fields default to blank, as on Shopify's later rows."""
    return {"Name": name, "Email": email, "Financial Status": status, "Created at": created,
            "Lineitem quantity": quantity, "Lineitem name": item or f"Product {sku}", "Lineitem sku": sku,
            "Cancelled at": cancelled, "Total": ""}


def order(name, email, created, *skus, status="paid", cancelled="") -> list[dict]:
    first, *rest = skus
    return ([line(name, first, email=email, status=status, created=created, cancelled=cancelled)]
            + [line(name, sku) for sku in rest])


def export(tmp_path, rows, header=HEADER):
    path = tmp_path / "orders_export.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_an_export_becomes_orders_keyed_by_a_salted_hash_of_the_email(tmp_path):
    path = export(tmp_path, order("#1001", "Anna@Example.com", "2024-03-05 10:12:00 +0200", "SKU-1", "SKU-2"))

    orders = read_shopify_export(path)

    (only,) = orders.invoices.values()
    assert only.codes == frozenset({"SKU-1", "SKU-2"})          # later rows inherit the order's fields
    assert only.date == "2024-03-05"
    assert only.customer_id == customer_hash("anna@example.com", b"test-salt-not-a-secret")
    assert "anna" not in only.customer_id.lower()


def test_dropped_rows_are_counted_by_reason_never_silently(tmp_path):
    path = export(tmp_path, [
        *order("#1001", "a@x.com", "2024-03-05 10:12:00 +0200", "S1", "S2", cancelled="2024-03-06 09:00:00 +0200"),
        *order("#1002", "a@x.com", "2024-03-07 10:12:00 +0200", "S1", status="refunded"),
        line("#1003", "S1", email="b@x.com", status="paid", created="2024-03-08 10:00:00 +0200", quantity="0"),
        line("#1003", "S2"),
        *order("#1004", "", "2024-03-09 10:00:00 +0200", "S3"),        # guest checkout
    ])

    orders = read_shopify_export(path)

    assert orders.dropped_rows == {"cancelled order": 2, "fully refunded": 1, "zero quantity": 1,
                                   "no customer (guest checkout)": 1}
    assert list(orders.invoices) == ["#1003"] and orders.invoices["#1003"].codes == frozenset({"S2"})


def test_a_line_without_a_sku_is_coded_by_its_name_and_counted(tmp_path):
    rows = order("#1001", "a@x.com", "2024-03-05 10:12:00 +0200", "S1", "")
    rows[1]["Lineitem name"] = "Gift wrap"

    orders = read_shopify_export(export(tmp_path, rows))

    assert orders.invoices["#1001"].codes == frozenset({"S1", "Gift wrap"})
    assert orders.notes == {"code from Lineitem name (no SKU)": 1}


def test_a_file_missing_a_column_is_refused_and_the_column_named(tmp_path):
    header = [column for column in HEADER if column != "Lineitem quantity"]
    path = export(tmp_path, order("#1001", "a@x.com", "2024-03-05 10:12:00 +0200", "S1"), header)

    with pytest.raises(ValueError, match="'Lineitem quantity'"):
        read_shopify_export(path)


def test_the_spellings_in_shopifys_documentation_are_accepted_too(tmp_path):
    header = [{"Cancelled at": "Canceled at", "Lineitem sku": "Lineitem SKU"}.get(c, c) for c in HEADER]
    rows = [{{"Cancelled at": "Canceled at", "Lineitem sku": "Lineitem SKU"}.get(k, k): v for k, v in row.items()}
            for row in order("#1001", "a@x.com", "2024-03-05 10:12:00 +0200", "S1")]

    assert read_shopify_export(export(tmp_path, rows, header)).invoices["#1001"].codes == frozenset({"S1"})


def test_an_order_whose_lines_disagree_on_customer_or_date_stops_the_adapter(tmp_path):
    rows = order("#1001", "a@x.com", "2024-03-05 10:12:00 +0200", "S1", "S2")
    rows[1]["Email"] = "someone-else@x.com"

    with pytest.raises(ValueError, match="#1001.*disagree on Email"):
        read_shopify_export(export(tmp_path, rows))


def test_without_a_salt_the_adapter_refuses_to_read_any_address(tmp_path, monkeypatch):
    monkeypatch.delenv(SALT_VARIABLE)

    with pytest.raises(SystemExit, match=SALT_VARIABLE):
        read_shopify_export(export(tmp_path, order("#1001", "a@x.com", "2024-03-05 10:12:00 +0200", "S1")))


def test_preparing_pins_the_cutoff_and_writes_only_training_orders_for_aito(tmp_path):
    rows = [row for n, day in enumerate(["01-05", "02-05", "03-05", "04-05"], start=1)
            for row in order(f"#100{n}", "a@x.com", f"2024-{day} 10:00:00 +0200", f"S{n}")]
    path = export(tmp_path, rows)

    dataset = prepare_shopify(path, "acme", root=tmp_path / "backtest")

    assert dataset.cutoff == "2024-03-01"                       # 3rd of 4 order dates: March
    stored = tmp_path / "backtest" / "acme"
    assert [row["invoice"] for row in json.loads((stored / "invoices.json").read_text())] == ["#1001", "#1002"]
    assert json.loads((stored / "split.json").read_text())["cutoff"] == "2024-03-01"
    assert load_prepared("acme", root=tmp_path / "backtest") == dataset


def test_preparing_again_from_a_different_export_is_refused(tmp_path):
    path = export(tmp_path, order("#1001", "a@x.com", "2024-01-05 10:00:00 +0200", "S1")
                  + order("#1002", "a@x.com", "2024-03-05 10:00:00 +0200", "S2"))
    prepare_shopify(path, "acme", root=tmp_path / "backtest")
    path.write_text(path.read_text() + "#1003,a@x.com,paid,2024-04-01 10:00:00 +0200,1,P,S3,,\n")

    with pytest.raises(SystemExit, match="pins export_md5"):
        prepare_shopify(path, "acme", root=tmp_path / "backtest")
