"""The metrics of ADR 0032's and ADR 0033's planted effects, read from one generated data dir.

Each returns one number; `scripts/planted_effects.py` compares it between a
planted generation and a null one (docs/verification/product-states-prereg.md,
amendment after the second generation). `Fixtures` is shared with the
metrics of ADRs 0038–0040 (`state_effect_metrics.py`,
`review_effect_metrics.py`, `acquisition_effect_metrics.py`).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from functools import cache
from pathlib import Path

from data.catalogue_events import LARGE_PACK_KG, add_months, pack_kg
from data.observable import kit_status
from data.review_chain import quality

WINDOW_START = "2024-05"


class Fixtures:
    """One generated data dir, each table read once."""

    def __init__(self, data_dir: Path):
        self.dir = data_dir

    @cache
    def load(self, table: str) -> list[dict]:
        return json.loads((self.dir / f"{table}.json").read_text(encoding="utf-8"))

    @cache
    def traits(self) -> dict[str, dict]:
        """The generator's hidden model per customer (its answer key; Aito never sees it)."""
        rows = json.loads((self.dir / "answer_key" / "customer_traits.json").read_text(encoding="utf-8"))
        return {t["customer_id"]: t for t in rows}

    @cache
    def impressions(self) -> list[dict]:
        """Customers' list impressions with their context, and the customer's
        hidden model from the generator's answer key (ADR 0033). A visitor who
        hasn't bought yet (ADR 0040) has no hidden model and never buys, and
        buy-again and checkout showings are bought by intent (ADR 0045): left out."""
        contexts = {c["context_id"]: c for c in self.load("contexts")}
        traits = self.traits()
        rows = []
        for imp in self.load("impressions"):
            ctx = contexts[imp["context"]]
            if "customer" not in ctx or imp["placement"] != "list":
                continue     # ADR 0045: the shop's lists; buy-again and checkout are intent
            t = traits[ctx["customer"]]
            rows.append({**imp, "month": ctx["month"], "basket_categories": ctx.get("basket_categories", ""),
                         "owned": ctx.get("owned", ""), "customer_id": ctx["customer"],
                         "customer_lifestyle": t["lifestyle"], "customer_brand_loyalty": t["brand_loyalty"],
                         **{f"{s}_sensitivity": t[f"{s}_sensitivity"]
                            for s in ("discount", "stars", "newness", "labels")}})
        return rows

    @cache
    def state(self) -> dict[str, dict]:
        return {st["product_state_id"]: st for st in self.load("product_states")}

    @cache
    def launches(self) -> dict[str, str]:
        first: dict[str, str] = {}
        for st in self.load("product_states"):
            first[st["product_sku"]] = min(first.get(st["product_sku"], st["month"]), st["month"])
        return {sku: m for sku, m in first.items() if m > WINDOW_START}

    @cache
    def rises(self) -> dict[str, str]:
        raised: dict[str, str] = {}
        for st in self.load("product_states"):
            if st["price_change"] == "rise":
                raised[st["product_sku"]] = min(raised.get(st["product_sku"], st["month"]), st["month"])
        return raised

    @cache
    def slice_of(self) -> dict[str, tuple[str, str]]:
        return {p["sku"]: (p["pet_type"], p["category"]) for p in self.load("products")}

    @cache
    def month_of_order(self) -> dict[str, str]:
        return {o["order_id"]: o["month"] for o in self.load("orders")}


def _rate(rows, outcome: str = "purchased") -> float:
    rows = list(rows)
    assert rows, "no impressions to rate"
    return sum(r[outcome] for r in rows) / len(rows)


def offer_ratio(fx: Fixtures, lifestyle: str) -> float:
    """P1: purchase rate on offer ÷ not, for one lifestyle."""
    state = fx.state()
    rows = [r for r in fx.impressions() if r["customer_lifestyle"] == lifestyle]
    on = _rate(r for r in rows if state[r["product_state"]]["on_offer"])
    return on / _rate(r for r in rows if not state[r["product_state"]]["on_offer"])


def launch_pull(fx: Fixtures) -> float:
    """P2b: launched products' slice share, first 3 months ÷ months 4–9, pooled."""
    slice_of, month_of = fx.slice_of(), fx.month_of_order()
    slice_lines, sku_lines = Counter(), Counter()
    for ln in fx.load("order_lines"):
        m = month_of[ln["order_id"]]
        slice_lines[(slice_of[ln["product_sku"]], m)] += 1
        sku_lines[(ln["product_sku"], m)] += 1

    def share(sku, months):
        total = sum(slice_lines[(slice_of[sku], m)] for m in months)
        return sum(sku_lines[(sku, m)] for m in months) / total if total else None

    new = established = 0.0
    for sku, launch in fx.launches().items():
        a = share(sku, [add_months(launch, i) for i in range(3)])
        b = share(sku, [add_months(launch, i) for i in range(3, 9)])
        if a is not None and b:
            new += a
            established += b
    return new / established


