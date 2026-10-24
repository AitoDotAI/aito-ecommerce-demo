"""ADR 0039: reviews with consequences, in one direction.

Before ADR 0039, churn wrote the reviews: a churning customer drew more
complaint categories and lower stars, so "1-star reviews predict churn" was
true of the data for the wrong reason. Now an order line's experience writes
the review, and the experience (not the review) raises churn.

Some of the planted paths do run from a review to churn, all causal: a reply
lowers its writer's churn (R4), and stars move which products are bought (R5,
R6, and P7's odds on every showing), and so which experiences follow. With those switched off,
writing reviews or not must leave every customer's history exactly as it was.
(docs/verification/actionable-states-prereg.md, "Where the ADRs' own numbers
can't hold", item 4.)
"""

import random
from collections import defaultdict

import pytest

import data.generate_fixtures as generator
from data import lifecycle, catalogue_events, planted_switches
from tests.fixture_joins import load

N_CUSTOMERS = 400


def _histories() -> tuple[list, generator.OrderHistory]:
    """The first customers' order histories, generated as `main` does."""
    rng = random.Random(generator.RNG_SEED)
    products = generator.gen_products(rng)
    customers = generator.gen_customers(rng)[:N_CUSTOMERS]
    generator.assign_sources_and_sensitivities(customers)
    promotions = lifecycle.plan_promotions(random.Random(generator.RNG_SEED + 27), products, generator._MONTH_WINDOW)
    events = catalogue_events.plan_catalogue_events(random.Random(generator.RNG_SEED + 32), products,
                                                    generator._MONTH_WINDOW, promotions.mispriced)
    return customers, generator.gen_orders_and_lines(customers, products, promotions, events)


@pytest.fixture
def stars_paths_off(monkeypatch):
    # Stars reach purchases through the shop's ranker (R5), price sensitivity
    # (R6) and every showing's odds (P7): since ADR 0045 a purchase is a showing.
    for effect in ("R5", "R6", "P7"):
        monkeypatch.setitem(planted_switches.ON, effect, False)


def test_without_reviews_every_customer_churns_when_they_did_with_them(stars_paths_off, monkeypatch):
    monkeypatch.setitem(planted_switches.ON, "R4_reply", False)
    with_reviews, history = _histories()
    monkeypatch.setattr(planted_switches, "REVIEWS_WRITTEN", False)
    without_reviews, history_without = _histories()

    assert history.reviews and not history_without.reviews
    assert [c.churn_month for c in with_reviews] == [c.churn_month for c in without_reviews]
    assert [(o.customer_id, o.month) for o in history.orders] == \
        [(o.customer_id, o.month) for o in history_without.orders]


def test_a_reply_is_the_only_way_a_review_reaches_its_writers_churn(stars_paths_off, monkeypatch):
    with_reviews, history = _histories()
    monkeypatch.setattr(planted_switches, "REVIEWS_WRITTEN", False)
    without_reviews, _ = _histories()

    replied = {r.customer_id for r in history.reviews if r.replied}
    changed = {a.customer_id for a, b in zip(with_reviews, without_reviews) if a.churn_month != b.churn_month}
    assert changed <= replied, sorted(changed - replied)


def test_a_reviews_stars_follow_its_experience_not_whether_the_writer_churned():
    # On the committed fixtures: within one experience, churned and active
    # writers give the same stars. The old generator gave churners lower ones.
    experience = {row["line_id"]: row["experience"] for row in load("answer_key/line_experiences.json")}
    churned = {c["customer_id"]: c["churned"] for c in load("customers.json")}
    low = defaultdict(lambda: [0, 0])     # (experience, churned) → [rating ≤ 2, reviews]
    for r in load("reviews.json"):
        cell = low[(experience[r["order_line"]], churned[r["customer_id"]])]
        cell[0] += r["rating"] <= 2
        cell[1] += 1
    for level in ("bad", "ok", "good"):
        (churned_low, churned_n), (active_low, active_n) = low[(level, True)], low[(level, False)]
        assert min(churned_n, active_n) >= 50, (level, churned_n, active_n)
        gap = churned_low / churned_n - active_low / active_n
        assert abs(gap) <= 0.10, f"{level}: churned writers' 1–2★ share differs by {gap:+.2f}"
