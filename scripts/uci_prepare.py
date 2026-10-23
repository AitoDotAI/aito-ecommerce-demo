"""Prepare UCI Online Retail II for env `uci`: xlsx in, `data/uci/*.json` out.

    ./do uci-prepare        # UCI_XLSX overrides the xlsx's path

Reads the local copy of the dataset (never downloads), checks it is the
exact file the benchmark used, cleans it as the benchmark did, and writes
one JSON per Aito table plus `outcomes.json` and `new_buyers.json` (the
held-out orders of buyers new after the cutoff; neither is loaded into Aito).
Fails if any count differs from the benchmark's.

Source: Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning
Repository. https://doi.org/10.24432/C5CG6D. Licence CC BY 4.0.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from src.uci_cleaning import clean_lines
from src.uci_outcomes import UCI_DATA_DIR
from src.uci_tables import (
    EXPECTED_COUNTS, aito_rows, basket_rows, group_invoices, new_buyer_orders, outcomes, product_rows,
    split, split_counts,
)
from src.uci_xlsx import read_rows

DEFAULT_XLSX = "~/.tmp/aito-retail-matching/online_retail_II.xlsx"
EXPECTED_MD5 = "ed54ccfc5d358481c399cc11d0a244be"


def main() -> None:
    xlsx = Path(os.path.expanduser(os.environ.get("UCI_XLSX", DEFAULT_XLSX)))
    _check_md5(xlsx)

    print(f"Reading {xlsx} ...")
    lines, cleaning = clean_lines(read_rows(str(xlsx)))
    for reason, count in sorted(cleaning.items()):
        print(f"  {reason:32s} {count:>9,}")

    invoices = group_invoices(lines)
    train, test = split(invoices)
    tables = aito_rows(invoices, train)
    tables["products"] = product_rows(lines)
    tables["baskets"] = basket_rows(invoices, train)

    counts = split_counts(invoices, train, test, tables)
    print("Counts (expected in brackets):")
    for name, count in counts.items():
        print(f"  {name:32s} {count:>9,}  ({EXPECTED_COUNTS[name]:,})")
    if counts != EXPECTED_COUNTS:
        raise SystemExit("Counts differ from the benchmark's; not writing data/uci/.")

    UCI_DATA_DIR.mkdir(parents=True, exist_ok=True)
    held_out = {"outcomes": outcomes(invoices, train, test),
                "new_buyers": new_buyer_orders(invoices, train, test)}
    for name, rows in {**tables, **held_out}.items():
        path = UCI_DATA_DIR / f"{name}.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(rows, fh)
        print(f"  wrote {path} ({len(rows):,} rows)")


def _check_md5(xlsx: Path) -> None:
    if not xlsx.exists():
        raise SystemExit(f"{xlsx} not found. Set UCI_XLSX to the Online Retail II xlsx.")
    digest = hashlib.md5(xlsx.read_bytes()).hexdigest()
    if digest != EXPECTED_MD5:
        raise SystemExit(f"{xlsx} has md5 {digest}, not the benchmark's {EXPECTED_MD5}.")


if __name__ == "__main__":
    main()
