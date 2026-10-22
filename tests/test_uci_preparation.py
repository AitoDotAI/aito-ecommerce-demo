"""Preparing UCI Online Retail II as Aito core's benchmark did (ADR 0034).

The demo quotes the benchmark's number, so these pin the benchmark's
cleaning rules and row shapes on a few hand-written rows. The real file's
counts are asserted by `./do uci-prepare` itself.
"""

from __future__ import annotations

import zipfile

from src.uci_cleaning import clean_lines
from src.uci_tables import (
    aito_rows, basket_rows, basket_token, code_of_token, group_invoices, outcomes, product_rows, split,
)
from src.uci_xlsx import excel_date, read_rows

# Excel serials: 40148 is 2009-12-01; 40787 is 2011-09-01, the cutoff.
DEC_2009, AUG_2011, SEP_2011 = "40148.5", "40786.4", "40787.6"


def row(invoice="489434", code="85048", quantity="12", date=DEC_2009, customer="13085",
        description="LIGHT GARLAND", price="6.95"):
    return {"invoice": invoice, "stock_code": code, "description": description, "quantity": quantity,
            "invoice_date": date, "price": price, "customer_id": customer, "country": "United Kingdom"}


# ── Cleaning ──────────────────────────────────────────────────────


def test_cleaning_drops_credit_notes_guests_and_non_positive_quantities():
    lines, counts = clean_lines([
        row(),
        row(invoice="C489449"),              # a credit note
        row(customer=""),                    # a guest at the till
        row(quantity="0"), row(quantity="-3"), row(quantity="lots"),
        row(code=""), row(date=""),
    ])

    assert [line.invoice for line in lines] == ["489434"]
    assert counts["dropped: credit note"] == 1
    assert counts["dropped: no customer id"] == 1
    assert counts["dropped: quantity not positive"] == 2
    assert counts["dropped: quantity not a number"] == 1
    assert counts["dropped: no invoice, code or date"] == 2


def test_cleaning_keeps_every_stock_code_upper_cased_including_postage():
    lines, _ = clean_lines([row(code=" 85123a "), row(code="POST"), row(code="M")])

    assert [line.code for line in lines] == ["85123A", "POST", "M"]


def test_excel_serials_become_dates_in_the_1900_system():
    assert excel_date("40148.322916666664") == "2009-12-01"
    assert excel_date("") == ""


def test_the_xlsx_reader_skips_each_sheets_own_header(tmp_path):
    # Two sheets, each with a header row, text cells via sharedStrings.
    shared = ('<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<si><t>Invoice</t></si><si><t>GARLAND</t></si></sst>')

    def sheet(invoice: str) -> str:
        return ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
                f'<row r="2"><c r="A2"><v>{invoice}</v></c><c r="C2" t="s"><v>1</v></c>'
                '<c r="G2"><v>13085</v></c></row></sheetData></worksheet>')

    path = tmp_path / "tiny.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet("489434"))
        archive.writestr("xl/worksheets/sheet2.xml", sheet("539993"))

    rows = list(read_rows(str(path)))

    assert [(r["invoice"], r["description"], r["customer_id"], r["quantity"]) for r in rows] == [
        ("489434", "GARLAND", "13085", ""), ("539993", "GARLAND", "13085", "")]


# ── Tables: the benchmark's rows, byte for byte ───────────────────


def prepared(rows):
    lines, _ = clean_lines(rows)
    invoices = group_invoices(lines)
    train, test = split(invoices)
    return lines, invoices, train, test


def test_an_invoices_items_are_a_set_and_lines_are_numbered_in_invoice_then_code_order():
    _, invoices, train, _ = prepared([
        row(invoice="489435", code="22350"),
        row(invoice="489434", code="85048"), row(invoice="489434", code="21232"),
        row(invoice="489434", code="85048"),         # the same code twice: one line
    ])

    tables = aito_rows(invoices, train)

    assert tables["lines"] == [
        {"line_id": "L0000001", "invoice": "489434", "code": "21232"},
        {"line_id": "L0000002", "invoice": "489434", "code": "85048"},
        {"line_id": "L0000003", "invoice": "489435", "code": "22350"},
    ]
    assert tables["customers"] == [{"customer_id": "13085"}]
    assert tables["invoices"][0] == {"invoice": "489434", "customer_id": "13085", "month": "2009-12"}


def test_only_invoices_before_2011_09_01_are_loaded():
    _, invoices, train, test = prepared([row(invoice="1", date=AUG_2011), row(invoice="2", date=SEP_2011)])

    assert (train, test) == (["1"], ["2"])
    assert [i["invoice"] for i in aito_rows(invoices, train)["invoices"]] == ["1"]


def test_a_buyers_next_order_is_their_first_invoice_from_the_cutoff_on():
    _, invoices, train, test = prepared([
        row(invoice="1", code="A", date=DEC_2009),
        row(invoice="2", code="B", date=SEP_2011), row(invoice="3", code="C", date="40800"),
        row(invoice="4", code="D", date=DEC_2009, customer="99999"),   # never returns
    ])

    result = outcomes(invoices, train, test)

    assert result["13085"] == {"prior_invoices": 1,
                               "next_order": {"invoice": "2", "date": "2011-09-01", "codes": ["B"]}}
    assert result["99999"] == {"prior_invoices": 1, "next_order": None}


def test_products_carry_the_most_frequent_description_and_the_latest_training_price():
    lines, _, _, _ = prepared([
        row(invoice="1", description="GARLAND", price="6.95", date="40148.3"),
        row(invoice="2", description="LIGHT GARLAND", price="5.95", date="40500.1"),
        row(invoice="3", description="GARLAND", price="7.25", date="40400.9"),
        row(invoice="4", description="NEW NAME", price="9.99", date=SEP_2011),  # after the cutoff
    ])

    assert product_rows(lines) == [{"code": "85048", "description": "GARLAND", "last_price_gbp": 5.95}]


def test_baskets_hold_each_training_invoices_codes_as_one_token_each():
    _, invoices, train, _ = prepared([row(code="85123A"), row(code="BANK CHARGES"), row(code="22041")])

    assert basket_rows(invoices, train) == [{"invoice": "489434", "customer_id": "13085", "month": "2009-12",
                                             "codes": "22041 85123A BANK_CHARGES"}]
    assert code_of_token(basket_token("BANK CHARGES")) == "BANK CHARGES"
