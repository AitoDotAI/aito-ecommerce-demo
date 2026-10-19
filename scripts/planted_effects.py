#!/usr/bin/env python3
"""Is each of ADR 0032's planted effects in the data? Judged against a null.

    ./do planted-effects

For seeds 42, 7 and 99, the fixtures are generated once as planted and
once per effect with that effect switched off (the null). A check passes
when `metric(planted) ÷ metric(null)` clears its margin on every seed:
time trends, selection and every other confound appear in both runs.
Design and margins: docs/verification/product-states-prereg.md (amendment
after the second generation). Writes docs/verification/product-states-data.md.
Nothing is written to `data/`: each run goes to a temporary dir.
"""
from __future__ import annotations

import contextlib
import io
import operator
import shutil
import sys
import tempfile
from pathlib import Path

import data.generate_fixtures as generator
from data import catalogue_events as events
from data import observable
from scripts import planted_effect_metrics as metrics

SEEDS = (42, 7, 99)
REPORT = Path(__file__).resolve().parent.parent / "docs/verification/product-states-data.md"

# Each null switches one planted effect off by setting its constants to "no effect".
NULLS = {
    "offers": {"OFFER_ODDS": {k: 1.0 for k in events.OFFER_ODDS}},
    "launch pull": {"LAUNCH_PICK_FACTOR": 1.0, "RIVAL_PICK_FACTOR": 1.0, "RECONSIDER_AFTER_RIVAL": 1.0,
                    "SWITCH_TO_RIVAL": False,
                    "NEW_ODDS": {k: 1.0 for k in events.NEW_ODDS}},
    "price rise": {"RISE_RANGE": (1.0, 1.0)},
    "stars": {"STARS_ODDS": {k: 1.0 for k in events.STARS_ODDS}},
    "pack size": {"PACK_FIT": 1.0},
    "kit progression": {"observable.KIT_PROGRESSION": False},
}

# (check, null, metric, comparison, margin) for planted ÷ null.
CHECKS = [
    ("P1a budget shoppers buy on offer", "offers", lambda fx: metrics.offer_ratio(fx, "budget"), operator.ge, 1.5),
    ("P1b premium shoppers barely", "offers", lambda fx: metrics.offer_ratio(fx, "premium"), operator.le, 1.3),
    ("P2b a new product's pull", "launch pull", metrics.launch_pull, operator.ge, 1.3),
    ("P2c incumbents lose to a launch", "launch pull", metrics.incumbents_after_launch, operator.le, 0.95),
    ("P2d flexible shoppers take to new", "launch pull", metrics.flexible_take_to_new, operator.ge, 1.25),
    ("P3a a price rise lowers sales", "price rise", metrics.sales_after_rise, operator.le, 0.92),
    ("P4a stars sell", "stars", metrics.stars_sell, operator.ge, 1.15),
    ("P5a big bags for big dogs", "pack size", metrics.big_bags_for_big_dogs, operator.ge, 1.8),
    ("K1a the kit's next item", "kit progression", metrics.kit_next_item, operator.ge, 2.0),
    ("K1b an owned kit item", "kit progression", metrics.kit_owned_item, operator.le, 0.3),
]


def _target(name: str):
    """("observable.KIT_PROGRESSION") → (data.observable, "KIT_PROGRESSION"); else catalogue_events."""
    module, _, attr = name.rpartition(".")
    return (observable if module == "observable" else events), attr


def generate(seed: int, null: dict | None) -> metrics.Fixtures:
    """Generate the fixtures for `seed` into a temporary dir, with `null`'s constants."""
    saved = {name: getattr(*_target(name)) for name in (null or {})}
    out = Path(tempfile.mkdtemp(prefix=f"planted-{seed}-"))
    try:
        for name, value in (null or {}).items():
            setattr(*_target(name), value)
        generator.RNG_SEED, generator.DATA_DIR = seed, out
        with contextlib.redirect_stdout(io.StringIO()):
            generator.main()
    finally:
        for name, value in saved.items():
            setattr(*_target(name), value)
    return metrics.Fixtures(out)


def main() -> int:
    rows = []   # (check, seed, planted, null, ratio, passed)
    for seed in SEEDS:
        planted = generate(seed, None)
        planted_values = {check: metric(planted) for check, _, metric, _, _ in CHECKS}
        shutil.rmtree(planted.dir)
        # One null at a time: each generation is ~120 MB on disk and more in memory.
        for null_name, patch in NULLS.items():
            null = generate(seed, patch)
            for check, which, metric, compare, margin in CHECKS:
                if which != null_name:
                    continue
                p, n = planted_values[check], metric(null)
                rows.append((check, seed, p, n, p / n, compare(p / n, margin)))
                print(f"seed {seed:>2}  {check:<36} planted {p:.3f}  null {n:.3f}  ratio {p / n:.3f}  "
                      f"{'pass' if rows[-1][-1] else 'FAIL'}", flush=True)
            shutil.rmtree(null.dir)

    # P1b's second half: budget's lift over its null, against premium's.
    for seed in SEEDS:
        budget = next(r[4] for r in rows if r[0].startswith("P1a") and r[1] == seed)
        premium = next(r[4] for r in rows if r[0].startswith("P1b") and r[1] == seed)
        rows.append(("P1b budget's lift ÷ premium's", seed, budget, premium, budget / premium, budget / premium >= 1.4))

    _write_report(rows)
    failed = [r for r in rows if not r[-1]]
    print(f"\n{len(rows) - len(failed)} of {len(rows)} pass. Report: {REPORT.relative_to(REPORT.parents[2])}")
    return 1 if failed else 0


def _write_report(rows) -> None:
    margins = {check: f"{'≥' if compare is operator.ge else '≤'} {margin}" for check, _, _, compare, margin in CHECKS}
    margins["P1b budget's lift ÷ premium's"] = "≥ 1.4"
    lines = [
        "# Planted effects against their nulls (ADR 0032)",
        "",
        "Generated by `./do planted-effects` (`scripts/planted_effects.py`). Each row compares",
        "a metric on the planted fixtures with the same seed's null generation (the effect",
        "switched off). Design and margins: `product-states-prereg.md`.",
        "",
        "| check | seed | planted | null | planted ÷ null | margin | result |",
        "|:--|--:|--:|--:|--:|:--|:--|",
    ]
    for check, seed, p, n, ratio, passed in rows:
        lines.append(f"| {check} | {seed} | {p:.3f} | {n:.3f} | {ratio:.3f} | {margins[check]} | "
                     f"{'pass' if passed else '**fail**'} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
