#!/usr/bin/env python3
"""Are the planted incidents (ADR 0056) in the data? Judged against a null generation.

    ./do planted-incidents

For seeds 42, 7 and 99 the fixtures are generated once with all four incidents on, and once per incident with that
incident alone off. The checks and their margins are those of ADR 0056 ("The checks"); each is judged on the three
seeds pooled, because one incident is a few dozen purchases. Nothing is written to `data/`; the report is written to
docs/verification/planted-incidents-data.md.
"""
from __future__ import annotations

import contextlib
import io
import operator
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

import data.generate_fixtures as generator
from data import incidents, planted_switches
from scripts import planted_effect_metrics as metrics

SEEDS = (42, 7, 99)
REPORT = Path(__file__).resolve().parent.parent / "docs/verification/planted-incidents-data.md"
INCIDENTS = ("E1", "E2", "E3", "E4")


def generate(seed: int, off: str | None) -> metrics.Fixtures:
    """The fixtures of `seed` in a temporary dir, every incident on except `off`."""
    out = Path(tempfile.mkdtemp(prefix=f"incidents-{seed}-"))
    for name in INCIDENTS:
        planted_switches.ON[name] = name != off
    try:
        generator.RNG_SEED, generator.DATA_DIR = seed, out
        with contextlib.redirect_stdout(io.StringIO()):
            generator.main()
    finally:
        for name in INCIDENTS:
            planted_switches.ON[name] = False
    return metrics.Fixtures(out)


def _planted(fx: metrics.Fixtures, incident_id: str) -> incidents.Incident:
    """The incident as the answer key wrote it (the recalled line is renamed in the fixtures, so the catalogue cannot find it again)."""
    import json
    rows = json.loads((fx.dir / "answer_key" / "incidents.json").read_text())
    row = next(r for r in rows if r["id"] == incident_id)
    return incidents.Incident(row["id"], row["kind"], frozenset(row["skus"]), tuple(row["months"]), row.get("withdrawn_from"))


def _lines(fx: metrics.Fixtures, skus, months: tuple[str, ...] | None = None, after: str | None = None) -> list[dict]:
    """The order lines of `skus` (kept lines only), with their customer and month."""
    order = {o["order_id"]: o for o in fx.load("orders")}
    rows = []
    for ln in fx.load("order_lines"):
        if ln["product_sku"] in skus and not ln.get("returned"):
            o = order[ln["order_id"]]
            if (months is None or o["month"] in months) and (after is None or o["month"] > after):
                rows.append({**ln, "customer_id": o["customer_id"], "month": o["month"]})
    return rows


def _experience(fx: metrics.Fixtures) -> dict[str, str]:
    import json
    rows = json.loads((fx.dir / "answer_key" / "line_experiences.json").read_text())
    return {r["line_id"]: r["experience"] for r in rows}


def _bad_share(fx, skus, months) -> tuple[int, int]:
    """(bad lines, all lines) of `skus` sold in `months`, returned lines included: a bad unit is returned, and still bought."""
    order = {o["order_id"]: o["month"] for o in fx.load("orders")}
    experience = _experience(fx)
    lines = [ln for ln in fx.load("order_lines") if ln["product_sku"] in skus and order[ln["order_id"]] in months]
    return sum(experience[ln["line_id"]] == "bad" for ln in lines), len(lines)


def _low_reviews(fx, skus, months) -> tuple[int, int]:
    rows = [r for r in fx.load("reviews") if r["product_sku"] in skus and r["created_at"] in months]
    return sum(r["rating"] <= 2 for r in rows), len(rows)


def _units(fx, skus, months=None, after=None) -> int:
    return sum(int(ln["qty"]) for ln in _lines(fx, skus, months, after))


def _grain_free_dog_dry_units(fx, months, excluding, exclude_customers=frozenset()) -> int:
    skus = {p["sku"] for p in fx.load("products") if p["pet_type"] == "dog" and p["category"] == "dry-food" and p.get("dietary") == "grain-free"}
    return sum(int(ln["qty"]) for ln in _lines(fx, skus - set(excluding), months) if ln["customer_id"] not in exclude_customers)


def _repeat_units(fx, skus, customers, months, after) -> int:
    """Units of `skus` bought by `customers` in the months after `after`."""
    return sum(int(ln["qty"]) for ln in _lines(fx, skus, None, after) if ln["customer_id"] in customers)


def _bad_customers(fx, incident_id: str) -> set[str]:
    import json
    key = json.loads((fx.dir / "answer_key" / "incidents.json").read_text())
    return set(next(r for r in key if r["id"] == incident_id)["customers_with_a_bad_unit"])


def _end_of_year_after(month: str) -> str:
    return incidents._add_months(month, incidents.SWITCH_MONTHS)


def _after_pull(months_after: int) -> tuple[str, ...]:
    return tuple(incidents._add_months("2025-11", i) for i in range(months_after))


def customers_of(fx: metrics.Fixtures, incident_id: str) -> tuple[set[str], set[str], set[str]]:
    """(customers with a bad unit, the other buyers in the incident months, everyone who ever bought the line) in a planted generation:
    the groups both generations are read on."""
    inc = _planted(fx, incident_id)
    hit = _bad_customers(fx, incident_id)
    return hit, {ln["customer_id"] for ln in _lines(fx, inc.skus, inc.months)} - hit, {ln["customer_id"] for ln in _lines(fx, inc.skus)}


