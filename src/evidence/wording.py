"""ADR 0037 §2's wording rule for a difference, shared by the Evidence writers.

- A difference whose interval spans 0 is "a tie".
- A lead is stated only when the interval excludes 0, in its direction.

`difference_sentence` is the only way a writer words a comparison, and it
refuses lead wording for a tie. (Personalised search adds the "too few to
read" rule for its slices: `src/personalised_search/wording.py`.)
"""

from __future__ import annotations

import math

Z_95 = 1.96
LEAD_WORDS = ("ahead", "beats", "better", "wins", "outperforms")


def is_tie(low: float, high: float) -> bool:
    return low <= 0 <= high


def difference_sentence(arm: str, base: str, difference: float, low: float, high: float, shown: str) -> str:
    """`shown` is the difference as the page prints it, e.g. "+0.225 nDCG@10 [+0.141, +0.318]"."""
    if is_tie(low, high):
        sentence = f"{arm} and {base}: a tie, {shown}; the interval spans 0."
        if any(word in sentence for word in LEAD_WORDS):
            raise AssertionError(f"Wording rule broken: {sentence!r} claims a lead on a tie")
        return sentence
    leader, other = (arm, base) if low > 0 else (base, arm)
    return f"{leader} is ahead of {other}: {shown}; the interval excludes 0."


def accuracy_interval(accuracy: float, n: int) -> tuple[float, float]:
    """A 95 % normal interval for a share of n held-out rows."""
    if n < 1:
        raise ValueError("An accuracy over no rows has no interval")
    half = Z_95 * math.sqrt(accuracy * (1 - accuracy) / n)
    return accuracy - half, accuracy + half


def unpaired_difference(a: float, b: float, n: int) -> tuple[float, float, float]:
    """a − b for two accuracies on the same n rows, with a 95 % interval that
    treats them as independent. `_evaluate` returns totals, not each row's
    answer, so the pairing can't be used; for two methods right on mostly the
    same rows this interval is wider than the paired one would be."""
    half = Z_95 * math.sqrt((a * (1 - a) + b * (1 - b)) / n)
    return a - b, a - b - half, a - b + half
