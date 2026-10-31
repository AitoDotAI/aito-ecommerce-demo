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

import pytest

from src.acquisition_service import source_queries

SRC = Path(__file__).resolve().parents[1] / "src"
LABEL_COLUMNS = {"became_regular", "first_order"}
# Paths relative to src/. schema.py declares the columns; acquisition_service.py is the one reader, and checked below.
MAY_NAME_THE_LABELS = {"schema.py", "acquisition_service.py"}
# Shop analytics' `_relate` lifts run over identified sessions only (ADR 0040): condition and
# population are cut the same way, so the lifts compare like with like, and no prediction reads it.
# Named here so a second use is a decision, not an accident.
MAY_RESTRICT_TO_IDENTIFIED = {"shop_analytics_service.py"}


def scanned_files(root: Path) -> list[str]:
    """The Python files under `root`, as paths relative to it: the names the allowlists use."""
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*.py"))


def violations_under(root: Path) -> list[str]:
    files = scanned_files(root)
    assert files, f"nothing to scan under {root}: an empty scan would pass every check"
    return [v for name in files for v in leaks((root / name).read_text(encoding="utf-8"), name)]


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
    assert violations_under(SRC) == []


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


def test_the_scan_reads_the_source_tree_and_finds_the_files_the_allowlists_name():
    scanned = scanned_files(SRC)

    assert scanned, "an empty scan passes every check"
    assert MAY_NAME_THE_LABELS | MAY_RESTRICT_TO_IDENTIFIED <= set(scanned)


def test_a_scan_of_a_directory_that_does_not_exist_fails_instead_of_passing_on_nothing(tmp_path):
    with pytest.raises(AssertionError, match="nothing to scan"):
        violations_under(tmp_path / "no-such-dir")


def test_a_file_that_shares_an_allowed_files_name_in_another_folder_is_still_caught(tmp_path):
    source = 'body = {"where": {"became_regular": True}}\n'
    (tmp_path / "views").mkdir()
    (tmp_path / "schema.py").write_text(source)
    (tmp_path / "views" / "schema.py").write_text(source)

    assert [v.split(":")[0] for v in violations_under(tmp_path)] == ["views/schema.py"]
