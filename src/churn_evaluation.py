"""How well does Retention's churn score work? A time split, for Evidence.

The question is the one Retention asks (`churn_risk.py`): given a month
in which a customer ordered, is it their last order for three months?
Tested on the orders of LABEL_KNOWN_UNTIL, the latest month whose three
months after are in the data. Trained on orders up to three months
before it, so no training label was settled by months the test can see.

`baseAccuracy` is "every order is followed by another". The old Churn
view's 96 % against 65 % scored random customer-months, including the
months after a customer had already gone, where "no orders" is the label
itself (see `churn_risk.py`).

Shown in Evidence › Model checks (ADR 0037), not in Retention.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.aito_client import AitoClient
from src.churn_risk import LABEL_KNOWN_UNTIL

TRAIN_UNTIL = "2025-10"    # three months before the test month

# The fields `_evaluate` reads off each held-out row: the non-null ones of
# `churn_risk.FEATURES`. Dog size and the latest review are empty on most
# rows, so they are left out here, as in the old Churn `_evaluate`.
_FEATURES = ["pets", "region", "tenure_months_at_month", "visits", "purchases", "spent_eur"]

METHOD = ("Predicts whether a month in which the customer ordered is followed by three months "
          "without an order. Trained on such months up to {train}, tested on every one of {test}.")


@dataclass(frozen=True)
class ChurnCheck:
    accuracy: float
    base_accuracy: float      # "another order follows", the majority answer
    n: int
    method: str
    last_query: dict


def evaluate_churn(client: AitoClient) -> ChurnCheck:
    where = {f: {"$get": f} for f in _FEATURES}
    train = {"month": {"$lte": TRAIN_UNTIL}, "purchases": {"$gte": 1}}
    test = {"month": LABEL_KNOWN_UNTIL, "purchases": {"$gte": 1}}
    res = client.evaluate(table="customer_months", where=where, predict_field="churned_in_3_months",
                          train=train, test=test)
    return ChurnCheck(
        accuracy=round(float(res["accuracy"]), 4),
        base_accuracy=round(float(res["baseAccuracy"]), 4),
        n=int(res["n"]),
        method=METHOD.format(train=TRAIN_UNTIL, test=LABEL_KNOWN_UNTIL),
        last_query={"endpoint": "_evaluate", "body": client.evaluate_body(
            "customer_months", where, "churned_in_3_months", train=train, test=test)},
    )
