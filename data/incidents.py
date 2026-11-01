"""Planted incidents (ADR 0056): one loud batch recall and three quiet quality problems.

Everything here is fiction: the lines are picked from the catalogue by name, and the loud one is renamed to the house
label when the fixtures are written, so no real retailer, brand or news story is in the data. Each incident has a switch
(`planted_switches.ON["E1"]` to `"E4"`) and draws from RNG streams of its own, so a null generation with one switched off
changes only what that incident touches.

  E1  loud     a batch of a grain-free fish dry dog food made dogs ill; pulled after the news, trust in the type dips
  E2  quiet    bad units of a cat wet-food line in one month: complaints and refunds, no recall, no all-clear
  E3  quiet    the same for a dog treat line
  E4  quiet    the same for a small-animal dry food line

An incident is a *line* of products (several SKUs), because a single SKU sells a handful of units a month in this shop:
too few for a batch to leave a mark that a check could tell from noise.
"""

from __future__ import annotations

from dataclasses import dataclass

from data.planted_switches import ON, stream

BAD_P = {"recall": 0.35, "quality": 0.30}   # a purchase of the line in an incident month goes badly
SWITCH_ODDS = 0.05          # a customer who had a bad unit buys that line at these odds ...
SWITCH_MONTHS = 12          # ... for this many months after, whatever its quality is by then
TRUST_ODDS = 0.90           # after the pull, the odds to buy any other grain-free dog dry food ...
TRUST_RECOVERY_MONTHS = 8   # ... recover linearly to 1.0 over this many months
BATCH_BUYER_ODDS = 0.5      # the customers who bought the batch buy that type at these odds for the same time
LINE_PICK_FACTOR = 4.0      # the house-label fish line is a hit from this month: it sells enough for its failure to matter
LINE_HIT_FROM = "2025-01"

HOUSE_LABEL = "PetNord"
EXPECTED_MIN_SKUS = 3


@dataclass(frozen=True)
class Incident:
    id: str
    kind: str                       # "recall" | "quality"
    skus: frozenset[str]
    months: tuple[str, ...]         # the months whose purchases of the line may go badly
    withdrawn_from: str | None      # recall: the first month the line is no longer on sale


def plan(products: list) -> tuple[Incident, ...]:
    """The four incidents, their lines found in the catalogue by name. Fails loudly if a line is too thin to leave a mark."""
    def line(pet: str, category: str, brand: str | None, words: tuple[str, ...], dietary: str | None = None) -> frozenset[str]:
        found = frozenset(p.sku for p in products if p.pet_type == pet and p.category == category
                          and (brand is None or p.brand == brand) and all(w in p.name for w in words)
                          and (dietary is None or p.dietary == dietary))
        assert len(found) >= EXPECTED_MIN_SKUS, f"incident line {pet}/{category}/{brand}/{words} has {len(found)} SKUs, need {EXPECTED_MIN_SKUS}"
        return found

    return (
        Incident("E1", "recall", line("dog", "dry-food", None, ("Salmon",), "grain-free"), ("2025-09", "2025-10"), "2025-11"),
        Incident("E2", "quality", line("cat", "wet-food", "Sheba", ("Beef",)), ("2025-02",), None),
        Incident("E3", "quality", line("dog", "treats", HOUSE_LABEL, ("Liver Treats",)), ("2025-06",), None),
        Incident("E4", "quality", line("small_animal", "dry-food", HOUSE_LABEL, ("Hamster Mix Food",)), ("2026-01",), None),
    )


def active(incidents: tuple[Incident, ...]) -> tuple[Incident, ...]:
    return tuple(i for i in incidents if ON[i.id])


def withdrawn(incidents: tuple[Incident, ...], sku: str, month: str) -> bool:
    return any(i.withdrawn_from is not None and sku in i.skus and month >= i.withdrawn_from for i in active(incidents))


def pick_factor(incidents: tuple[Incident, ...], sku: str, month: str) -> float:
    """The house-label fish line sells well before it fails (E1)."""
    return LINE_PICK_FACTOR if any(i.id == "E1" and sku in i.skus and month >= LINE_HIT_FROM for i in active(incidents)) else 1.0


def experience(incidents: tuple[Incident, ...], seed: int, drawn: str, line_id: str, sku: str, month: str, customer_id: str,
               hits: dict[tuple[str, str], str]) -> str:
    """The experience of a line: `drawn` unless the line is in an incident month and the incident's own stream says it went badly.
    A bad unit is noted in `hits` as (customer, incident) -> month: that customer is the one who switches (E2-E4) or who bought the batch (E1)."""
    for incident in active(incidents):
        if sku in incident.skus and month in incident.months:
            if stream(seed, "incident", incident.id, line_id).random() < BAD_P[incident.kind]:
                hits.setdefault((customer_id, incident.id), month)
                return "bad"
    return drawn


def purchase_odds(incidents: tuple[Incident, ...], hits: dict[tuple[str, str], str], customer_id: str, product, month: str) -> float:
    """What the incidents do to the odds that this customer buys this product this month."""
    odds = 1.0
    for incident in active(incidents):
        hit = hits.get((customer_id, incident.id))
        if incident.kind == "quality" and hit and product.sku in incident.skus and hit < month <= _add_months(hit, SWITCH_MONTHS):
            odds *= SWITCH_ODDS
        if incident.kind == "recall" and incident.withdrawn_from and product.sku not in incident.skus and _grain_free_dog_dry(product):
            since = _months_between(incident.withdrawn_from, month)
            if 0 <= since < TRUST_RECOVERY_MONTHS:
                odds *= TRUST_ODDS + (1 - TRUST_ODDS) * since / TRUST_RECOVERY_MONTHS
                if hit:
                    odds *= BATCH_BUYER_ODDS + (1 - BATCH_BUYER_ODDS) * since / TRUST_RECOVERY_MONTHS
    return odds


def _grain_free_dog_dry(product) -> bool:
    return product.pet_type == "dog" and product.category == "dry-food" and product.dietary == "grain-free"


def _add_months(yyyymm: str, n: int) -> str:
    year, month = (int(x) for x in yyyymm.split("-"))
    year, month = divmod(year * 12 + month - 1 + n, 12)
    return f"{year:04d}-{month + 1:02d}"


def _months_between(first: str, last: str) -> int:
    (fy, fm), (ly, lm) = ((int(x) for x in m.split("-")) for m in (first, last))
    return (ly - fy) * 12 + lm - fm


def rename_for_output(products: list, incidents: tuple[Incident, ...]) -> None:
    """The recalled line carries the house label in the written fixtures (not in the draws, where its catalogue brand set its price)."""
    if not ON["E1"]:
        return
    recalled = next(i for i in incidents if i.id == "E1")
    for p in products:
        if p.sku in recalled.skus:
            p.name = f"{HOUSE_LABEL} Grain Free Fish Adult Dog Food {p.name.rsplit(' ', 1)[-1]}"
            p.brand = HOUSE_LABEL


def answer_key_rows(incidents: tuple[Incident, ...], hits: dict[tuple[str, str], str]) -> list[dict]:
    """What was planted, for the tests: every incident with its line and months, whether it is on in this generation, and the
    customers who had a bad unit from it."""
    return [{"id": i.id, "kind": i.kind, "planted": ON[i.id], "skus": sorted(i.skus), "months": list(i.months),
             "withdrawn_from": i.withdrawn_from,
             "customers_with_a_bad_unit": sorted(c for (c, inc), _ in hits.items() if inc == i.id)} for i in incidents]
