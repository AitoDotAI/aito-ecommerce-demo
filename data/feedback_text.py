"""The words of feedback (ADR 0058): reviews that read like their stars, and the comments of NPS answers.

Everything here is fiction. A review's text follows its topic and its stars, and names the product; an NPS comment is built from the causes the
generator already knows about the order (the product, the delivery, a return, the experience, a recalled batch) and comes with its ground
truth, which goes to the answer key and never to the table. Each text draws from a random stream of its own, so no other draw moves.
"""

from __future__ import annotations

import random

TONES = ("negative", "mixed", "positive")

# review topic -> tone -> sentences; {p} is the product, {pet} the animal.
REVIEW_CLAUSES: dict[str, dict[str, list[str]]] = {
    "praise": {
        "positive": ["My {pet} loves the {p}.", "The {p} is the best we have tried.", "Great {p}, my {pet} cannot get enough.",
                     "The {p} is just what we needed.", "Five stars for the {p}: my {pet} approves."],
        "mixed": ["The {p} is fine. My {pet} eats it.", "Decent {p}, does the job."],
        "negative": [],
    },
    "quality": {
        "negative": ["The {p} was poor: my {pet} would not touch it.", "Contents of the {p} are not what the listing shows.",
                     "The {p} smells off and my {pet} refused it.", "Quality of the {p} is much worse than I expected."],
        "mixed": ["The {p} is okay, but not as good as the photo.", "Average quality for the {p}; I expected a bit more."],
        "positive": ["Good quality {p}, as described.", "The {p} looks and smells fresh."],
    },
    "shipping": {
        "negative": ["The {p} arrived late and the box was damaged.", "Delivery of the {p} took far too long.", "Packaging of the {p} was crushed when it came."],
        "mixed": ["The {p} came a day later than promised.", "Delivery of the {p} was slow but the box was fine."],
        "positive": ["The {p} arrived quickly and well packed."],
    },
    "fit": {
        "negative": ["The {p} is the wrong size for my {pet}.", "The {p} does not fit my {pet} at all; I returned it.", "Sizing of the {p} is far off the chart."],
        "mixed": ["The {p} fits my {pet}, just a little tight.", "The {p} runs a bit small, but works."],
        "positive": ["The {p} fits my {pet} perfectly."],
    },
    "question": {
        "negative": ["Is the {p} really suitable for a {pet}? Mine did not take to it."],
        "mixed": ["Is the {p} suitable for a {pet} with a sensitive stomach?", "Does the {p} come in a bigger size?"],
        "positive": ["Is there a bigger pack of the {p}? My {pet} loves it.", "Will the {p} come back in stock soon? We want more."],
    },
}

RECALLED_REVIEW = ["My {pet} got ill after eating the {p}. We stopped at once and took it to the vet.",
                   "After the {p} my {pet} was sick for days. I will not buy this again."]
QUIET_REVIEW = ["The {p} tasted and smelled wrong this time. I have switched to another brand.", "A bad batch of the {p}: my {pet} would not eat it. Refunded, but I do not trust it now."]


def tone_of(rating: int) -> str:
    return "negative" if rating <= 2 else "mixed" if rating == 3 else "positive"


def review_text(rng: random.Random, category: str, rating: int, product: str, pet: str, incident: str | None = None) -> str:
    """The text of a review. `incident` is "recalled" or "quiet" when the unit came from a planted incident (ADR 0056)."""
    if incident == "recalled" and rating <= 2:
        pool = RECALLED_REVIEW
    elif incident == "quiet" and rating <= 2:
        pool = QUIET_REVIEW
    else:
        pool = REVIEW_CLAUSES[category][tone_of(rating)] or REVIEW_CLAUSES["quality"][tone_of(rating)]
    return rng.choice(pool).format(p=product, pet=pet)


# NPS comments ---------------------------------------------------------------------------------------------------------------------------

COMMENT_P = {"promoter": 0.5, "passive": 0.25, "detractor": 0.5}

PRODUCT_CLAUSES = {
    "good": ["The {p} was just what we needed.", "My {pet} likes the {p}.", "The {p} is good and my {pet} eats it happily."],
    "ok": ["The {p} is fine, nothing special.", "The {p} does the job."],
    "bad": ["The {p} was poor and my {pet} would not eat it.", "I was disappointed with the {p}: the quality is not what I expected."],
}
RECALLED_CLAUSE = "My {pet} got ill after the {p}. We stopped feeding it."
QUIET_CLAUSE = "The {p} tasted and smelled wrong. I have switched brand."
DELIVERY_CLAUSES = {"problem": ["Delivery was late and the box was damaged.", "The parcel came late and crushed."],
                    "fine": ["Delivery was quick.", "The parcel came on time and well packed."]}
RETURN_CLAUSE = "I had to send one item back."
OVERALL = {"promoter": ["We will order again.", "Happy with the shop."], "passive": ["Okay overall.", "Nothing to complain about, nothing special."],
           "detractor": ["I will think twice before ordering again.", "Not the experience I wanted."]}


def nps_comment(rng: random.Random, group: str, experience: str, product: str, pet: str, delivery_problem: bool, returned: bool,
                incident: str | None = None) -> tuple[str | None, dict]:
    """(the comment or None, its ground truth {"topics": [...], "names_product": bool}). The comment follows the causes the order had."""
    if rng.random() >= COMMENT_P[group]:
        return None, {"topics": [], "names_product": False}
    clauses: list[str] = []
    topics: set[str] = set()
    names_product = False
    if incident == "recalled" and experience == "bad":
        clauses.append(RECALLED_CLAUSE)
        topics |= {"product", "health"}
        names_product = True
    elif incident == "quiet" and experience == "bad":
        clauses.append(QUIET_CLAUSE)
        topics |= {"product", "quality"}
        names_product = True
    elif rng.random() < 0.8:
        clauses.append(rng.choice(PRODUCT_CLAUSES[experience]))
        topics |= {"product"} | ({"quality"} if experience == "bad" else set())
        names_product = True
    if delivery_problem:
        clauses.append(rng.choice(DELIVERY_CLAUSES["problem"]))
        topics.add("delivery")
    elif not clauses or rng.random() < 0.3:
        clauses.append(rng.choice(DELIVERY_CLAUSES["fine"]) if group == "promoter" and rng.random() < 0.5 else rng.choice(OVERALL[group]))
        topics.add("delivery" if clauses[-1] in DELIVERY_CLAUSES["fine"] else "overall")
    if returned:
        clauses.append(RETURN_CLAUSE)
        topics.add("returns")
    return " ".join(c.format(p=product, pet=pet) for c in clauses), {"topics": sorted(topics), "names_product": names_product}
