#!/usr/bin/env python3
"""Is each planted effect in the data? Judged against a null generation.

    ./do planted-effects

For seeds 42, 7 and 99, the fixtures are generated once as planted and once
per null: the same seed with one effect switched off. A check passes when its
value clears its margin on every seed (or, for a pooled check, over the three
seeds together). Time trends, selection and every other confound appear in
both generations, and each effect draws from its own RNG, so a null changes
only what its effect touches.

Design, metrics and margins: docs/verification/actionable-states-prereg.md
(ADRs 0038–0040), product-states-prereg.md and observable-data-prereg.md for
the older checks. Writes docs/verification/actionable-states-data.md.
Nothing is written to `data/`: each generation goes to a temporary dir.
"""
from __future__ import annotations

import contextlib
import io
import multiprocessing
import operator
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import data.generate_fixtures as generator
from data import acquisition, catalogue_events as events, observable, planted_switches
from scripts import acquisition_effect_metrics as acq
from scripts import person_effect_metrics as person
from scripts import planted_effect_metrics as metrics
from scripts import review_effect_metrics as rev
from scripts import sales_effect_metrics as sales
from scripts import state_effect_metrics as st

SEEDS = (42, 7, 99)
REPORT = Path(__file__).resolve().parent.parent / "docs/verification/actionable-states-data.md"

# Each null switches one planted effect off. A name in `planted_switches.ON`
# turns that switch off; the older effects set their constants to "no effect".
SWITCHED = {name: (name,) for name in ("P6", "P7", "P8", "P9", "P10", "quality", "R3", "R4", "R4_reply", "A6", "A7",
                                        "R5", "R6", "F1", "F2", "F3", "F4", "F5", "C1", "placement")}
# ADR 0045's O2: both effects of an offer, per showing and by placement.
SWITCHED["offers"] = ("P6", "placement")
CONSTANTS = {
    "launch pull": {"LAUNCH_PICK_FACTOR": 1.0, "RIVAL_PICK_FACTOR": 1.0, "RECONSIDER_AFTER_RIVAL": 1.0,
                    "SWITCH_TO_RIVAL": False},
    "price rise": {"RISE_RANGE": (1.0, 1.0)},
    "pack size": {"PACK_FIT": 1.0},
    "kit progression": {"observable.KIT_PROGRESSION": False},
}
NULLS = tuple(SWITCHED) + tuple(CONSTANTS)

# Every number a check reads, by name. Each is computed once per generation.
LEVEL_METRICS = {"P6": st.offer_contrast, "P7": st.stars_contrast, "P8": st.newness_contrast,
                 "P9": st.random_label_contrast, "P9p": st.popular_label_contrast}
