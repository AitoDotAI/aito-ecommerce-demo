"""No view feeds Aito a column that holds the answer, or a hint of it.

Three columns carry the future, or a trace of it, and are safe only as something to count:

- `customers.became_regular`: a label computed from later orders, on the very row a query reads features from.
- `contexts.first_order`: whether that session ended in the customer's first order.
- `contexts.customer`: null until the customer's first order, so "has a customer" is "is about to order".

Acquisition counts them on purpose (labelled customers, first-order sessions) and predicts
`became_regular` from `first_source` alone. Nothing else may name them, and no prediction may
use one as evidence. The checks read the source with `ast`, so a new view that names one fails here
before it reaches a query.
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.acquisition_service import source_queries

SRC = Path(__file__).resolve().parents[1] / "src"
LABEL_COLUMNS = {"became_regular", "first_order"}
# schema.py declares the columns; acquisition_service.py is the one reader, and checked below.
MAY_NAME_THE_LABELS = {"schema.py", "acquisition_service.py"}
# Shop analytics' `_relate` lifts run over identified sessions only (ADR 0040): condition and
# population are cut the same way, so the lifts compare like with like, and no prediction reads it.
# Named here so a second use is a decision, not an accident.
MAY_RESTRICT_TO_IDENTIFIED = {"shop_analytics_service.py"}


def leaks(source: str, filename: str) -> list[str]:
    """What in `source` uses a future-carrying column where it is not allowed."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and node.value in LABEL_COLUMNS and filename not in MAY_NAME_THE_LABELS:
            found.append(f"{filename}:{node.lineno} names `{node.value}`, a column that carries the future")
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                names_customer = isinstance(key, ast.Constant) and key.value in ("customer", "context.customer")
                if names_customer and filename not in MAY_RESTRICT_TO_IDENTIFIED and isinstance(value, ast.Dict) and any(
                        isinstance(k, ast.Constant) and k.value == "$exists" for k in value.keys):
                    found.append(f"{filename}:{node.lineno} asks whether a customer is present; "
                                 "a context has one only after the first order")
    return found


def test_no_view_names_the_label_columns_outside_the_acquisition_view():
    violations = [v for path in sorted(SRC.rglob("*.py"))
                  for v in leaks(path.read_text(encoding="utf-8"), path.name)]

    assert violations == []


def test_the_acquisition_view_predicts_the_label_from_the_first_source_alone():
    queries = source_queries("email")

    predictions = [q for q in queries if "predict" in q]
    counts = [q for q in queries if "predict" not in q]

    assert [(q["predict"], set(q["where"])) for q in predictions] == [("became_regular", {"first_source"})]
    assert all(q["limit"] == 0 for q in counts), "a query that reads the labels without predicting must only count"


def test_a_view_that_names_a_label_column_is_caught():
    source = 'body = {"from": "customers", "where": {"became_regular": True}, "predict": "returned"}\n'

    assert leaks(source, "new_view.py") == [
        "new_view.py:1 names `became_regular`, a column that carries the future"]


def test_a_view_that_conditions_on_the_first_order_session_flag_is_caught():
    source = 'where = {"first_order": True}\n'

    assert len(leaks(source, "funnel_view.py")) == 1


def test_shop_analytics_may_restrict_its_lifts_to_identified_sessions_and_nobody_else_may():
    source = 'IDENTIFIED = {"context.customer": {"$exists": True}}\n'

    assert leaks(source, "shop_analytics_service.py") == []
    assert len(leaks(source, "another_view.py")) == 1


def test_a_view_that_asks_whether_a_context_has_a_customer_is_caught():
    source = 'where = {"customer": {"$exists": False}}\n'

    assert leaks(source, "visitors_view.py") == [
        "visitors_view.py:1 asks whether a customer is present; a context has one only after the first order"]
