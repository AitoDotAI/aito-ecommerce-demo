"""`experiments`, `experiment_variants` and `experiment_showings`: a shop's A/B tests on how a product is shown (ADR 0064).

Twelve experiments, one per product, of three kinds with two arms each: an offer (list price or 15 % off), a title (the product name or one that leads
with a benefit) and an image (pack shot or lifestyle). Ten run (eight undecided, two decided after two months and then shown at 90 % to the winner, 10 %
still drawn at random), two are drafts with no showings. Showings are separate from the order data: a purchase here is not an order line (ADR 0064).

The planted reactions, hidden in the answer key and found by the tests (`data/answer_key/experiment_chances.json` holds every shopper's true chance of a
purchase on each arm):

  X1  an offer lifts the chance ×2.6 for a shopper with high discount sensitivity (ADR 0038), ×1.4 for mid, ×1.05 for low
  X2  a benefit-led title lifts it ×1.5 for a high health focus, ×1.15 for medium, and lowers it to ×0.95 for low
  X3  a lifestyle image lifts it ×1.4 for a shopper with high newness sensitivity, ×1.15 for mid, ×1.0 for low

The shop sees none of that. What it can observe goes on each showing as `signal`: the share of the shopper's lines bought on offer (offer), the
share of wellness diets among what they bought (title), the source of their first visit (image).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from data.planted_switches import stream

KINDS = ("offer", "title", "image")
ARMS = {"offer": ("list", "offer"), "title": ("plain", "benefit"), "image": ("packshot", "lifestyle")}
OFFER_SHARE = 0.85                         # the offer arm's price, as a share of the list price
LIFT = {"offer": {"high": 2.6, "mid": 1.4, "low": 1.05}, "title": {"high": 1.5, "medium": 1.15, "low": 0.95},
        "image": {"high": 1.4, "mid": 1.15, "low": 1.0}}
MONTHS = 4                                 # the last four months of the data; the evidence holds the last out
EXPERIMENTS = 12
DRAFTS = 2                                 # the last two have no showings yet
DECIDED = {"offer": 1, "title": 1}         # how many of each kind are decided after two months (the first of the kind in rank order)
DECIDED_AFTER = 2                          # months of 50/50 before a decision
SERVE_WINNER = 0.9                         # after a decision the winner is shown at 90 %, the rest still at random
SHOWINGS_PER_MONTH = 2
BASE_CHANCE = (0.03, 0.09)                 # a product's chance of a purchase on a showing before the arm's lift
BENEFIT = {"dry-food": "complete daily nutrition", "wet-food": "real meat, no fillers", "treats": "a reward that is good for them",
           "toys": "built to last", "litter": "low dust, fast clumping", "health": "vet-recommended care",
           "grooming": "gentle on skin and coat", "accessories": "made for everyday comfort"}
SIGNAL_OF = {"offer": "offer_buyer", "title": "wellness_share", "image": "first_source"}


@dataclass(frozen=True)
class Plan:
    """An experiment before any showing: its product, kind and state."""
    experiment_id: str
    sku: str
    kind: str
    status: str                             # draft | running | decided
    decided_month: str | None


def plan_experiments(products: list[dict], units_sold: dict[str, int], months: list[str]) -> list[Plan]:
    """The twelve best-selling products, one experiment each, kinds in turn, in rank order; the last `DRAFTS` are drafts."""
    ranked = sorted((p for p in products if units_sold.get(p["sku"], 0) > 0), key=lambda p: (-units_sold[p["sku"]], p["sku"]))[:EXPERIMENTS]
    plans, decided = [], defaultdict(int)
    for rank, product in enumerate(ranked):
        kind = KINDS[rank % len(KINDS)]
        if rank >= EXPERIMENTS - DRAFTS:
            status, month = "draft", None
        elif decided[kind] < DECIDED.get(kind, 0):
            decided[kind] += 1
            status, month = "decided", months[DECIDED_AFTER - 1]
        else:
            status, month = "running", None
        plans.append(Plan(f"EXP-{rank + 1:02d}", product["sku"], kind, status, month))
    return plans


def wellness_shares(lines: list[dict], orders: list[dict], dietary: dict[str, str | None], wellness: set[str]) -> dict[str, str]:
    """Per customer, the share of their kept lines that are a wellness diet, as a band: none | some | most. A customer with no lines is not here."""
    owner = {o["order_id"]: o["customer_id"] for o in orders}
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for line in lines:
        if not line["returned"]:
            counts[owner[line["order_id"]]][0] += dietary.get(line["product_sku"]) in wellness
            counts[owner[line["order_id"]]][1] += 1
    return {c: "none" if w == 0 else "some" if w / n < 0.5 else "most" for c, (w, n) in counts.items()}


def signal_of(kind: str, customer: dict, offer_buyer: dict[str, str], wellness_band: dict[str, str]) -> str:
    """What the shop can see about this customer for this kind of experiment; `unknown` when they have not ordered."""
    if kind == "offer":
        return offer_buyer.get(customer["customer_id"], "unknown")
    if kind == "title":
        return wellness_band.get(customer["customer_id"], "unknown")
    return customer["first_source"]


def true_chance(kind: str, arm: str, base: float, hidden: dict[str, str]) -> float:
    """The shopper's true chance of buying when shown this arm; `hidden` has `discount`, `health_focus` and `newness` levels."""
    trait = {"offer": "discount", "title": "health_focus", "image": "newness"}[kind]
    lift = LIFT[kind][hidden[trait]] if arm == ARMS[kind][1] else 1.0
    return min(0.6, base * lift)


