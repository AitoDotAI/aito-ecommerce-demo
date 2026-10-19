"""Shop analytics, search words: which query words convert above and
below the average search (ADR 0031).

`contexts.search_query` is a whitespace Text column, set only on the
`search` surface; impressions reach it as `context.search_query` (ADR 0033). Relating it returns one hit per word, `$has` form.

**Baseline.** `where {surface: "search", purchased: true}` alone compares
against the wrong baseline: `_relate` divides by the word's share of
*all* impressions, and only search impressions have a query, so every
word came out about 2.5× ("food" 2.76×, though it converts slightly
below the average search). A nested `from` would restrict the
population, but `_relate` answers 501 to that on 2.11.4. So the view
sends the query with and without `purchased`, and divides the counts:

  lift = (purchases with the word / search purchases)
       / (impressions with the word / search impressions)

**Clustering.** One search shows 6–14 products under one query, and a
customer searches many times; the design effect for purchases among
search impressions widens every interval (`src/design_effect.py`).

**Phrases.** Words that only ever appear together ("algae" and "wafers")
have identical counts and are one finding, not two. Words with identical
counts are checked with a `_search` for searches holding all of them,
and merged into one phrase ("algae wafers") when that count matches.

**Never bought.** A word shown in searches that never ended in a purchase
has no `_relate` hit among purchases. Those words are listed with their
impressions and the purchases the average would expect; zero purchases
can't be given a lift interval of this kind.
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from src.aito_client import AitoClient, AitoError
from src.aito_compat import related_value
from src.design_effect import DesignEffect, customer_bodies, design_effect, rows_per_customer
from src.lift_rows import Candidate, Significance, judge, relate_hits
from src.timing import submit_in_request

SEARCH = {"context.surface": "search"}
SEARCH_PURCHASED = {"context.surface": "search", "purchased": True}
QUERY = "context.search_query"   # a whitespace Text column on the context (ADR 0033)
# Above the vocabulary of the generated queries (99 words on 2026-10-13),
# so a full page means words may be missing and the call raises.
WORD_LIMIT = 500


@dataclass(frozen=True)
class SearchWordRow:
    word: str                # one word, or a phrase of words always searched together
    lift: float              # conversion with the word / conversion of all searches
    interval_low: float
    interval_high: float
    purchases: int
    impressions: int


@dataclass(frozen=True)
class NeverBoughtWord:
    word: str
    impressions: int
    expected_purchases: float   # impressions × the average search's conversion


@dataclass
class SearchWordSection:
    rows: list[SearchWordRow]           # strongest first, family-wise interval excluding 1
    never_bought: list[NeverBoughtWord]
    words: int                          # after merging phrases
    search_impressions: int
    search_purchases: int
    clustering: DesignEffect
    significance: Significance          # `tested` is the testable words
    queries_sent: int
    example_query: dict

    def to_dict(self) -> dict:
        return asdict(self)


def search_words_bodies() -> tuple[dict, dict]:
    def body(where: dict) -> dict:
        return {"from": "impressions", "where": where, "relate": QUERY, "limit": WORD_LIMIT}

    return body(SEARCH_PURCHASED), body(SEARCH)


def together_count_query(words: tuple[str, ...]) -> dict:
    return {"$and": [SEARCH] + [{QUERY: {"$match": w}} for w in words]}


def _counts_by_word(hits: list[dict]) -> tuple[dict[str, float], float]:
    counts = {related_value(h, QUERY): h["fs"]["fOnCondition"] for h in hits}
    # Every hit of one `_relate` shares its condition, so fCondition is one
    # number; two would mean the hits answer different questions.
    conditions = {h["fs"]["fCondition"] for h in hits}
    if len(conditions) != 1:
        raise AitoError(f"{QUERY} _relate hits disagree on their condition count: {sorted(conditions)}")
    return counts, conditions.pop()


def _phrases(client: AitoClient, bought: dict, shown: dict) -> tuple[list[tuple[str, ...]], int]:
    """Words grouped by identical (purchases, impressions). A group becomes
    one phrase only if the searches holding all its words are as many as
    those holding each; one such search gives the words' order. Also
    returns how many `_search`es were sent."""
    groups: dict[tuple, list[str]] = defaultdict(list)
    for word, impressions in shown.items():
        groups[(bought.get(word, 0), impressions)].append(word)
    phrases, checks = [], 0
    for (_, impressions), words in groups.items():
        if len(words) == 1:
            phrases.append((words[0],))
            continue
        checks += 1
        res = client.search("impressions", where=together_count_query(tuple(words)), limit=0)
        if res["total"] != impressions:
            phrases.extend((w,) for w in words)
            continue
        # One search that held them all, read from the contexts table itself.
        found = client.search("contexts", where={"surface": "search", "search_query": {
            "$and": [{"$match": w} for w in words]}}, select=["search_query"], limit=1)["hits"]
        example = found[0]["search_query"].split()
        if not set(words) <= set(example):
            raise AitoError(f"search {example} matched {words} but doesn't hold them as words")
        phrases.append(tuple(sorted(words, key=example.index)))
    return phrases, checks


def get_search_words_section(client: AitoClient) -> SearchWordSection:
    bought_body, shown_body = search_words_bodies()
    customers_body, buyers_body = customer_bodies("impressions", "context.customer", SEARCH, SEARCH_PURCHASED)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [submit_in_request(pool, relate_hits, client, b)
                for b in (bought_body, shown_body, customers_body, buyers_body)]
        bought_hits, shown_hits, customer_hits, buyer_hits = (j.result() for j in jobs)

    bought, search_purchases = _counts_by_word(bought_hits)
    shown, search_impressions = _counts_by_word(shown_hits)
    missing = set(bought) - set(shown)
    if missing:
        raise AitoError(f"search words {sorted(missing)} were bought from search but never shown on search")
    clustering = design_effect(rows_per_customer(customer_hits, "context.customer"),
                               rows_per_customer(buyer_hits, "context.customer"))
    phrases, phrase_checks = _phrases(client, bought, shown)
    average = search_purchases / search_impressions

    candidates, never_bought, impressions_by_label = [], [], {}
    for words in phrases:
        label, purchases, impressions = " ".join(words), bought.get(words[0], 0), shown[words[0]]
        impressions_by_label[label] = impressions
        if purchases == 0:
            never_bought.append(NeverBoughtWord(label, int(impressions), round(impressions * average, 1)))
            continue
        lift = (purchases / search_purchases) / (impressions / search_impressions)
        fs = {"fOnCondition": purchases, "fCondition": search_purchases, "f": impressions, "n": search_impressions}
        candidates.append(Candidate(QUERY, label, lift, fs, clustering.design_effect))

    rows, significance = judge(candidates)
    return SearchWordSection(
        rows=[SearchWordRow(r.value, r.lift, r.interval_low, r.interval_high,
                            r.rows_with_value, int(impressions_by_label[r.value])) for r in rows],
        never_bought=sorted(never_bought, key=lambda w: w.expected_purchases, reverse=True),
        words=len(phrases),
        search_impressions=int(search_impressions), search_purchases=int(search_purchases),
        clustering=clustering, significance=significance,
        queries_sent=4 + phrase_checks,
        example_query={"endpoint": "_relate", "body": bought_body},
    )
