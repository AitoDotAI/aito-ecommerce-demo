"""What the personalised-search page may say: ADR 0037 §2's wording rules, in code.

- A difference whose interval spans 0 is "a tie".
- No sentence claims a lead outside the intervals that exclude 0.
- A slice under 30 sessions is "too few to read": its numbers are shown,
  no conclusion is drawn.

Every sentence comes from `verdict()`, and `comparison_sentence` refuses to
emit lead wording for any other verdict. The page renders these sentences;
it never words a result itself.
"""

from __future__ import annotations

from enum import Enum

from src.personalised_search.metrics import ALL, TOO_FEW_TO_READ, Comparison, SliceScores

LEAD_WORDS = ("ahead", "beats", "better", "wins", "outperforms")


class Verdict(Enum):
    TOO_FEW = "too few to read"
    TIE = "a tie"
    AHEAD = "ahead"
    BEHIND = "behind"


def verdict(sessions: int, comparison: Comparison) -> Verdict:
    if sessions < TOO_FEW_TO_READ:
        return Verdict.TOO_FEW
    d = comparison.difference
    if d.spans_zero():
        return Verdict.TIE
    return Verdict.AHEAD if d.low > 0 else Verdict.BEHIND


def slice_label(name: str) -> str:
    return "All sessions" if name == ALL else f"{name.replace('-', '–')} prior orders"


def comparison_sentence(scores: SliceScores, comparison: Comparison) -> str:
    v = verdict(scores.sessions, comparison)
    sentence = _sentence(scores, comparison, v)
    if any(word in sentence for word in LEAD_WORDS) and v not in (Verdict.AHEAD, Verdict.BEHIND):
        raise AssertionError(f"Wording rule broken: {sentence!r} claims a lead, the verdict is {v.value!r}")
    return sentence


def _sentence(scores: SliceScores, c: Comparison, v: Verdict) -> str:
    label = slice_label(scores.name)
    if v is Verdict.TOO_FEW:
        return (f"{label}: too few to read ({scores.sessions} sessions, under {TOO_FEW_TO_READ}). "
                "The numbers are shown; no conclusion is drawn.")
    a, b = scores.hit10[c.ranking].mean, scores.hit10[c.against].mean
    compared = f"hit@10 {pct(a)} vs {pct(b)}, difference {points(c.difference)}"
    if v is Verdict.TIE:
        return f"{label}: {c.ranking} and {c.against} are a tie. {compared}; the interval spans 0."
    leader, other = (c.ranking, c.against) if v is Verdict.AHEAD else (c.against, c.ranking)
    return f"{label}: {leader} is ahead of {other}. {compared}; the interval excludes 0."


def headline(scores: SliceScores) -> str:
    """The index's one line: the shipped search against BM25, over every session."""
    shop_vs_bm25 = scores.comparisons[0]
    return comparison_sentence(scores, shop_vs_bm25).removeprefix(f"{slice_label(scores.name)}: ")


def pct(value: float) -> str:
    return f"{value:.1%}"


def points(interval) -> str:
    """A hit@10 difference in percentage points: "+4.2 pp [+2.0, +6.4]"."""
    if interval.low is None:
        return f"{interval.mean * 100:+.1f} pp [n/a]"
    return f"{interval.mean * 100:+.1f} pp [{interval.low * 100:+.1f}, {interval.high * 100:+.1f}]"
