"""The Patterns, Reviews and Acquisition sections: their cache keys, their lifetime and their warmup (ADR 0024).

A section is 5-40 `_relate`s, 2-13 s for whoever opens the page first. The data is fixed within a release, and the release
gate drops every memory cache when it changes (`data_release_gate.py`), so a section is kept for hours and the start-up warmup
fills it: nobody pays for the first visit.

One place for the keys, so a route and the warmup cannot disagree about what is cached.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from src import cache
from src.aito_client import AitoClient
from src.design_effect import DesignEffect
from src.reviews_service import SECTIONS as REVIEW_SECTIONS, get_reply_effect, get_reviews_section
from src.acquisition_service import get_acquisition
from src.basket_pairs import get_basket_section
from src.search_words import get_search_words_section
from src.shop_analytics_service import DEFAULT_WHO, KPIS, get_funnel_section, get_who_section

SECTION_TTL_SECONDS = 6 * 3600


def cached(key: str, load: Callable[[], object]) -> dict:
    """The section under `key`, computed by `load()` (an object with `to_dict`) on a miss."""
    return cache.get_or_compute(f"shop-analytics:{key}", lambda: load().to_dict(), ttl=SECTION_TTL_SECONDS)


def reply_effect(client: AitoClient):
    """Churn after a negative review, replied over not replied: it reuses the churn section's clustering."""
    churn = cached("reviews:churn", lambda: get_reviews_section(client, "churn"))
    return get_reply_effect(client, DesignEffect(**churn["clustering"]))


def warmed(client: AitoClient) -> list[tuple[str, Callable[[], object]]]:
    """Every section the pages open with, in the order they are computed (the reply effect needs the churn section first).
    The other `who` choices are computed when someone picks them."""
    return [
        *((f"funnel:{kpi}", lambda kpi=kpi: get_funnel_section(client, kpi=kpi)) for kpi in KPIS),
        (f"who:{DEFAULT_WHO}", lambda: get_who_section(client, who=DEFAULT_WHO)),
        ("acquisition", lambda: get_acquisition(client)),
        *((f"reviews:{s}", lambda s=s: get_reviews_section(client, s)) for s in REVIEW_SECTIONS),
        ("reviews:reply-effect", lambda: reply_effect(client)),
        ("baskets", lambda: get_basket_section(client)),
        ("search-words", lambda: get_search_words_section(client)),
    ]


def warm(client: AitoClient | None, *, verbose: bool = True) -> None:
    """Compute every warmed section once, one after the other (parallel sections would crowd Aito). A failure is
    reported and does not stop the rest: that section is computed when someone opens it."""
    for key, load in warmed(client):
        started = time.perf_counter()
        try:
            cached(key, load)
        except Exception as exc:
            if verbose:
                print(f"  warm ERR section {key}: {exc}")
            continue
        if verbose:
            print(f"  warm: section {key:30s} ({int((time.perf_counter() - started) * 1000)} ms)")
