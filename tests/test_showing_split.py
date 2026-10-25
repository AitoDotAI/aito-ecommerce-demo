"""The showings log is loaded as two tables, and no row is lost or counted twice (ADR 0045, amendment 2)."""

import pytest

from src.showing_split import split_showings

CONTEXTS = [{"context_id": "ctx-search", "surface": "search"},
            {"context_id": "ctx-direct", "surface": "direct"},
            {"context_id": "ctx-landing", "surface": "landing"}]


def showing(impression_id: str, context: str, placement: str) -> dict:
    return {"impression_id": impression_id, "context": context, "placement": placement}


def test_only_a_list_showing_on_a_ranked_surface_is_ranked():
    ranked_row = showing("i1", "ctx-search", "list")
    unranked_rows = [showing("i2", "ctx-search", "checkout"),   # the shop's add-on, bought 90 % of the time
                     showing("i3", "ctx-direct", "buy_again"),  # what the household came for
                     showing("i4", "ctx-landing", "list")]      # a landing page, nobody buys from it

    ranked, unranked = split_showings([ranked_row, *unranked_rows], CONTEXTS)

    assert ranked == [ranked_row]
    assert unranked == unranked_rows


def test_a_showing_in_an_unknown_context_fails_loudly_rather_than_dropping_out():
    with pytest.raises(ValueError, match="i9.*ctx-missing"):
        split_showings([showing("i9", "ctx-missing", "list")], CONTEXTS)
