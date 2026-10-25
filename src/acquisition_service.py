"""Where customers come from, and whether they stay (ADR 0040).

One row per visit source, from counts and one `_predict`, all in one `_batch`:

- **Conversion**: a new visitor's sessions that end in a first order, over all
  their sessions (`contexts.first_order`, against landing pages nobody bought from).
  Only visitors who accepted behavioural tracking leave sessions (ADR 0044).
- **Regular**: of the customers who joined at least 6 months before the data
  ends, the share who made 3 or more orders in their first 6 months
  (`customers.became_regular`, a label from later data).
- **Predicted to stay**: `_predict became_regular` from the first source alone,
  with the source's lift out of `$why`.

Then, per source, where its visitors land (`_relate` on `contexts`), and which first-basket
words go with becoming regular (`_relate` on `customers`).
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.aito_compat import related_value
from src.timing import submit_in_request
from src.lift_rows import LiftRow, candidates_from_hits, judge, relate_hits

SOURCES = ("organic_search", "paid_search", "direct", "email", "affiliate", "social")
LANDING_LIMIT = 30
BASKET_LIMIT = 60
Z95 = 1.959964


@dataclass(frozen=True)
class Rate:
    successes: int
    total: int
    low: float
    high: float

    @property
    def share(self) -> float:
        return self.successes / self.total


def wilson(successes: int, total: int) -> Rate:
    """The 95 % Wilson interval of a share: honest at the small counts of a recent cohort."""
    if total <= 0:
        raise AitoError(f"a rate over {total} rows has no interval")
    p = successes / total
    centre = (p + Z95 ** 2 / (2 * total)) / (1 + Z95 ** 2 / total)
    half = Z95 * math.sqrt(p * (1 - p) / total + Z95 ** 2 / (4 * total ** 2)) / (1 + Z95 ** 2 / total)
    return Rate(successes, total, max(0.0, centre - half), min(1.0, centre + half))


@dataclass(frozen=True)
class LandingShare:
    category: str
    lift: float             # the category's share of this source's sessions over its share of all


@dataclass(frozen=True)
class SourceRow:
    source: str
    sessions: int                   # a new visitor's sessions from this source
    conversion: Rate                # first orders over those sessions
    labelled_customers: int
    regular: Rate                   # of the labelled customers, 3+ orders in 6 months
    predicted_regular: float        # `_predict became_regular` from the source alone
    source_lift: float              # the source's lift in that `$why`
    landing: list[LandingShare]     # strongest over-represented landing categories


@dataclass(frozen=True)
class Acquisition:
    sources: list[SourceRow]
    regular_basket: list[LiftRow]   # first-basket words over- or under-represented among regulars
    queries_sent: int
    example_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def source_queries(source: str) -> list[dict]:
    def count(table: str, where: dict) -> dict:
        return {"from": table, "where": where, "limit": 0}

    return [
        count("contexts", {"source": source, "surface": "landing"}),
        count("contexts", {"source": source, "first_order": True}),
        count("customers", {"first_source": source, "became_regular": {"$exists": True}}),
        count("customers", {"first_source": source, "became_regular": True}),
        {"from": "customers", "where": {"first_source": source}, "predict": "became_regular",
         "select": ["$p", "feature", "$why"]},
    ]


def landing_body(source: str) -> dict:
    return {"from": "contexts", "where": {"source": source}, "relate": "landing_category", "limit": LANDING_LIMIT}


def source_row(source: str, answers: list, landing_hits: list[dict]) -> SourceRow:
    landing_sessions, first_orders, labelled, regular, predicted = answers
    sessions = landing_sessions["total"] + first_orders["total"]
    true_hit = next((h for h in predicted["hits"] if h.get("feature") is True), None)
    if true_hit is None:
        raise AitoError(f"_predict became_regular for {source} had no `true` hit: {str(predicted)[:300]}")
    lifts = [f["value"] for f in true_hit["$why"].get("factors", [])
             if f["type"] == "relatedPropositionLift" and f["proposition"] == {"first_source": source}]
    if len(lifts) != 1:
        raise AitoError(f"$why for first_source={source} has {len(lifts)} lifts of the source, expected one")
    over = [LandingShare(str(related_value(h, "landing_category")), float(h["lift"]))
            for h in landing_hits if h["lift"] > 1.2]
    return SourceRow(
        source=source, sessions=sessions, conversion=wilson(first_orders["total"], sessions),
        labelled_customers=labelled["total"], regular=wilson(regular["total"], labelled["total"]),
        predicted_regular=float(true_hit["$p"]), source_lift=float(lifts[0]), landing=over[:3])


def get_acquisition(client: AitoClient) -> Acquisition:
    queries = [q for source in SOURCES for q in source_queries(source)]
    # `_relate` goes through the client one at a time: a batched answer keeps v2's bare
    # values, and `related_value` reads the normalised shape.
    with ThreadPoolExecutor(max_workers=6) as pool:
        landing_jobs = [submit_in_request(pool, relate_hits, client, landing_body(s)) for s in SOURCES]
        answers = client.batch(queries)
        landing = [job.result() for job in landing_jobs]
    per_source = len(queries) // len(SOURCES)
    rows = [source_row(s, answers[i * per_source:(i + 1) * per_source], landing[i]) for i, s in enumerate(SOURCES)]

    body = {"from": "customers", "where": {"became_regular": True}, "relate": "first_basket_categories",
            "limit": BASKET_LIMIT}
    hits = relate_hits(client, body)
    # One customer is one row, so the rows are independent: a design effect of 1.
    basket, _ = judge(candidates_from_hits("first_basket_categories", hits, 1.0))
    return Acquisition(sources=rows, regular_basket=basket, queries_sent=len(queries) + len(SOURCES) + 1, example_query=body)
