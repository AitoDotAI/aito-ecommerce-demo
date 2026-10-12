"""Errors for an id that isn't in the data.

Views take their product or review from the URL, so a shared link can
name an id that doesn't exist. The API answers 404 with the message
instead of quietly showing another item under the same URL.
"""


class UnknownProductError(LookupError):
    """The requested SKU is not in the catalogue."""


class UnknownReviewError(LookupError):
    """The requested review id is not in the data."""
