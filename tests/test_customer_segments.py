"""The bootstrap interval behind the profit-per-customer ranges (src/customer_segments.py)."""

import time

from src.customer_segments import bootstrap_mean_interval


def test_bootstrap_interval_is_fast_enough_for_a_request_and_repeatable():
    # A segment view asks for ~45 of these; in pure Python each cost ~0.2 s, which made the first click on a new segment take 10-50 s.
    values = [float(i % 37) for i in range(1500)]
    started = time.perf_counter()
    low, high = bootstrap_mean_interval(values)
    assert time.perf_counter() - started < 0.1
    assert low < sum(values) / len(values) < high
    assert bootstrap_mean_interval(values) == [low, high]
