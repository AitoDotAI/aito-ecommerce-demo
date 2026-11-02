"""How good is the Demand forecast? A time split, judged against naive.

A forecast is only worth showing if it beats the rule every planner
already uses: "next month will look like last month". So the page reports
three numbers on the SAME held-out rows (see ADR 0014 §Correction):

  - model    — Aito predicting the month's sales range from last month's
               range plus the product profile;
  - naive    — "this month lands in last month's range";
  - majority — always the most common range (Aito's `baseAccuracy`).

The split is by time: each test month is scored by a model trained ONLY on the
months before it (`{"month": {"$lt": m}}`), so nothing from the future leaks
in, and the score is pooled over the last TEST_MONTHS months so one noisy
month does not decide it (ADR 0061).

Ranges, not exact units, because `_evaluate` scores classification. The
right score for a numeric forecast is the error size against naive; the
engine documents `_evaluate` over `estimate` but v2.10.3 rejects it, so
this is the interim design and the page says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.aito_client import AitoClient

# What drives a month's sales and is known before it: last month's range, the
# season, the category, and the product's state through its link (the stars
# band its reviews so far give it, and its age: new or not). `month` is left
# out: a test month is a value no training row has, so it would carry no
# evidence. `product_sku` and the state's own id are left out too: each value
# is unique to a product or product-month, so it only dilutes the evidence
# (scripts/supply_drivers_backtest.py, ADR 0061).
_FEATURES = ("units_last_month_bucket", "season", "category",
             "product_state.rating_band", "product_state.age")
TEST_MONTHS = 7

# Says what is scored: Aito predicting the month's sales RANGE. That is
# not the `_estimate` forecast in the page's table, which `_evaluate`
# cannot score yet (see the module docstring).
METHOD = ("Scores Aito predicting each month's sales range (0, 1, 2-3, 4-7, "
          "8-15, 16-31, 32+) from last month's range, the season, the category "
          "and the product's stars band and age, not the unit forecast in the "
          "table. Time split: each of the {months} months up to {test_month} is "
          "tested by a model trained only on the months before it; the scores "
          "are pooled.")


@dataclass(frozen=True)
class EvalSummary:
    accuracy: float          # model: share of test rows in the right range
    naive_accuracy: float    # "same range as last month" on the same rows
    base_accuracy: float     # always the most common range
    n: int                   # test rows, pooled over the months
    method: str
    months: int = 1          # how many test months the scores pool


def evaluate_demand(client: AitoClient, test_month: str) -> EvalSummary:
    """One test month, scored by a model trained on the months before it."""
    train = {"month": {"$lt": test_month}}
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
        method=METHOD.format(test_month=test_month, months=1),
    )


def evaluate_demand_months(client: AitoClient, last_month: str, months: int = TEST_MONTHS) -> EvalSummary:
    """`months` test months ending at `last_month`, each on its own time split, with the scores pooled by rows."""
    scored = [evaluate_demand(client, m) for m in months_up_to(last_month, months)]
    n = sum(e.n for e in scored)
    pooled = lambda field: round(sum(getattr(e, field) * e.n for e in scored) / n, 4)
    return EvalSummary(accuracy=pooled("accuracy"), naive_accuracy=pooled("naive_accuracy"), base_accuracy=pooled("base_accuracy"), n=n,
                       method=METHOD.format(test_month=last_month, months=months), months=months)


def months_up_to(last_month: str, count: int) -> list[str]:
    """The `count` months ending at `last_month`, oldest first."""
    year, month = map(int, last_month.split("-"))
    index = year * 12 + month - 1
    return [f"{(i // 12)}-{i % 12 + 1:02d}" for i in range(index - count + 1, index + 1)]


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
