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
    # Re-picked for data release 2 (ADRs 0038-0045): a guinea-pig household
    # with a declared pet profile. The key stays `paivi` so links and the
    # default hold.
    Shopper("paivi", "CUST-00922", "Anna Ojala", "🐹",
            "Got a guinea pig in February: a cage and a water bottle so far."),
    # Re-picked for data release 2: a declared medium dog and grain-free rule,
    # with consent (ADR 0044, ADR 0045).
    Shopper("janne", "CUST-00152", "Juha Järvinen", "🐕",
            "A grain-free dog household: never any other food."),
    Shopper("helena", "CUST-00053", "Helena Heinonen", "🐈",
            "Buys the same cat food every few weeks."),
    Shopper("maija", "CUST-00001", "Maija Lehtonen", "🐈",
            "A cats-only home in Helsinki."),
    Shopper("olli", "CUST-00002", "Olli Mäkelä", "🐕",
            "Declares a small dog; reorders Eukanuba Puppy Lamb dog food."),
    Shopper("saara", "CUST-00003", "Saara Virtanen", "🐕",
            "A large dog: 6 of 13 orders hold the same 4 kg bag of Hill's Science Plan Large Breed."),
    # ADR 0044: said no to behavioural tracking. The shop has their orders
    # and what they told it, and no visits or impressions.
    Shopper("juhani", "CUST-00330", "Juhani Salminen", "🐈",
            "Said no to tracking: 11 orders, and the interests they chose (grooming, budget buys)."),
    # Most customers fill no pet profile (2026-10-24): the shop reads the pet
    # from their orders (`contexts.pets_from_orders`).
    Shopper("eemil", "CUST-01896", "Eemil Ojala", "🐕",
            "No pet profile: 17 orders, every one for a dog."),
]
# The shopper whose Shop shows "no behavioural data" (ADR 0044).
NO_CONSENT_SHOPPER = "juhani"
# The shopper who declared no pets: "Picked for you" reads their orders.
NO_PET_PROFILE_SHOPPER = "eemil"
DEFAULT_SHOPPER = "paivi"


class UnknownShopperError(LookupError):
    """The requested shopper key is not one of SHOPPERS."""


def shopper(key: str) -> Shopper:
    for s in SHOPPERS:
        if s.key == key:
            return s
    raise UnknownShopperError(f"No shopper {key!r}; known: {', '.join(s.key for s in SHOPPERS)}")
