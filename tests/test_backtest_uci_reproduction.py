"""The backtest reproduces Aito core's baseline numbers on UCI (ADR 0036).

Runs on `data/uci/` from `./do uci-prepare` (gitignored: the UCI file is
not in the repo), and skips with that reason where it is absent. The
expected counts are the benchmark's `retail2/analysis.json` at aito-core
625867faca, exactly: the baselines are deterministic.
"""

from __future__ import annotations

import pytest

from src.backtest_metrics import slice_results
from src.backtest_run import baseline_rankings
from src.backtest_uci import load_uci_dataset
from src.uci_outcomes import UCI_DATA_DIR

pytestmark = pytest.mark.skipif(not (UCI_DATA_DIR / "new_buyers.json").exists(),
                                reason="data/uci/ not prepared: run ./do uci-prepare (needs the UCI xlsx)")


def test_the_three_baselines_reproduce_the_benchmarks_hits_in_every_slice():
    dataset = load_uci_dataset()
    test_codes = {customer: order.codes for customer, order in dataset.test_orders.items()}

    slices = slice_results(baseline_rankings(dataset), test_codes, dataset.prior_orders())

    hits = {s.name: {m: round(i.mean * s.buyers) for m, i in s.hit1.items()} for s in slices}
    assert {s.name: s.buyers for s in slices} == {"0": 630, "1–2": 636, "3+": 1708}
    # 1–2: popularity 0.0833, personal repeat 0.1447, EASE 0.1541 (n = 636).
    assert hits["1–2"] == {"popularity": 53, "personal repeat": 92, "EASE": 98}
    assert hits["3+"] == {"popularity": 185, "personal repeat": 724, "EASE": 425}
    assert hits["0"] == {"popularity": 37, "personal repeat": 37, "EASE": 37}   # both fall back to popularity
