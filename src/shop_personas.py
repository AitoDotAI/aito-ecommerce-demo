"""The shoppers the Shop view lets you be (ADR 0031).

Each is a real customer in the generated data whose history tells the
story on their card. `tests/test_shop_personas.py` checks that the story
is true of the data, so a regenerated fixture can't quietly break it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Shopper:
    key: str            # the URL value: /shop/?shopper=paivi
    customer_id: str
    name: str
    emoji: str
    story: str          # one line of narration, shown on the card

    def to_dict(self) -> dict:
        return asdict(self)


# Stories read as of the Shop's default month, April 2026.
SHOPPERS = [
    Shopper("paivi", "CUST-01177", "Päivi Salminen", "🐹",
            "Got a guinea pig in February: a cage and a water bottle so far."),
    Shopper("janne", "CUST-00049", "Janne Hämäläinen", "🐕",
            "A grain-free dog household: never any other food."),
    Shopper("helena", "CUST-00053", "Helena Heinonen", "🐈",
            "Buys the same cat food every few weeks."),
    Shopper("maija", "CUST-00001", "Maija Lehtonen", "🐈",
            "A cats-only home in Helsinki."),
    Shopper("olli", "CUST-00002", "Olli Mäkelä", "🐕",
            "Declares a small dog; reorders Acana Sensitive dog food."),
    Shopper("saara", "CUST-00003", "Saara Virtanen", "🐕",
            "A large dog: 13 of 14 orders hold the same 7 kg bag of Hill's Science Plan Senior."),
]
DEFAULT_SHOPPER = "paivi"


class UnknownShopperError(LookupError):
    """The requested shopper key is not one of SHOPPERS."""


def shopper(key: str) -> Shopper:
    for s in SHOPPERS:
        if s.key == key:
            return s
    raise UnknownShopperError(f"No shopper {key!r}; known: {', '.join(s.key for s in SHOPPERS)}")
