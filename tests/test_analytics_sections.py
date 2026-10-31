"""The Patterns, Reviews and Acquisition sections are warmed at start and kept for the release (ADR 0024).

Each section is 5-40 `_relate`s: 2-13 s for whoever opens the page first. They were cached for 30 minutes and warmed by nobody,
so the first visitor of every half hour paid for it. The data is fixed within a release and the release gate drops the caches
when it changes, so a section can be kept for hours, and the start-up warmup can fill them.
"""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient

from src import analytics_sections, cache


class Stub:
    def __init__(self, label):
        self.label = label

    def to_dict(self):
        return {"stub": self.label}


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _stub_everything(monkeypatch, computed: list[str]):
    def fake_warmed(client):
        return [(key, (lambda key=key: computed.append(key) or Stub(key))) for key in EXPECTED_KEYS]

    monkeypatch.setattr(analytics_sections, "warmed", fake_warmed)


EXPECTED_KEYS = ["funnel:purchased", "funnel:clicked", "who:summer", "acquisition", "reviews:clicked", "reviews:purchased",
                 "reviews:nps", "reviews:churn", "reviews:reply-effect", "baskets", "search-words"]


def test_warmup_covers_every_section_the_patterns_reviews_and_acquisition_pages_open_with():
    keys = [key for key, _ in analytics_sections.warmed(client=None)]

    assert keys == EXPECTED_KEYS


def test_a_warmed_section_is_served_from_the_cache_without_computing_again(monkeypatch):
    computed: list[str] = []
    _stub_everything(monkeypatch, computed)

    analytics_sections.warm(None, verbose=False)
    served = analytics_sections.cached("reviews:clicked", lambda: pytest.fail("computed again"))

    assert computed == EXPECTED_KEYS and served == {"stub": "reviews:clicked"}


def test_a_section_is_kept_for_hours_not_half_an_hour():
    assert analytics_sections.SECTION_TTL_SECONDS >= 3 * 3600


def test_one_failing_section_does_not_stop_the_others_from_warming(monkeypatch):
    computed: list[str] = []

    def fake_warmed(client):
        def boom():
            raise RuntimeError("one section failed")
        return [("funnel:purchased", boom), ("baskets", lambda: computed.append("baskets") or Stub("baskets"))]

    monkeypatch.setattr(analytics_sections, "warmed", fake_warmed)

    analytics_sections.warm(None, verbose=False)

    assert computed == ["baskets"]


def test_the_pages_routes_answer_from_what_the_warmup_filled(app_module, monkeypatch):
    computed: list[str] = []
    _stub_everything(monkeypatch, computed)
    analytics_sections.warm(None, verbose=False)
    client = TestClient(app_module.app)
    monkeypatch.setattr(app_module.release_gate, "state", "ready")

    answers = {path: client.get(path).json() for path in (
        "/api/reviews?section=clicked", "/api/reviews/reply-effect", "/api/acquisition",
        "/api/shop-analytics/funnel?kpi=purchased", "/api/shop-analytics/who?who=summer",
        "/api/shop-analytics/baskets", "/api/shop-analytics/search-words")}

    assert answers["/api/reviews?section=clicked"] == {"stub": "reviews:clicked"}
    assert answers["/api/shop-analytics/who?who=summer"] == {"stub": "who:summer"}
    assert all(a.get("stub") for a in answers.values()), answers
    assert len(computed) == len(EXPECTED_KEYS), "the routes computed nothing more"