def measure(fx: metrics.Fixtures, incident_id: str, groups: tuple[set[str], set[str], set[str]] | None = None) -> dict[str, float]:
    """The numbers one incident's checks read from one generation. `groups` are the planted generation's customers (the same ids in the null)."""
    inc = _planted(fx, incident_id)
    out: dict[str, float] = {}
    bad, total = _bad_share(fx, inc.skus, inc.months)
    out["bad"], out["lines"] = bad, total
    low, reviews = _low_reviews(fx, inc.skus, inc.months)
    out["low_reviews"], out["reviews"] = low, reviews
    if incident_id == "E1":
        out["batch_units"] = _units(fx, inc.skus, inc.months)
        out["units_after_pull"] = _units(fx, inc.skus, None, "2025-10")
        # Trust is read on customers who never bought the line: those who did switch to other grain-free food when it was pulled.
        bought_line = groups[2] if groups is not None else {ln["customer_id"] for ln in _lines(fx, inc.skus)}
        out["type_units_after_pull"] = _grain_free_dog_dry_units(fx, _after_pull(2), inc.skus, exclude_customers=bought_line)
        buyers = {ln["customer_id"] for ln in _lines(fx, inc.skus, inc.months)}
        churned = {c["customer_id"] for c in fx.load("customers") if c["churned"]}
        out["batch_buyers"], out["batch_buyers_churned"] = len(buyers), len(buyers & churned)
    else:
        hit, buyers, _ = groups if groups is not None else customers_of(fx, incident_id)
        last = inc.months[-1]
        out["bad_customers"] = len(hit)
        out["bad_customers_repeat_units"] = _repeat_units(fx, inc.skus, hit, None, last) if hit else 0
        out["other_buyers"] = len(buyers)
        out["other_buyers_repeat_units"] = _repeat_units(fx, inc.skus, buyers, None, last)
    return out


# (id, incident, what it asserts, value from the pooled planted and null sums, comparison, margin)
def _ratio(num: str, den: str):
    return lambda s: (s[num] / s[den]) if s[den] else float("nan")


def judge(incident_id: str, planted: dict, null: dict) -> list[tuple[str, str, float, bool]]:
    rows = []

    def add(check, text, value, op, margin):
        rows.append((check, text, value, bool(op(value, margin))))

    safe = lambda a, b: a / b if b else float("inf")
    add(f"{incident_id}-bad", "bad-unit share of the line in the incident months, planted ÷ null",
        safe(planted["bad"] / max(planted["lines"], 1), null["bad"] / max(null["lines"], 1)), operator.ge, 3.0)
    add(f"{incident_id}-reviews", "share of 1–2 star reviews of the line in the incident months, planted − null (points)",
        100 * (planted["low_reviews"] / max(planted["reviews"], 1) - null["low_reviews"] / max(null["reviews"], 1)), operator.ge, 20.0)
    if incident_id == "E1":
        add("E1-hit", "units of the line in the batch months, planted ÷ null (a house-label hit)", safe(planted["batch_units"], null["batch_units"]), operator.ge, 2.0)
        add("E1-pulled", "units of the line after the pull, planted", planted["units_after_pull"], operator.eq, 0)
        add("E1-null-sells", "units of the line after the pull, null (it would have sold)", null["units_after_pull"], operator.gt, 0)
        add("E1-trust", "other grain-free dog dry food bought by customers who never bought the line, two months after the pull, planted ÷ null",
            safe(planted["type_units_after_pull"], null["type_units_after_pull"]), operator.le, 0.95)
        add("E1-churn", "churn of the batch's buyers, planted ÷ null",
            safe(planted["batch_buyers_churned"] / max(planted["batch_buyers"], 1), null["batch_buyers_churned"] / max(null["batch_buyers"], 1)), operator.ge, 1.3)
    else:
        add(f"{incident_id}-switch", "the bad-unit customers' repeat units of the line, planted ÷ null (same customers' number of units per customer)",
            safe(planted["bad_customers_repeat_units"] / max(planted["bad_customers"], 1), null["bad_customers_repeat_units"] / max(null["bad_customers"], 1)), operator.le, 1 / 3)
        add(f"{incident_id}-others", "the other buyers' repeat units per customer, planted ÷ null",
            safe(planted["other_buyers_repeat_units"] / max(planted["other_buyers"], 1), null["other_buyers_repeat_units"] / max(null["other_buyers"], 1)), lambda v, m: abs(v - 1) <= m, 0.10)
    return rows


def main() -> int:
    pooled_planted: dict[str, Counter] = {i: Counter() for i in INCIDENTS}
    pooled_null: dict[str, Counter] = {i: Counter() for i in INCIDENTS}
    for seed in SEEDS:
        fx = generate(seed, None)
        groups = {incident: customers_of(fx, incident) for incident in INCIDENTS}
        for incident in INCIDENTS:
            pooled_planted[incident].update(measure(fx, incident, groups[incident]))
        shutil.rmtree(fx.dir)
        metrics.clear_caches()
        for incident in INCIDENTS:
            fx = generate(seed, incident)
            pooled_null[incident].update(measure(fx, incident, groups[incident]))
            shutil.rmtree(fx.dir)
            metrics.clear_caches()
        print(f"seed {seed} done", file=sys.stderr)
    lines = ["# Planted incidents: the data against its nulls (ADR 0056)", "",
             "Seeds 42, 7 and 99, pooled. Each null switches one incident off. Margins are the ADR's.", "",
             "| Check | What | Value | Margin met |", "|---|---|---|---|"]
    failed = 0
    for incident in INCIDENTS:
        for check, text, value, passed in judge(incident, dict(pooled_planted[incident]), dict(pooled_null[incident])):
            lines.append(f"| {check} | {text} | {value:.3f} | {'yes' if passed else '**no**'} |")
            failed += not passed
    REPORT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
