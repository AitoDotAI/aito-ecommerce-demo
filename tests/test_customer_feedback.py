"""What a segment says (ADR 0053): reviews and NPS answers of profiled customers, compared with the other profiled customers."""

from src.customer_feedback import MIN_RESPONDENTS, feedback_by_segment


def reviews(customer: str, *categories: str, rating: int = 4) -> list[dict]:
    return [{"customer_id": customer, "category": c, "rating": rating,
             "sentiment": "negative" if c in ("quality", "shipping", "fit") else "positive"} for c in categories]


def answer(customer: str, group: str) -> dict:
    return {"customer": customer, "nps_group": group, "score": {"promoter": 9, "passive": 7, "detractor": 3}[group]}


def two_groups(n_in: int = 40, n_out: int = 40) -> tuple[dict, list[str]]:
    """n_in customers in segment "s", n_out outside it; every one profiled."""
    members = {f"in{i}": ["all", "s"] for i in range(n_in)} | {f"out{i}": ["all"] for i in range(n_out)}
    return members, ["s"]


def test_a_segment_that_complains_more_about_shipping_shows_the_points_and_its_margin():
    members, listed = two_groups()
    rows = [r for i in range(40) for r in reviews(f"in{i}", "shipping")] + [r for i in range(40) if i < 10 for r in reviews(f"out{i}", "shipping")]
    out = feedback_by_segment(rows, [], members, listed)
    shipping = next(r for r in out["s"]["rows"] if r["label"] == "Wrote about shipping")
    assert shipping["share"] == 1.0 and shipping["share_others"] == 0.25
    assert shipping["points"] == 75.0 and shipping["clear"] is True and shipping["margin_points"] > 0


def test_a_customer_counts_once_however_many_reviews_they_wrote():
    members, listed = two_groups()
    rows = reviews("in0", "shipping", "shipping", "shipping")
    out = feedback_by_segment(rows, [], members, listed)
    shipping = next(r for r in out["s"]["rows"] if r["label"] == "Wrote about shipping")
    assert shipping["share"] == 1 / 40
    assert out["s"]["reviews"] == 3 and out["s"]["reviewers"] == 1


def test_reviews_of_customers_who_are_not_profiled_are_not_counted_anywhere():
    members, listed = two_groups()
    out = feedback_by_segment(reviews("stranger", "shipping", "quality"), [answer("stranger", "detractor")], members, listed)
    assert out["all"]["reviews"] == 0 and out["all"]["nps_respondents"] == 0


def test_nps_is_promoters_minus_detractors_in_points_and_needs_enough_respondents():
    members, listed = two_groups(n_in=MIN_RESPONDENTS, n_out=40)
    answers = [answer(f"in{i}", "promoter" if i < 20 else "detractor") for i in range(MIN_RESPONDENTS)] + [answer(f"out{i}", "passive") for i in range(40)]
    out = feedback_by_segment([], answers, members, listed)
    assert out["s"]["nps"] == round(100 * (20 - (MIN_RESPONDENTS - 20)) / MIN_RESPONDENTS, 1)
    assert out["all"]["nps_respondents"] == MIN_RESPONDENTS + 40
    few, _ = two_groups(n_in=MIN_RESPONDENTS - 1, n_out=40)
    thin = feedback_by_segment([], [answer(f"in{i}", "promoter") for i in range(MIN_RESPONDENTS - 1)], few, listed)
    assert thin["s"]["nps"] is None, "too few answers to call a score"


def test_everyone_has_shares_but_nothing_to_compare_with():
    members, listed = two_groups()
    out = feedback_by_segment(reviews("in0", "praise"), [], members, listed)
    assert all(r["points"] is None for r in out["all"]["rows"])


def test_a_group_too_small_to_compare_has_no_difference_rows():
    members, listed = two_groups(n_in=5, n_out=40)
    out = feedback_by_segment(reviews("in0", "praise"), [], members, listed)
    assert out["s"]["rows"] == []
