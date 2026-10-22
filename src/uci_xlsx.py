"""Read the rows of UCI Online Retail II's xlsx, with the standard library only.

An xlsx is a zip of XML files: `xl/sharedStrings.xml` holds every text
cell's string once, and each `xl/worksheets/sheetN.xml` holds the rows,
where a text cell (`t="s"`) carries an index into those strings. The file
has two sheets (2009-2010 and 2010-2011), each with its own header row.

Columns: A Invoice, B StockCode, C Description, D Quantity, E InvoiceDate,
F Price, G Customer ID, H Country.

Copied from Aito core's benchmark preparer (retail2_prepare.py), so the
demo reads the file exactly as the benchmark did.
"""

from __future__ import annotations

import datetime
import re
import zipfile
from collections.abc import Iterator
from xml.etree import ElementTree

NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

COLUMNS = {
    "A": "invoice", "B": "stock_code", "C": "description", "D": "quantity",
    "E": "invoice_date", "F": "price", "G": "customer_id", "H": "country",
}


def read_rows(path: str) -> Iterator[dict[str, str]]:
    """Every data row of every sheet, as raw strings keyed by column name.

    Each sheet's first row is its header and is skipped. (An earlier
    harness skipped only the first sheet's, and read the second header as
    data.) A missing cell reads as "".
    """
    with zipfile.ZipFile(path) as archive:
        strings = _shared_strings(archive)
        sheets = sorted(n for n in archive.namelist() if n.startswith("xl/worksheets/sheet"))
        for sheet in sheets:
            cells_by_row = _sheet_rows(archive, sheet, strings)
            next(cells_by_row)          # this sheet's header
            for cells in cells_by_row:
                yield {name: cells.get(letter, "") for letter, name in COLUMNS.items()}


def excel_date(serial: str) -> str:
    """An Excel date serial ("40148.32") as YYYY-MM-DD, or "" if not a number.

    Excel's 1900 date system counts days from 1899-12-30 (one day earlier
    than it says, because of its 1900 leap-year bug).
    """
    try:
        days = float(serial)
    except (TypeError, ValueError):
        return ""
    return (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(days))).isoformat()


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    strings = []
    with archive.open("xl/sharedStrings.xml") as fh:
        for _, element in ElementTree.iterparse(fh, events=("end",)):
            if element.tag == NAMESPACE + "si":
                strings.append("".join(t.text or "" for t in element.iter(NAMESPACE + "t")))
                element.clear()
    return strings


def _sheet_rows(archive: zipfile.ZipFile, sheet: str, strings: list[str]) -> Iterator[dict[str, str]]:
    """One sheet's rows as {column letter: cell text}."""
    with archive.open(sheet) as fh:
        for _, element in ElementTree.iterparse(fh, events=("end",)):
            if element.tag != NAMESPACE + "row":
                continue
            cells = {}
            for cell in element.findall(NAMESPACE + "c"):
                letter = re.match(r"[A-Z]+", cell.get("r") or "")
                value = cell.find(NAMESPACE + "v")
                text = "" if value is None or value.text is None else value.text
                if text and cell.get("t") == "s":
                    text = strings[int(text)]
                cells[letter.group(0) if letter else ""] = text
            yield cells
            element.clear()
