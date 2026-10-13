"""Search words — which query words convert above and below average.

`impressions.search_query` is a whitespace Text column, set only on the
`search` surface. Relating it returns one hit per word, `$has` form
(Text keeps `$has` on v2).

The obvious query, `where {surface: "search", purchased: true}`, compares
against the wrong baseline. `_relate` divides by the word's share of
*all* impressions, and only search impressions have a query, so every
word comes out about 2.5× (probe, 2026-10-13: "food" 2.76×, though it
converts slightly below the search average). A nested `from` would
restrict the population, but `_relate` answers 501 to that on 2.11.4.

So the view sends two `_relate`s on the same field and divides their
counts:

  bought = where {surface: search, purchased: true}  → fOnCondition per word
  shown  = where {surface: search}                   → fOnCondition per word

  lift = (bought_w / search purchases) / (shown_w / search impressions)
       = conversion of searches with the word / conversion of all searches

The interval is `lift_interval` on the same four counts, with search
impressions as the population.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.aito_client import AitoError
from src.aito_compat import related_value
from src.lift_rows import by_strength, lift_row


SEARCH = {"surface": "search"}
SEARCH_PURCHASED = {"surface": "search", "purchased": True}
# Above the vocabulary of the generated queries (99 words on 2026-10-13),
# so a full page means words may be missing and the call raises.
WORD_LIMIT = 500


@dataclass(frozen=True)
class SearchWordRow:
    word: str
    lift: float              # conversion with the word / conversion of all searches
    interval_low: float
    interval_high: float
    purchases: int           # search impressions with the word that ended in a purchase
    impressions: int         # search impressions with the word


@dataclass(frozen=True)
class SearchWords:
    rows: list[SearchWordRow]           # strongest first, interval excluding 1
    words_checked: int                  # every word that led to a purchase
    search_impressions: int
    search_purchases: int


def search_words_bodies() -> tuple[dict, dict]:
    def body(where: dict) -> dict:
        return {"from": "impressions", "where": where, "relate": "search_query", "limit": WORD_LIMIT}

    return body(SEARCH_PURCHASED), body(SEARCH)


def _counts_by_word(hits: list[dict]) -> dict[str, dict]:
    return {related_value(hit, "search_query"): hit["fs"] for hit in hits}


def search_words_from_hits(bought_hits: list[dict], shown_hits: list[dict]) -> SearchWords:
    bought = _counts_by_word(bought_hits)
    shown = _counts_by_word(shown_hits)
    search_purchases = _one_condition_count(bought, "search purchases")
    search_impressions = _one_condition_count(shown, "search impressions")

    rows = []
    for word, fs in bought.items():
        if word not in shown:
            raise AitoError(f"search word {word!r} was bought from search but never shown on search")
        purchases, impressions = fs["fOnCondition"], shown[word]["fOnCondition"]
        lift = (purchases / search_purchases) / (impressions / search_impressions)
        counts = {"fOnCondition": purchases, "fCondition": search_purchases,
                  "f": impressions, "n": search_impressions}
        row = lift_row("search_query", word, lift, counts)
        if row is not None:
            rows.append(SearchWordRow(
                word=row.value, lift=row.lift,
                interval_low=row.interval_low, interval_high=row.interval_high,
                purchases=int(purchases), impressions=int(impressions),
            ))
    return SearchWords(
        rows=by_strength(rows),
        words_checked=len(bought),
        search_impressions=int(search_impressions),
        search_purchases=int(search_purchases),
    )


def _one_condition_count(fs_by_word: dict[str, dict], what: str) -> float:
    # Every hit of one `_relate` shares its condition, so fCondition is one
    # number; two would mean the hits answer different questions.
    counts = {fs["fCondition"] for fs in fs_by_word.values()}
    if len(counts) != 1:
        raise AitoError(f"_relate hits disagree on the number of {what}: {sorted(counts)}")
    return counts.pop()

