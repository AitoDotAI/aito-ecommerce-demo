"""The lever tools return only fields of the views' own results, name their view, and flag thin bands."""

from src import ask_tools
from src.ask_tools import LISTED, THIN_BELOW_SHOWINGS, build_tools


class Reader:
    def __init__(self, hits=()):
        self.hits, self.searches = list(hits), []

    def search(self, table, **kwargs):
        self.searches.append((table, kwargs))
        return {"hits": self.hits}


def _by_name(tools):
    return {t.name: t for t in tools}


def test_the_tools_are_read_only_lookups_named_for_what_they_answer():
    names = [t.name for t in build_tools(Reader(), dict, dict)]

    assert names == ["find_products", "offer_what_if", "price_what_if", "reorder_queue", "overstock", "at_risk_customers"]


def test_find_products_matches_the_words_of_a_name():
    reader = Reader([{"sku": "SKU-1", "name": "Trixie Hideout"}])

    result = _by_name(build_tools(reader, dict, dict))["find_products"].run({"text": "hideout"})

    assert reader.searches[0][1]["where"] == {"name": {"$match": "hideout"}}
    assert result == {"products": [{"sku": "SKU-1", "name": "Trixie Hideout"}], "listed": 1}


def test_a_band_shown_under_the_rule_is_thin_and_the_result_links_its_view(monkeypatch):
    what_if = type("W", (), {"to_dict": lambda self: {
        "name": "Trixie Hideout", "month": "2026-04", "current_band": "none",
        "bands": [{"band": "none", "shown": 31}, {"band": "20+", "shown": THIN_BELOW_SHOWINGS - 1}]}})()
    monkeypatch.setattr(ask_tools, "get_discount_what_if", lambda reader, sku, month: what_if)

    result = _by_name(build_tools(Reader(), dict, dict))["offer_what_if"].run({"sku": "SKU-PT-0563"})

    assert [(b["band"], b["thin"]) for b in result["bands"]] == [("none", False), ("20+", True)]
    assert result["view"] == "/product/?sku=SKU-PT-0563&tab=what-if"


def test_a_list_tool_returns_the_top_rows_without_the_views_explanation_trees():
    rows = [{"sku": f"S{i}", "name": f"P{i}", "current_stock": 1, "reorder_point": 5, "recent_units": 9,
             "order_qty": 8, "order_cost_eur": 10.0, "revenue_at_risk_eur": 20.0, "why_explanation": {"big": "tree"}}
            for i in range(LISTED + 5)]
    supply = lambda: {"planning_month": "2026-05", "reorder": {"skus": len(rows)}, "reorder_queue": rows}

    result = _by_name(build_tools(Reader(), supply, dict))["reorder_queue"].run({})

    assert result["listed"] == LISTED and result["of"] == LISTED + 5
    assert "why_explanation" not in result["top"][0] and result["view"] == "/supply/"


def test_at_risk_customers_keep_the_offer_but_not_the_why():
    row = {"customer_id": "C1", "name": "N", "pets": "cat", "risk": "likely", "spend_12m_eur": 100.0,
           "last_order_month": "2026-04", "why_explanation": {"big": "tree"},
           "offer": {"name": "Food", "expected_return_eur": 3.5, "sku": "S", "response_p": 0.2}}
    retention = lambda: {"as_of_month": "2026-04", "decision": {}, "counts": {}, "at_risk": [row]}

    result = _by_name(build_tools(Reader(), dict, retention))["at_risk_customers"].run({})

    assert result["top"][0]["offer"] == {"name": "Food", "expected_return_eur": 3.5}
    assert "why_explanation" not in result["top"][0]