METRICS = {
    **{f"{effect} {level}": (lambda fx, f=f, level=level: f(fx, level))
       for effect, f in LEVEL_METRICS.items() for level in ("high", "low")},
    "P10": st.low_stock_purchase_given_cart,
    "V1": st.offer_share_tracks_discount_sensitivity,
    "offer budget": lambda fx: metrics.offer_ratio(fx, "budget"),
    "offer premium": lambda fx: metrics.offer_ratio(fx, "premium"),
    "P4a": metrics.stars_sell,
    "R1": lambda fx: rev.stars_contrast(fx, "clicked"),
    "R2a": lambda fx: rev.stars_contrast(fx, "purchased"),
    "R2b": rev.poor_quality_contrast,
    "R3a": rev.nps_after_bad,
    "R3b non-reviewers": rev.nps_after_bad_without_review,
    "R3b gap": lambda fx: abs(rev.nps_reviewer_gap(fx)),
    "R3c": rev.nps_reply_gap,
    "R4a": rev.churn_after_bad,
    "R4b counts": rev.churn_after_replied_counts,
    "R4b": lambda fx: (lambda churned, writers: churned / writers)(*rev.churn_after_replied_counts(fx)),
    "R4c": rev.never_ordered_again_after_bad,
    "A6": rev.churn_after_incident,
    "A7": rev.churn_after_return,
    "A7b": rev.returned_after_bad,
    "R5": rev.demand_by_stars,
    "R6": rev.offer_response_by_stars,
    "F1a": lambda fx: acq.landing_share(fx, ("organic_search",), "product"),
    "F1b": acq.social_toys_and_treats,
    "F1c": lambda fx: acq.landing_share(fx, ("email", "affiliate"), "offer"),
    **{f"conversion {s}": (lambda fx, s=s: acq.conversion(fx, s)) for s in acquisition.SOURCES},
    "F2b": lambda fx: max(abs(acq.conversion(fx, s) / acquisition.CONVERSION[s] - 1) for s in acquisition.SOURCES),
    "F3a": lambda fx: acq.sensitivity_by_source(fx, "discount", "affiliate"),
    "F3b": lambda fx: acq.sensitivity_by_source(fx, "newness", "social"),
    "F3c": lambda fx: acq.offer_share_of_purchases(fx, "affiliate"),
    **{f"regular {s}": (lambda fx, s=s: acq.regular_rate(fx, source=s)) for s in acquisition.SOURCES},
    "regular staple": lambda fx: acq.regular_rate(fx, staple_first=True),
    "regular no staple": lambda fx: acq.regular_rate(fx, staple_first=False),
    **{f"regular {s} {staple}": (lambda fx, s=s, staple=staple: acq.regular_rate(
        fx, source=s, staple_first=staple == "staple"))
       for s in ("organic_search", "affiliate") for staple in ("staple", "no staple")},
    "O2": sales.units_at_deep_offers,
    "O3a": sales.showings_on_offer,
    "O3b": sales.click_rate_rises_by_position,
    "C1": person.natural_food_grain_free,
    "C2 rate": person.consent_rate_off,
    "C2 gap": person.consent_largest_gap,
    "C3": person.sex_largest_log_ratio,
    "P2b": metrics.launch_pull,
    "P2c": metrics.incumbents_after_launch,
    "P3a": metrics.sales_after_rise,
    "P5a": metrics.big_bags_for_big_dogs,
    "K1a": metrics.kit_next_item,
    "K1b": metrics.kit_owned_item,
}


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    null: str | None            # None: read on the planted generation alone
    form: str                   # ratio | high ÷ low | difference | planted | pooled
    metrics: tuple[str, ...]
    compare: object = None      # operator.ge or operator.le; None: reported, not judged
    margin: float | None = None

    def value(self, planted: dict, null: dict) -> float:
        p = [planted[m] for m in self.metrics]
        n = [null[m] for m in self.metrics] if self.null else []
        if self.form == "ratio":
            return p[0] / n[0]
        if self.form == "high ÷ low":
            return (p[0] / n[0]) / (p[1] / n[1])
        if self.form == "difference":
            return p[0] - n[0]
        assert self.form == "planted", self.form
        return p[0]

    def passes(self, value: float) -> bool | None:
        return None if self.compare is None else self.compare(value, self.margin)


GE, LE = operator.ge, operator.le


def _sensitivity_checks(effect: str, title: str) -> list[Check]:
    return [Check(effect, f"{title}: high ÷ low", effect, "high ÷ low", (f"{effect} high", f"{effect} low"), GE, 1.5),
            Check(f"{effect} high", f"{title}: high shoppers", effect, "ratio", (f"{effect} high",), GE, 1.3)]