def incumbents_after_launch(fx: Fixtures) -> float:
    """P2c: units of a launch's incumbents, 3 months after ÷ 3 before, pooled."""
    slice_of, launches = fx.slice_of(), fx.launches()
    units = Counter()
    for ms in fx.load("monthly_sales"):
        if ms["product_sku"] not in launches:
            units[(slice_of[ms["product_sku"]], ms["month"])] += ms["units_sold"]
    after = before = 0
    for sku, m in launches.items():
        after += sum(units[(slice_of[sku], add_months(m, i))] for i in range(3))
        before += sum(units[(slice_of[sku], add_months(m, -i))] for i in range(1, 4))
    return after / before


def flexible_take_to_new(fx: Fixtures) -> float:
    """P2d: on launched products, (flexible ÷ loyal purchase rate) new ÷ established."""
    state, launches = fx.state(), fx.launches()

    def ratio(age):
        rows = [r for r in fx.impressions()
                if r["product_sku"] in launches and state[r["product_state"]]["age"] == age]
        flexible = _rate(r for r in rows if r["customer_brand_loyalty"] == "flexible")
        return flexible / _rate(r for r in rows if r["customer_brand_loyalty"] == "loyal")

    return ratio("new") / ratio("established")


def sales_after_rise(fx: Fixtures) -> float:
    """P3a: raised products' units 6 months after ÷ 6 before, over the same
    months' ratio for products neither raised nor launched."""
    raised, launches = fx.rises(), fx.launches()
    units = Counter()
    for ms in fx.load("monthly_sales"):
        units[(ms["product_sku"], ms["month"])] += ms["units_sold"]
    calm = {p["sku"] for p in fx.load("products")} - set(raised) - set(launches)
    calm_units = Counter()
    for (sku, m), u in units.items():
        if sku in calm:
            calm_units[m] += u
    mine_after = mine_before = calm_after = calm_before = 0
    for sku, m in raised.items():
        mine_after += sum(units[(sku, add_months(m, i))] for i in range(6))
        mine_before += sum(units[(sku, add_months(m, -i))] for i in range(1, 7))
        calm_after += sum(calm_units[add_months(m, i)] for i in range(6))
        calm_before += sum(calm_units[add_months(m, -i)] for i in range(1, 7))
    return (mine_after / mine_before) / (calm_after / calm_before)


def stars_sell(fx: Fixtures) -> float:
    """P4a: purchase rate at 5 stars ÷ at 3, products whose quality isn't poor."""
    state = fx.state()
    rows = [r for r in fx.impressions() if quality(r["product_sku"]) != "poor"]
    five = _rate(r for r in rows if state[r["product_state"]]["rating_band"] == "5")
    return five / _rate(r for r in rows if state[r["product_state"]]["rating_band"] == "3")


def big_bags_for_big_dogs(fx: Fixtures) -> float:
    """P5a: share of dog-food lines ≥ 7 kg, large-dog ÷ small-dog households."""
    pet_size = {cid: t.get("pet_size") for cid, t in fx.traits().items()}
    customer_of = {o["order_id"]: o["customer_id"] for o in fx.load("orders")}
    products = {p["sku"]: p for p in fx.load("products")}
    big = defaultdict(lambda: [0, 0])
    for ln in fx.load("order_lines"):
        p = products[ln["product_sku"]]
        if p["pet_type"] == "dog" and p["category"] in ("dry-food", "wet-food"):
            cell = big[pet_size[customer_of[ln["order_id"]]]]
            cell[0] += pack_kg(p["name"]) >= LARGE_PACK_KG
            cell[1] += 1
    return (big["large"][0] / big["large"][1]) / (big["small"][0] / big["small"][1])


def _kit_rows(fx: Fixtures) -> dict[str | None, list[dict]]:
    """Impressions by where the shown product stands in the household's kit."""
    products = {p["sku"]: p for p in fx.load("products")}
    by: dict[str | None, list[dict]] = defaultdict(list)
    for r in fx.impressions():
        status = kit_status(products[r["product_sku"]], set(r["basket_categories"].split()), set(r["owned"].split()))
        by[status].append(r)
    return by


def kit_next_item(fx: Fixtures) -> float:
    """K1a: purchase rate of the kit's next item ÷ other add-ons not yet owned."""
    by = _kit_rows(fx)
    return _rate(by["next"]) / _rate(by["other"])


def kit_owned_item(fx: Fixtures) -> float:
    """K1b: purchase rate of a kit item the household has ÷ kit items it doesn't."""
    by = _kit_rows(fx)
    return _rate(by["owned"]) / _rate(by["next"] + by["other"])


def clear_caches() -> None:
    """Forget every table read so far: one generation at a time stays in memory."""
    for value in vars(Fixtures).values():
        if hasattr(value, "cache_clear"):
            value.cache_clear()