def margin(kind: str, arm: str, price: float, cost: float) -> float:
    return round(price * OFFER_SHARE - cost, 2) if (kind, arm) == ("offer", "offer") else round(price - cost, 2)


def gen_experiments(seed: int, customers: list[dict], products: list[dict], unit_cost: dict[str, float], units_sold: dict[str, int],
                    offer_buyer: dict[str, str], wellness_band: dict[str, str], months: list[str]) -> dict[str, list[dict]]:
    """The three tables and the answer key's chances. `customers` carry the hidden levels (`discount`, `health_focus`, `newness`), their `pets`,
    `first_source` and `consent`; only customers who consented to behavioural profiling are shown anything (ADR 0044). `months` are the months the
    experiments ran, the last of which the evidence holds out."""
    by_sku = {p["sku"]: p for p in products}
    plans = plan_experiments(products, units_sold, months)
    experiments, variants, showings, chances = [], [], [], {}
    for plan in plans:
        product, price, cost = by_sku[plan.sku], by_sku[plan.sku]["price_eur"], unit_cost[plan.sku]
        base = BASE_CHANCE[0] + (BASE_CHANCE[1] - BASE_CHANCE[0]) * stream(seed, "experiment-base", plan.sku).random()
        first, second = ARMS[plan.kind]
        for arm in (first, second):
            variants.append({"variant_id": f"{plan.experiment_id}:{arm}", "experiment": plan.experiment_id, "product_sku": plan.sku, "kind": plan.kind,
                             "arm": arm, "is_control": arm == first, "price_eur": round(price * OFFER_SHARE, 2) if (plan.kind, arm) == ("offer", "offer") else price,
                             "margin_eur": margin(plan.kind, arm, price, cost),
                             "title": f"{product['name']}: {BENEFIT[product['category']]}" if (plan.kind, arm) == ("title", "benefit") else product["name"],
                             "image": f"{plan.sku}-{arm}.jpg" if plan.kind == "image" else f"{plan.sku}-packshot.jpg"})
        eligible = [c for c in customers if c["consent"] and product["pet_type"] in c["pets"]]
        chances[plan.experiment_id] = {c["customer_id"]: [round(true_chance(plan.kind, arm, base, c["hidden"]), 4) for arm in (first, second)] for c in eligible}
        winner = None
        for month_index, month in enumerate(months):
            if plan.status == "draft":
                break
            if plan.status == "decided" and month_index == DECIDED_AFTER and winner is None:
                winner = _observed_winner(plan, showings, price, cost)
            for customer in eligible:
                rng = stream(seed, "experiment-showing", plan.experiment_id, customer["customer_id"], month)
                for n in range(SHOWINGS_PER_MONTH):
                    arm = winner if winner and rng.random() < SERVE_WINNER else rng.choice((first, second))
                    chance = chances[plan.experiment_id][customer["customer_id"]][(first, second).index(arm)]
                    signal = signal_of(plan.kind, customer, offer_buyer, wellness_band)
                    showings.append({"showing_id": f"{plan.experiment_id}-{customer['customer_id']}-{month}-{n}", "experiment": plan.experiment_id,
                                     "product_sku": plan.sku, "customer": customer["customer_id"], "month": month,
                                     "variant": f"{plan.experiment_id}:{arm}", "purchased": rng.random() < chance,
                                     "signal": signal, "signal_arm": f"{signal}|{arm}"})
        experiments.append({"experiment_id": plan.experiment_id, "product_sku": plan.sku, "kind": plan.kind,
                            "hypothesis": _hypothesis(plan.kind, product), "status": plan.status,
                            "started_month": None if plan.status == "draft" else months[0], "decided_month": plan.decided_month,
                            "decided_arm": winner, "allocation": 0.5, "explore_floor": 0.1, "signal": SIGNAL_OF[plan.kind]})
    return {"experiments": experiments, "experiment_variants": variants, "experiment_showings": showings, "chances": chances}


def _observed_winner(plan: Plan, showings: list[dict], price: float, cost: float) -> str:
    """What the team decides after the first months: the arm with the higher profit per showing so far, from what was observed."""
    shown, sold = defaultdict(int), defaultdict(int)
    for row in showings:
        if row["experiment"] == plan.experiment_id:
            arm = row["variant"].split(":")[1]
            shown[arm] += 1
            sold[arm] += row["purchased"]
    return max(ARMS[plan.kind], key=lambda arm: sold[arm] / shown[arm] * margin(plan.kind, arm, price, cost))


def _hypothesis(kind: str, product: dict) -> str:
    name = product["name"]
    return {"offer": f"A 15 % offer on {name} earns more profit than it gives away in margin.",
            "title": f"A title that leads with the benefit sells {name} better than its plain name.",
            "image": f"A lifestyle image sells {name} better than the pack shot."}[kind]