CHECKS = [
    *_sensitivity_checks("P6", "an offer, by discount sensitivity"),
    *_sensitivity_checks("P7", "stars, by stars sensitivity"),
    *_sensitivity_checks("P8", "new, by newness sensitivity"),
    *_sensitivity_checks("P9", "a random label, by label sensitivity"),
    Check("P9p", "popular, by label sensitivity: high ÷ low", "P9", "high ÷ low", ("P9p high", "P9p low")),
    Check("P10", "low stock: purchase given cart", "P10", "ratio", ("P10",), GE, 1.03),
    Check("V1", "offer_share follows discount sensitivity", "P6", "ratio", ("V1",), GE, 1.2),
    Check("P1a", "budget shoppers buy on offer", "P6", "ratio", ("offer budget",), GE, 1.5),
    Check("P1b", "budget's offer lift ÷ premium's", "P6", "high ÷ low", ("offer budget", "offer premium"), GE, 1.05),
    Check("P4a", "stars sell (5 ÷ 3, not poor)", "P7", "ratio", ("P4a",), GE, 1.15),
    Check("R1", "stars move clicks (5 ÷ 1–2)", "P7", "ratio", ("R1",), GE, 1.4),
    Check("R2a", "stars move purchases (5 ÷ 1–2)", "P7", "ratio", ("R2a",), GE, 1.8),
    Check("R2b", "a poor product converts less", "quality", "ratio", ("R2b",), LE, 0.8),
    Check("R3a", "NPS after a bad experience, planted − null", "R3", "difference", ("R3a",), LE, -2.5),
    Check("R3b", "NPS after a bad experience, non-reviewers", None, "planted", ("R3b non-reviewers",), LE, 5.5),
    Check("R3b gap", "\\|unreplied reviewers − non-reviewers\\|, after a bad experience", None, "planted",
          ("R3b gap",), LE, 0.5),
    Check("R3c", "NPS: replied − unreplied negative-review writers", None, "planted", ("R3c",), GE, 1.2),
    Check("R4a", "churn in 3 months after a bad experience", "R4", "ratio", ("R4a",), GE, 1.4),
    Check("R4b seed", "churn in 3 months after a replied negative review (per seed)", "R4_reply", "ratio",
          ("R4b",)),
    Check("R4c", "never orders again after a bad experience", "R4", "ratio", ("R4c",)),
    # Data release 3b: the experience flags a shop reads as churn tells.
    Check("A6", "churn in 3 months after a late or damaged delivery", "A6", "ratio", ("A6",), GE, 1.8),
    Check("A7a", "churn in 3 months after an order with a returned line", "A7", "ratio", ("A7",), GE, 1.5),
    Check("A7b", "a badly-experienced line is returned, planted ÷ null", "A7", "ratio", ("A7b",), GE, 1.8),
    Check("R5", "stars move demand (5 ÷ 1–2)", "R5", "ratio", ("R5",), GE, 1.4),
    # Reported since ADR 0045: offers act through P6, not ε (actionable-states-prereg.md).
    Check("R6", "offer response at 1–2 stars ÷ at 5", "R6", "ratio", ("R6",)),
    Check("O2", "units at a 20 %+ offer", "offers", "ratio", ("O2",), GE, 1.8),
    Check("O3a", "showings of an offered product", "placement", "ratio", ("O3a",), GE, 1.2),
    Check("O3b", "list slots 1–9 clicked as often as the slot above", None, "planted", ("O3b",), LE, 0.0),
    Check("F1a", "organic search lands on product pages", "F1", "ratio", ("F1a",), GE, 1.6),
    Check("F1b", "social lands on toys and treats", "F1", "ratio", ("F1b",), GE, 1.8),
    Check("F1c", "email and affiliate land on offers", "F1", "ratio", ("F1c",), GE, 2.0),
    Check("F2a", "conversion, email ÷ social", "F2", "high ÷ low", ("conversion email", "conversion social"),
          GE, 3.0),
    Check("F2b", "the worst source's conversion off its rate (share)", None, "planted", ("F2b",), LE, 0.2),
    Check("F3a", "affiliates bring discount-high shoppers", "F3", "ratio", ("F3a",), GE, 1.8),
    Check("F3b", "social brings newness-high shoppers", "F3", "ratio", ("F3b",), GE, 1.5),
    Check("F3c", "affiliates' purchases on offer ÷ others'", "F3", "ratio", ("F3c",)),
    Check("F4a", "becomes regular: organic ÷ affiliate", "F4", "high ÷ low",
          ("regular organic_search", "regular affiliate"), GE, 1.6),
    Check("F4b", "becomes regular: social ÷ organic", "F4", "high ÷ low",
          ("regular social", "regular organic_search"), LE, 0.7),
    Check("F5a", "becomes regular: staple in the first basket ÷ not", "F5", "high ÷ low",
          ("regular staple", "regular no staple"), GE, 1.5),
    Check("F5b organic", "F5a among organic-search customers", "F5", "high ÷ low",
          ("regular organic_search staple", "regular organic_search no staple")),
    Check("F5b affiliate", "F5a among affiliate customers", "F5", "high ÷ low",
          ("regular affiliate staple", "regular affiliate no staple")),
    Check("C1", "natural-food declarers buy grain-free (÷ everyone else)", None, "planted", ("C1",), GE, 1.8),
    Check("C1 vs null", "C1 against interests drawn without the traits", "C1", "ratio", ("C1",)),
    Check("C2 rate", "consent rate's distance from 0.6", None, "planted", ("C2 rate",), LE, 0.05),
    Check("C2 gap", "largest consent gap between a trait level and the rest", None, "planted", ("C2 gap",),
          LE, 0.07),
    Check("C3", "largest \\|log\\| female ÷ male category share (log 1.25 = 0.223)", None, "planted", ("C3",),
          LE, 0.223),
    Check("P2b", "a new product's pull", "launch pull", "ratio", ("P2b",), GE, 1.3),
    Check("P2c", "incumbents lose to a launch", "launch pull", "ratio", ("P2c",), LE, 0.95),
    Check("P3a", "a price rise lowers sales", "price rise", "ratio", ("P3a",), LE, 0.92),
    Check("P5a", "big bags for big dogs", "pack size", "ratio", ("P5a",), GE, 1.8),
    Check("K1a", "the kit's next item", "kit progression", "ratio", ("K1a",), GE, 2.0),
    Check("K1b", "an owned kit item", "kit progression", "ratio", ("K1b",), LE, 0.3),
]
POOLED = Check("R4b", "churn in 3 months after a replied negative review, pooled", "R4_reply", "pooled",
               ("R4b counts",), LE, 0.9)


def _target(name: str):
    """"observable.KIT_PROGRESSION" → (data.observable, "KIT_PROGRESSION"); else catalogue_events."""
    module, _, attr = name.rpartition(".")
    return (observable if module == "observable" else events), attr


