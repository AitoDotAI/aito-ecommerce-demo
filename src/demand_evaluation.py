"""How good is the Demand forecast? A time split, judged against naive.

A forecast is only worth showing if it beats the rule every planner
already uses: "next month will look like last month". So the page reports
three numbers on the SAME held-out rows (see ADR 0014 §Correction):

  - model    — Aito predicting the month's sales range from last month's
               range plus the product profile;
  - naive    — "this month lands in last month's range";
  - majority — always the most common range (Aito's `baseAccuracy`).

The split is by time: train on every month before the latest, test on
the latest, so the model never learns from the month it predicts.

Ranges, not exact units, because `_evaluate` scores classification. The
right score for a numeric forecast is the error size against naive; the
engine documents `_evaluate` over `estimate` but v2.10.3 rejects it, so
this is the interim design and the page says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.aito_client import AitoClient

# Everything the model may know about a (SKU, month) row except its own
# sales. `month` is left out: the test month is a value no training row
# has, so it would carry no evidence.
_FEATURES = ("units_last_month_bucket", "product_sku", "pet_type",
             "category", "brand", "season")

# Says what is scored: Aito predicting the month's sales RANGE. That is
# not the `_estimate` forecast in the page's table, which `_evaluate`
# cannot score yet (see the module docstring).
METHOD = ("Scores Aito predicting each month's sales range (0, 1, 2-3, 4-7, "
          "8-15, 16-31, 32+) from last month's range and the product, not the "
          "unit forecast in the table. Time split: trained on months before "
          "{test_month}, tested on {test_month}.")


@dataclass(frozen=True)
class EvalSummary:
    accuracy: float          # model: share of test rows in the right range
    naive_accuracy: float    # "same range as last month" on the same rows
    base_accuracy: float     # always the most common range
    n: int
    method: str


def evaluate_demand(client: AitoClient, test_month: str) -> EvalSummary:
    train = {"month": {"$not": test_month}}
    test = {"month": test_month}
    res = client.evaluate(
        table="monthly_sales",
        where={f: {"$get": f} for f in _FEATURES},
        predict_field="units_bucket",
        train=train,
        test=test,
    )
    naive, n_rows = _naive_accuracy(client, test_month)
    assert int(res["n"]) == n_rows, (
        f"Aito evaluated {res['n']} test rows for {test_month} but the naive "
        f"score read {n_rows}; the two numbers would not be comparable")
    return EvalSummary(
        accuracy=round(float(res["accuracy"]), 4),
        naive_accuracy=round(naive, 4),
        base_accuracy=round(float(res["baseAccuracy"]), 4),
        n=n_rows,
        method=METHOD.format(test_month=test_month),
    )


def _naive_accuracy(client: AitoClient, test_month: str) -> tuple[float, int]:
    """Share of the test month's rows whose range equals last month's."""
    res = client.search("monthly_sales", where={"month": test_month},
                        select=["units_bucket", "units_last_month_bucket"],
                        limit=10_000)
    rows = res["hits"]
    assert len(rows) == res["total"], (
        f"read {len(rows)} of {res['total']} rows for {test_month}; raise the limit")
    assert rows, f"no monthly_sales rows for test month {test_month}"
    same = sum(r["units_bucket"] == r["units_last_month_bucket"] for r in rows)
    return same / len(rows), len(rows)
