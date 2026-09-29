"""Dashboard purchase-pattern tiles: loud failures without a dead landing page.

The dashboard fans out one `_relate` per pattern. A failed call used to be
swallowed into a silently missing tile; it must now show as unavailable,
and only a total failure may take the page down.
"""

from __future__ import annotations

import pytest

from src.aito_client import AitoError
from src.overview_service import _PATTERN_PAIRS, _compute_top_patterns


def _token(pet: str, category: str) -> str:
    return f"{pet}_{category.replace('-', '')}"


class FakeAito:
    """Answers every pattern with a lift of 2.0, except anchors listed in
    `failing`, whose `_relate` raises."""

    def __init__(self, failing: set[str]):
        self.failing = failing

    def relate(self, table, where, relate_field, limit=10):
        anchor = where["line_categories"]["$match"]
        if anchor in self.failing:
            raise AitoError("shared timeout", status_code=504)
        targets = [_token(*t) for a, t, _ in _PATTERN_PAIRS if _token(*a) == anchor]
        return {"hits": [{"related": {"line_categories": {"$has": t}}, "lift": 2.0} for t in targets]}


def test_one_failed_pattern_shows_as_unavailable_and_the_rest_still_render():
    failing = _token("cat", "wet-food")
    tiles = _compute_top_patterns(FakeAito({failing}), k=len(_PATTERN_PAIRS))
    unavailable = [t.label for t in tiles if not t.available]
    assert unavailable == ["Cat wet-food → Cat litter"]
    assert any(t.available and t.lift == 2.0 for t in tiles)


def test_the_page_fails_loudly_only_when_every_pattern_fails():
    every_anchor = {_token(*a) for a, _, _ in _PATTERN_PAIRS}
    with pytest.raises(AitoError, match="all .* dashboard pattern lifts failed"):
        _compute_top_patterns(FakeAito(every_anchor))