def generate(seed: int, null: str | None) -> metrics.Fixtures:
    """Generate the fixtures for `seed` into a temporary dir, with `null`'s effect off."""
    patch = CONSTANTS.get(null, {})
    saved = {name: getattr(*_target(name)) for name in patch}
    out = Path(tempfile.mkdtemp(prefix=f"planted-{seed}-"))
    try:
        for name, value in patch.items():
            setattr(*_target(name), value)
        for switch in SWITCHED.get(null, ()):
            planted_switches.ON[switch] = False
        generator.RNG_SEED, generator.DATA_DIR = seed, out
        with contextlib.redirect_stdout(io.StringIO()):
            generator.main()
    finally:
        for name, value in saved.items():
            setattr(*_target(name), value)
        for switch in SWITCHED.get(null, ()):
            planted_switches.ON[switch] = True
    return metrics.Fixtures(out)


def _measure(fx: metrics.Fixtures, names: set[str]) -> dict:
    """The named metrics of one generation; then its tables leave memory and disk."""
    values = {name: METRICS[name](fx) for name in sorted(names)}
    metrics.clear_caches()
    rev.clear_caches()
    shutil.rmtree(fx.dir)
    return values


def judge_seed(seed: int) -> tuple[list[tuple], dict]:
    """Rows of (check id, seed, value, passed), and R4b's counts, planted and null."""
    planted = _measure(generate(seed, None), {m for c in CHECKS + [POOLED] for m in c.metrics})
    rows, pooled = [], {}
    for check in (c for c in CHECKS if c.null is None):
        value = check.value(planted, {})
        rows.append((check.id, seed, value, check.passes(value)))
    for null_name in NULLS:
        mine = [c for c in CHECKS + [POOLED] if c.null == null_name]
        null = _measure(generate(seed, null_name), {m for c in mine for m in c.metrics})
        for check in mine:
            if check is POOLED:
                pooled = {"planted": planted["R4b counts"], "null": null["R4b counts"]}
                continue
            value = check.value(planted, null)
            rows.append((check.id, seed, value, check.passes(value)))
            print(f"seed {seed:>2}  {check.id:<14} {value:8.3f}  "
                  f"{'reported' if check.compare is None else 'pass' if rows[-1][-1] else 'FAIL'}", flush=True)
    return rows, pooled


def main() -> int:
    # One process per seed: each generation patches module-level switches.
    with multiprocessing.get_context("fork").Pool(len(SEEDS)) as pool:
        results = pool.map(judge_seed, SEEDS)
    rows = [row for seed_rows, _ in results for row in seed_rows]
    (planted_churned, planted_writers), (null_churned, null_writers) = [
        tuple(map(sum, zip(*(counts[side] for _, counts in results)))) for side in ("planted", "null")]
    value = (planted_churned / planted_writers) / (null_churned / null_writers)
    pooled_row = (value, POOLED.passes(value),
                  f"{planted_churned}/{planted_writers} planted, {null_churned}/{null_writers} null")
    _write_report(rows, pooled_row)
    judged = [r[3] for r in rows if r[3] is not None] + [pooled_row[1]]
    print(f"\n{sum(judged)} of {len(judged)} pass. Report: {REPORT.relative_to(REPORT.parents[2])}")
    return 0 if all(judged) else 1


def _margin(check: Check) -> str:
    if check.compare is None:
        return "reported"
    return f"{'≥' if check.compare is GE else '≤'} {check.margin}"


def _write_report(rows: list[tuple], pooled_row: tuple) -> None:
    by_id = {c.id: c for c in CHECKS}
    order = {c.id: i for i, c in enumerate(CHECKS)}
    lines = [
        "# Planted effects against their nulls (ADRs 0032, 0033, 0038–0040)",
        "",
        "Generated by `./do planted-effects` (`scripts/planted_effects.py`). Each row is a",
        "check on one seed: a planted generation compared with the same seed's null (the",
        "effect switched off), or the planted generation alone where the null is `—`.",
        "Design and margins: `actionable-states-prereg.md`.",
        "",
        "| check | what | null | form | seed | value | margin | result |",
        "|:--|:--|:--|:--|--:|--:|:--|:--|",
    ]
    for check_id, seed, value, passed in sorted(rows, key=lambda r: (order[r[0]], SEEDS.index(r[1]))):
        c = by_id[check_id]
        result = "reported" if passed is None else "pass" if passed else "**fail**"
        lines.append(f"| {c.id} | {c.title} | {c.null or '—'} | {c.form} | {seed} | {value:.3f} | "
                     f"{_margin(c)} | {result} |")
    value, passed, counts = pooled_row
    lines.append(f"| {POOLED.id} | {POOLED.title} ({counts}) | {POOLED.null} | {POOLED.form} | 42, 7, 99 | "
                 f"{value:.3f} | {_margin(POOLED)} | {'pass' if passed else '**fail**'} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
