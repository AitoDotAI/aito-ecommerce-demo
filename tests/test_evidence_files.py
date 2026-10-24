"""The Evidence pages' committed result files, and how they word a result (ADR 0037 §2).

Each page renders `data/evidence/<entry>.json`, written by `./do evidence
<entry>`; none runs a benchmark live. These tests read the committed files
as a reader would, and hold every sentence in them to the wording rules:
a difference whose interval spans 0 is "a tie", and a lead is stated only
when its interval excludes 0.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.evidence import result_file
from src.evidence.search_relevance import REPORT, summarise
from src.evidence.wording import accuracy_interval, difference_sentence, is_tie, unpaired_difference
from src.search_eval.relevance import load_queries

ROOT = Path(__file__).resolve().parent.parent


def committed(entry: str) -> dict:
    path = result_file.EVIDENCE_DIR / f"{entry}.json"
    if not path.exists():
        pytest.skip(f"{path.name} not written yet: run ./do evidence {entry}")
    return json.loads(path.read_text(encoding="utf-8"))


# ── The shared wording rule ──────────────────────────────────────────


def test_a_difference_whose_interval_spans_zero_is_a_tie():
    assert difference_sentence("Aito", "naive", -0.033, -0.086, 0.019, "-3.3 pp [-8.6, +1.9]") == (
        "Aito and naive: a tie, -3.3 pp [-8.6, +1.9]; the interval spans 0.")


def test_a_lead_names_the_side_its_interval_favours():
    assert difference_sentence("Aito", "always stays", 0.31, 0.25, 0.37, "+31 pp").startswith(
        "Aito is ahead of always stays")
    assert difference_sentence("Aito", "naive", -0.2, -0.3, -0.1, "-20 pp").startswith("naive is ahead of Aito")


def test_an_accuracy_interval_is_95_percent_normal():
    low, high = accuracy_interval(0.5, 100)
    assert (round(low, 3), round(high, 3)) == (0.402, 0.598)


def test_an_unpaired_difference_is_wider_than_either_accuracys_own_interval():
    _, low, high = unpaired_difference(0.6, 0.5, 400)
    own_low, own_high = accuracy_interval(0.6, 400)
    assert high - low > own_high - own_low


# ── Every committed sentence obeys it ────────────────────────────────


def _worded(entry: str) -> list[dict]:
    """Each worded comparison in a file: its sentence and its interval."""
    f = committed(entry)
    if entry == "model-checks":
        return [c for m in f["models"] for c in m["comparisons"]] + f["churn"]["comparisons"] + f["demand"]["comparisons"]
    if entry == "search-relevance":
        return f["comparisons"] + list(f["out_of_sample"]["one_split"]["by_persona"].values())
    return [{"sentence": sentence, "low": c["difference"]["low"], "high": c["difference"]["high"]}
            for s in f["slices"] for sentence, c in zip(s["sentences"], s["comparisons"]) if s["sessions"] >= 30]


@pytest.mark.parametrize("entry", result_file.ENTRIES)
def test_every_committed_sentence_calls_a_spanning_interval_a_tie_and_nothing_else_a_tie(entry):
    for c in _worded(entry):
        tie = is_tie(c["low"], c["high"])
        assert ("a tie" in c["sentence"]) == tie, c
        assert ("ahead" in c["sentence"]) == (not tie), c


def test_synthetic_entries_say_so():
    for entry in result_file.ENTRIES:
        assert committed(entry)["data"] == "Synthetic"


@pytest.mark.parametrize("entry", result_file.ENTRIES)
def test_every_file_records_its_date_command_and_aito_version(entry):
    run = committed(entry)["run"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\d", run["date"])
    assert run["command"].startswith("./do ")
    assert re.fullmatch(r"\d+\.\d+\.\d+", run["aito_version"])


# ── Search relevance: derived, not re-run ────────────────────────────


def test_search_relevance_recomputes_the_reports_own_intervals():
    """The page's intervals are the Markdown report's: same rows, same seeded bootstrap."""
    summary = summarise(json.loads(REPORT.read_text(encoding="utf-8")), load_queries())
    report = (ROOT / "docs" / "verification" / "search-eval.md").read_text(encoding="utf-8")
    first = summary["comparisons"][0]
    assert f"{first['difference']:+.3f} [{first['low']:+.3f}, {first['high']:+.3f}]" in report


def test_search_relevance_file_matches_a_fresh_derivation():
    f = committed("search-relevance")
    summary = summarise(json.loads(REPORT.read_text(encoding="utf-8")), load_queries())
    assert f["comparisons"] == summary["comparisons"]


# ── What the endpoint serves (`/api/evidence/<entry>`) ───────────────


def test_the_served_file_is_the_committed_file_as_is():
    assert result_file.served("model-checks") == committed("model-checks")


def test_the_served_file_leaves_out_the_per_session_rows():
    f = committed("personalised-search")
    served = result_file.served("personalised-search")
    assert "per_session" in f and "per_session" not in served
    assert served["slices"] == f["slices"]


def test_an_entry_that_does_not_exist_is_a_key_error_the_endpoint_answers_404():
    with pytest.raises(KeyError, match="no-such-entry"):
        result_file.served("no-such-entry")
