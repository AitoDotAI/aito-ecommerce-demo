"""Theme tags for what customers wrote: a review's text or an NPS answer's comment, tagged by what it is about.

A message gets every tag whose phrase it contains. The tags are what the Feedback tab groups by: far fewer and more readable than the words,
and one message can carry several ("I was disappointed ...: the quality is not what I expected. I had to send one item back." is
`quality-below-expectations` and `return-or-refund`). A text no rule recognises raises: a message the rules do not cover must be added to them,
not silently left untagged.
"""

from __future__ import annotations

import re

# Ordered as shown in the lists; each theme is the phrases (case-insensitive) that put a message under it.
THEMES: dict[str, tuple[str, ...]] = {
    "late-delivery": ("arrived late", "came late", "took far too long", "delivery of the .* was slow", "came a day later than promised", "delivery was slow"),
    "damaged-packaging": ("box was damaged", "was crushed", "and crushed"),
    "not-as-described": ("not what the listing shows", "not as good as the photo"),
    "quality-below-expectations": ("much worse than i expected", "quality is not what i expected", "average quality", "expected a bit more"),
    "sizing-or-fit": ("sizing of", "wrong size", "does not fit", "runs a bit small", "a little tight"),
    "pet-rejected-it": ("refused it", "would not touch it", "did not take to it", "would not eat it", "tasted and smelled wrong", "smells off"),
    "health-concern": ("was sick", "got ill", "took it to the vet", "bad batch", "sensitive stomach"),
    "return-or-refund": ("returned it", "refunded", "send one item back"),
    "losing-trust": ("think twice before ordering", "will not buy this again", "do not trust it", "switched to another brand", "not the experience i wanted"),
    "mediocre": ("nothing special", "does the job", "okay overall", "is okay, but", "nothing to complain about"),
    "quick-or-good-delivery": ("delivery was quick", "on time and well packed", "box was fine"),
    "pet-likes-it": ("loves the", "likes the", "cannot get enough", "approves", "eats it happily", "loves it"),
    "fits-well": ("fits my .* perfectly", "good quality .*, as described", "looks and smells fresh"),
    "asks-for-more": ("bigger pack", "come back in stock", "come in a bigger size"),
    "praise": ("best we have tried", "just what we needed", "five stars", "great ", "happy with the shop", "we will order again"),
}
_RULES = {tag: re.compile("|".join(phrases), re.IGNORECASE) for tag, phrases in THEMES.items()}


def themes_of(text: str | None) -> list[str]:
    """The tags of one message, in the order of `THEMES`; an empty or missing message has none."""
    if not text:
        return []
    tags = [tag for tag, rule in _RULES.items() if rule.search(text)]
    if not tags:
        raise ValueError(f"No theme rule covers this message, add one to src/feedback_themes.py: {text!r}")
    return tags
