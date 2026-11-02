"""ADR 0044: what a shop can know about a person.

Behaviour (visits, impressions) is recorded only for shoppers who consented;
orders exist for everyone. Sex comes from the purchase form and never ranks
products. C1–C3 themselves are judged by `./do planted-effects`
(docs/verification/actionable-states-prereg.md, ADR 0044 addendum).
"""

import re
from pathlib import Path

from tests.fixture_joins import load

SRC = Path(__file__).resolve().parent.parent / "src"


def test_no_context_or_impression_belongs_to_a_non_consenting_customer():
    declined = {c["customer_id"] for c in load("customers.json") if not c["consent_behavioural"]}
    contexts = load("contexts.json")
    assert declined, "every customer consented: the consent draw is missing"
    assert not [c["context_id"] for c in contexts if c.get("customer") in declined]
    # Impressions reach a customer only through their context.
    known = {c["context_id"] for c in contexts}
    assert all(i["context"] in known for i in load("impressions.json"))


def test_non_consenting_customers_still_have_their_orders():
    declined = {c["customer_id"] for c in load("customers.json") if not c["consent_behavioural"]}
    buyers = {o["customer_id"] for o in load("orders.json")}
    assert declined <= buyers


def test_the_answer_key_records_consent_as_the_customers_table_does():
    consent = {c["customer_id"]: c["consent_behavioural"] for c in load("customers.json")}
    key = {t["customer_id"]: t["consent_behavioural"] for t in load("answer_key/customer_traits.json")}
    assert key == consent


def test_a_postcode_area_lies_in_the_customers_region():
    from data.person_data import POSTCODE_AREAS
    for c in load("customers.json"):
        assert int(c["postcode_area"]) in POSTCODE_AREAS[c["region"]], c["customer_id"]


def test_no_ranking_query_conditions_on_sex():
    # The Shop's ranking and search modules, and the recommenders.
    rankers = [*SRC.glob("shop_*.py"), SRC / "search_service.py", SRC / "recommend_service.py"]
    mentions = [f.name for f in rankers if f.exists() and re.search(r"""["']([\w.]*\.)?sex["']""", f.read_text())]
    assert not mentions, mentions
