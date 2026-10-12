"""A shared link can name an id that doesn't exist (a typo, or a product
removed since the link was sent). The view must say so, not quietly show
a different item under the same URL.
"""

import pytest

from src import cache
from src.feedback_service import get_feedback
from src.filling_service import get_filling
from src.lookup_errors import UnknownProductError, UnknownReviewError


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    monkeypatch.setattr(cache, "get", lambda key: None)


def test_an_unknown_review_id_raises_instead_of_showing_the_default_review():
    # The id is checked against the local fixtures before any Aito call,
    # so no client is needed.
    with pytest.raises(UnknownReviewError, match="REV-NO-SUCH"):
        get_feedback(client=None, review_id="REV-NO-SUCH")


def test_an_unknown_sku_raises_instead_of_filling_the_default_product():
    with pytest.raises(UnknownProductError, match="SKU-NO-SUCH"):
        get_filling(client=None, sku="SKU-NO-SUCH")
