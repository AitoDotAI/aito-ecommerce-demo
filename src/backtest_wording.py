"""What a backtest report may say about each slice: ADR 0036's wording rules, in code.

- A slice whose interval for Aito − best baseline spans 0 is "a tie".
- The 0-prior-orders slice is "a fallback" ("Aito equals popularity
  here") when the two point estimates are equal.
- No sentence claims a win outside the slices whose interval excludes 0.
- A slice under 30 buyers is "too few to read": its interval is shown,
  no conclusion is drawn from it.

Every sentence comes from `verdict()`, and `slice_sentence` refuses to
emit win wording for any other verdict.
"""

from __future__ import annotations

from enum import Enum

from src.backtest_metrics import AITO, Interval, SliceResult

TOO_FEW_TO_READ = 30
# A sentence claims a win for Aito when it says one of these.
WIN_CLAIMS = ("Aito ahead", "Aito beats", "Aito wins", "Aito outperforms", "Aito is better")


class Verdict(Enum):
    NO_BUYERS = "no buyers"
    NOT_RUN = "Aito not run"
    TOO_FEW = "too few to read"
    FALLBACK = "a fallback"
    TIE = "a tie"
    AITO_AHEAD = "Aito ahead"
    BASELINE_AHEAD = "best baseline ahead"


def slice_label(name: str) -> str:
    return f"{name} prior orders"


def verdict(result: SliceResult) -> Verdict:
    if result.buyers == 0:
        return Verdict.NO_BUYERS
    if result.buyers < TOO_FEW_TO_READ:
        return Verdict.TOO_FEW
    if AITO not in result.hit1:
        return Verdict.NOT_RUN
    if result.name == "0" and result.hit1[AITO].mean == result.hit1["popularity"].mean:
        return Verdict.FALLBACK
    if result.aito_minus_best.spans_zero():
        return Verdict.TIE
    return Verdict.AITO_AHEAD if result.aito_minus_best.low > 0 else Verdict.BASELINE_AHEAD


def slice_sentence(result: SliceResult) -> str:
    v = verdict(result)
    sentence = _sentence(result, v)
    if any(claim in sentence for claim in WIN_CLAIMS) and v is not Verdict.AITO_AHEAD:
        raise AssertionError(f"Wording rule broken: {sentence!r} claims a win, the verdict is {v.value!r}")
    return sentence


def _sentence(result: SliceResult, v: Verdict) -> str:
    label = slice_label(result.name).capitalize()
    if v is Verdict.NO_BUYERS:
        return f"{label}: no buyers in this slice."
    best = result.best_baseline
    if v is Verdict.NOT_RUN:
        return f"{label}: Aito not run; the best baseline here is {best}, hit@1 {pct(result.hit1[best].mean)}."
    if v is Verdict.TOO_FEW:
        return (f"{label}: too few to read ({result.buyers} buyers, under {TOO_FEW_TO_READ}). "
                f"The interval is shown; no conclusion is drawn.")
    aito, other, diff = result.hit1[AITO].mean, result.hit1[best].mean, result.aito_minus_best
    if v is Verdict.FALLBACK:
        return f"{label}: a fallback. Aito equals popularity here (hit@1 {pct(aito)} each)."
    compared = f"Aito {pct(aito)} vs {best} {pct(other)} hit@1, difference {signed_interval(diff)}"
    if v is Verdict.TIE:
        return f"{label}: a tie. {compared}; the interval spans 0."
    if v is Verdict.AITO_AHEAD:
        return f"{label}: Aito ahead of {best}. {compared}; the interval excludes 0."
    return f"{label}: {best} ahead of Aito. {compared}; the interval excludes 0."


def pct(value: float) -> str:
    return f"{value:.1%}"


def interval_text(interval: Interval) -> str:
    if interval.low is None:
        return f"{interval.mean:.4f} [n/a]"
    return f"{interval.mean:.4f} [{interval.low:.4f}, {interval.high:.4f}]"


def signed_interval(interval: Interval) -> str:
    if interval.low is None:
        return f"{interval.mean:+.4f} [n/a]"
    return f"{interval.mean:+.4f} [{interval.low:+.4f}, {interval.high:+.4f}]"
