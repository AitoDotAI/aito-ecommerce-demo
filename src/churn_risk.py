"""Who is about to leave? Each active customer's latest order, scored by Aito.

`churned_in_3_months` on a `customer_months` row is true when the
customer orders nothing in the three months after it. Two kinds of row
can't teach that:

  - the latest three months: their three months after aren't in the data
    yet, so a "false" there is not known, only not yet true;
  - the months after a customer's last order: the customer has already
    gone, and "no orders this month" nearly IS the label. A model trained
    on them learns the definition of churn, not its warning signs (this is
    how the old Churn view scored 96 %).

So the `_predict` sets its population with a nested `from`: the months in
which the customer ordered, up to the last month whose follow-up is in
the data. The question becomes "is this order their last for three
months?", which a shop can only answer in hindsight, and Aito learns it
from the orders whose hindsight exists.

Each active customer (an order in the last three months) is scored on the
month of their latest order. Rows go to Aito in `_batch`es: 2,000 single
`_predict`s would cost 2,000 round trips. The `$why` is asked only for
the customers the view lists (`explain`).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError
from src.catalogue_reads import read_all
from src.why_processor import process_why

LATEST_MONTH = "2026-04"
LABEL_KNOWN_UNTIL = "2026-01"     # LATEST_MONTH minus the label's three months of follow-up
POPULATION = {"from": "customer_months",
              "where": {"month": {"$lte": LABEL_KNOWN_UNTIL}, "purchases": {"$gte": 1}}}

# What the shop knows of a customer in a month: declared and recorded
# profile, tenure, the month's activity and its latest review (ADR 0033).
FEATURES = ["pets", "dog_size", "region", "tenure_months_at_month", "visits", "purchases",
            "spent_eur", "latest_rating", "latest_sentiment", "latest_category"]

LIKELY = 0.5          # more likely to stop ordering than not
VERY_LIKELY = 0.8
BATCH_SIZE = 100

_WHY_SELECT = ["$p", "feature", {"$why": {"highlight": {
    "posPreTag": "«", "posPostTag": "»", "negPreTag": "‹", "negPostTag": "›"}}}]


@dataclass(frozen=True)
class ScoredCustomer:
    customer_id: str
    name: str
    pets: str | None               # declared; most households declare none (src/retention_pets.py)
    dog_size: str | None
    region: str
    last_order_month: str
    tenure_months: int
    visits: int                    # in the month of their latest order
    latest_rating: int | None
    risk_p: float                  # Aito's P(no order in the three months after it)
    evidence: dict                 # the `where` it was scored on

    @property
    def risk(self) -> str:
        return "very likely" if self.risk_p >= VERY_LIKELY else "likely" if self.risk_p >= LIKELY else "unlikely"


def evidence_of(row: dict) -> dict:
    """A customer-month's known fields. Nullable ones (dog size, the review)
    are left out when empty: Aito refuses `where: {field: null}`."""
    return {f: row[f] for f in FEATURES if row.get(f) is not None}


def predict_body(evidence: dict, *, with_why: bool = True) -> dict:
    return {"from": POPULATION, "where": evidence, "predict": "churned_in_3_months",
            "limit": 2, "select": _WHY_SELECT if with_why else ["$p", "feature"]}


def latest_order_rows(client: AitoClient) -> list[tuple[dict, dict]]:
    """(customer, their row in the month of their latest order) per active customer.
    Active means ordered and not churned: a customer who never ordered has no latest order, and is
    `churned: false` only because the label counts from the last order."""
    active = {c["customer_id"]: c for c in client.search(
        "customers", where={"churned": False, "last_order_month": {"$exists": True}}, limit=10_000)["hits"]}
    recent = read_all(client, "customer_months", where={"month": {"$gt": LABEL_KNOWN_UNTIL}})
    rows = {r["customer_id"]: r for r in recent
            if r["customer_id"] in active and r["month"] == active[r["customer_id"]]["last_order_month"]}
    missing = set(active) - set(rows)
    if missing:
        raise AitoError(f"{len(missing)} active customers have no customer_months row for their last "
                        f"order month after {LABEL_KNOWN_UNTIL}, e.g. {sorted(missing)[:3]}")
    return [(active[cid], rows[cid]) for cid in sorted(rows)]


def score_active_customers(client: AitoClient) -> list[ScoredCustomer]:
    pairs = latest_order_rows(client)
    chunks = [pairs[i:i + BATCH_SIZE] for i in range(0, len(pairs), BATCH_SIZE)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda chunk: client.batch([predict_body(evidence_of(r), with_why=False) for _, r in chunk]), chunks))
    scored = []
    for chunk, answers in zip(chunks, results):
        for (customer, row), answer in zip(chunk, answers, strict=True):
            scored.append(_scored(customer, row, _true_hit(answer, row)))
    return scored


def explain(client: AitoClient, customers: list[ScoredCustomer]) -> dict[str, dict | None]:
    """The `$why` behind each listed customer's score, in one `_batch`."""
    if not customers:
        return {}
    answers = client.batch([predict_body(c.evidence) for c in customers])
    explained = {}
    for c, answer in zip(customers, answers, strict=True):
        hit = _true_hit(answer, c.evidence)
        explained[c.customer_id] = process_why(hit.get("$why"), True, actual_p=float(hit["$p"]))
    return explained


def _true_hit(answer: dict, evidence: dict) -> dict:
    hit = next((h for h in answer["hits"] if h["feature"] is True), None)
    if hit is None:
        raise AitoError(f"_predict churned_in_3_months for {evidence} has no true hit: {answer}")
    return hit


def _scored(customer: dict, row: dict, hit: dict) -> ScoredCustomer:
    p = float(hit["$p"])
    return ScoredCustomer(
        customer_id=customer["customer_id"], name=customer["name"], pets=customer.get("pets"),
        dog_size=customer.get("dog_size"), region=customer["region"],
        last_order_month=customer["last_order_month"],
        tenure_months=int(row["tenure_months_at_month"]), visits=int(row["visits"]),
        latest_rating=row.get("latest_rating"), risk_p=round(p, 4), evidence=evidence_of(row),
    )
