"""The Shop's season switch: the month is evidence (`context.month`) or it is not.

Without it the month still decides which orders are history, but the query carries no condition on it. A month's
lift is shop-wide ("Sells in April ×2.0" for every product), so on a dog household it lifted cat products too.
"""

from src.shop_ranking import shop_scope
from tests.test_shop_profile import FakeAito


def test_the_season_is_in_the_context_by_default():
    scope = shop_scope(FakeAito(), "janne", "2026-04", [])

    assert scope.context["context.month"] == "2026-04"


def test_without_the_season_the_context_has_no_month_but_the_history_still_ends_there():
    scope = shop_scope(FakeAito(), "janne", "2026-04", [], season=False)

    assert "context.month" not in scope.context
    assert "context.month" not in scope.where()
    assert [o["month"] for o in scope.orders] == ["2025-06", "2025-11", "2026-02"]    # the May order is not history yet
    assert scope.month == "2026-04"


def test_the_pets_and_the_rest_of_the_context_are_untouched():
    with_season = shop_scope(FakeAito(), "janne", "2026-04", [], identity=True)
    without = shop_scope(FakeAito(), "janne", "2026-04", [], identity=True, season=False)

    assert {k: v for k, v in with_season.context.items() if k != "context.month"} == without.context
