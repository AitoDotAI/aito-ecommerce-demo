"""Supply's second lever (ADR 0061): lines that do not move, which the shop could end and sell down, instead of reordering."""

from types import SimpleNamespace

from src.supply_end_of_line import end_of_line, season_ahead

MONTHS = [f"2025-{m:02d}" for m in range(1, 13)] + [f"2026-{m:02d}" for m in range(1, 5)]


def sales(by_month: dict[str, int]) -> list[dict]:
    return [{"month": m, "units_sold": by_month.get(m, 1)} for m in MONTHS]


def overstock(sku: str, action: str = "wont_clear", capital: float = 1000.0, weeks: float | None = 60.0) -> SimpleNamespace:
    return SimpleNamespace(sku=sku, name=f"Product {sku}", category="toys", current_stock=40, excess_units=30, unit_cost_eur=30.0, tied_capital_eur=capital,
                           markdown=SimpleNamespace(action=action, discount_pct=20, price_eur=45.0, weeks_to_clear=weeks))


def test_a_product_that_sold_far_more_in_the_months_ahead_last_year_has_a_season_ahead():
    # Planning May 2026: May-July last year sold 10 a month against 1 in the other months.
    christmas_like = sales({"2025-05": 10, "2025-06": 10, "2025-07": 10})

    assert season_ahead(christmas_like, "2026-05") is True
    assert season_ahead(sales({}), "2026-05") is False


def test_a_product_with_too_little_history_to_know_its_seasons_is_not_said_to_have_one():
    short = [{"month": m, "units_sold": 30} for m in ("2026-02", "2026-03", "2026-04")]

    assert season_ahead(short, "2026-05") is False


def test_a_line_that_will_not_clear_even_at_the_deepest_markdown_and_has_no_season_ahead_is_a_candidate_to_end():
    rows = [overstock("A"), overstock("B", action="hold"), overstock("C", action="markdown", weeks=10.0)]

    candidates = end_of_line(rows, {r.sku: sales({}) for r in rows}, "2026-05")

    assert [c["sku"] for c in candidates] == ["A"]
    assert candidates[0]["tied_capital_eur"] == 1000.0 and candidates[0]["weeks_to_clear"] == 60.0 and candidates[0]["discount_pct"] == 20


def test_a_line_with_a_season_ahead_is_not_a_candidate_it_is_held():
    rows = [overstock("A"), overstock("B")]
    history = {"A": sales({"2025-05": 12, "2025-06": 12, "2025-07": 12}), "B": sales({})}

    candidates = end_of_line(rows, history, "2026-05")

    assert [c["sku"] for c in candidates] == ["B"]


def test_a_markdown_price_below_cost_is_said_to_be_a_loss():
    cheap = overstock("A")
    cheap.markdown.price_eur = 25.0          # below the unit cost of 30

    (candidate,) = end_of_line([cheap, overstock("B")], {"A": sales({}), "B": sales({})}, "2026-05")[:1]

    assert candidate["below_cost"] is True
