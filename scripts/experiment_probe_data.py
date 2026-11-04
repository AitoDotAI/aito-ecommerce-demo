"""The synthetic shop of `scripts/experiment_probe.py` (docs/verification/experiments-prereg.md): shoppers with hidden sensitivities, products with two
variants each, and the showings of a random 50/50 experiment. The generator knows every true purchase chance, so a policy is scored without noise."""
from __future__ import annotations

import random
from dataclasses import dataclass

SHOPPERS, PRODUCTS, SESSIONS, SHOWN, HELD_OUT = 1200, 60, 24, 8, 2
CATEGORIES = ("dry-food", "wet-food", "treats", "toys", "litter", "health", "grooming", "accessories")
KINDS = ("offer", "title", "image")                  # 20 products each
ARMS = {"offer": ("list", "offer"), "title": ("plain", "benefit"), "image": ("packshot", "lifestyle")}
OFFER_SHARE = 0.85                                   # the offer arm's price, as a share of the list price
# How much each hidden trait level multiplies the chance of a purchase when the shopper is shown the second arm.
LIFT = {"offer": {"high": 2.6, "mid": 1.4, "low": 1.05}, "title": {"high": 1.5, "low": 0.95}, "image": {"high": 1.4, "low": 1.0}}
TRAIT = {"offer": "discount", "title": "health_focus", "image": "visual"}


@dataclass(frozen=True)
class Shopper:
    shopper_id: str
    traits: dict[str, str]
    favourites: tuple[str, str]


@dataclass(frozen=True)
class Product:
    sku: str
    category: str
    kind: str
    list_price: float
    cost: float
    popularity: float

    def variant_id(self, arm: str) -> str:
        return f"{self.sku}:{arm}"

    def price(self, arm: str) -> float:
        return round(self.list_price * OFFER_SHARE, 2) if (self.kind, arm) == ("offer", "offer") else self.list_price

    def margin(self, arm: str) -> float:
        return round(self.price(arm) - self.cost, 2)


def make_shoppers(rng: random.Random) -> list[Shopper]:
    pick = lambda levels, weights: rng.choices(levels, weights)[0]
    return [Shopper(f"S{i:04d}", {"discount": pick(("high", "mid", "low"), (30, 45, 25)), "health_focus": pick(("high", "low"), (35, 65)),
                                  "visual": pick(("high", "low"), (40, 60))}, tuple(rng.sample(CATEGORIES, 2))) for i in range(SHOPPERS)]


def make_products(rng: random.Random) -> list[Product]:
    kinds = [kind for kind in KINDS for _ in range(PRODUCTS // len(KINDS))]
    rng.shuffle(kinds)
    out = []
    for i, kind in enumerate(kinds):
        price = round(rng.uniform(8, 40), 2)
        out.append(Product(f"P{i:03d}", CATEGORIES[i % len(CATEGORIES)], kind, price, round(price * rng.uniform(0.55, 0.72), 2), rng.uniform(0.02, 0.10)))
    return out


def chance(shopper: Shopper, product: Product, arm: str) -> float:
    """The true chance this shopper buys this product when shown this arm."""
    base = product.popularity * (2.0 if product.category in shopper.favourites else 0.7)
    second = arm == ARMS[product.kind][1]
    lift = LIFT[product.kind][shopper.traits[TRAIT[product.kind]]] if second else 1.0
    return min(0.6, base * lift)


def make_showings(rng: random.Random, shoppers: list[Shopper], products: list[Product]) -> list[dict]:
    """Every shopper is shown `SHOWN` products a session for `SESSIONS` sessions, favourite categories more often; the arm is a coin flip."""
    rows = []
    for shopper in shoppers:
        weights = [3.0 if p.category in shopper.favourites else 1.0 for p in products]
        for session in range(SESSIONS):
            seen: set[str] = set()
            while len(seen) < SHOWN:
                product = rng.choices(products, weights)[0]
                if product.sku in seen:
                    continue
                seen.add(product.sku)
                arm = rng.choice(ARMS[product.kind])
                rows.append({"shopper": shopper.shopper_id, "sku": product.sku, "session": session, "arm": arm,
                             "purchased": rng.random() < chance(shopper, product, arm)})
    return rows


def profit(shopper: Shopper, product: Product, arm: str) -> float:
    """Expected profit of showing this arm to this shopper, from the true chance."""
    return chance(shopper, product, arm) * product.margin(arm)


def observed_winner(showings: list[dict], products: dict[str, Product]) -> dict[str, str]:
    """What a plain A/B test decides per product: the arm with the higher observed profit per showing over everybody."""
    shown, sold = {}, {}
    for row in showings:
        key = (row["sku"], row["arm"])
        shown[key] = shown.get(key, 0) + 1
        sold[key] = sold.get(key, 0) + row["purchased"]
    per_showing = lambda sku, arm: sold.get((sku, arm), 0) / shown[(sku, arm)] * products[sku].margin(arm)
    return {sku: max(ARMS[p.kind], key=lambda arm: per_showing(sku, arm)) for sku, p in products.items()}


def leans(train: list[dict], products: dict[str, Product]) -> dict[tuple[str, str], str]:
    """What a shop can observe of how a shopper reacts to each kind of variant: the shopper's purchase rate on the kind's second arm against the first,
    from the training showings only, in thirds across shoppers ("lo", "mid", "hi"). A shopper has few purchases, so this is a noisy but honest signal."""
    shown, sold = {}, {}
    for row in train:
        key = (row["shopper"], products[row["sku"]].kind, row["arm"])
        shown[key] = shown.get(key, 0) + 1
        sold[key] = sold.get(key, 0) + row["purchased"]
    ratio = {}
    for shopper, kind in {(s, k) for s, k, _ in shown}:
        first, second = ARMS[kind]
        rate = lambda arm: (sold.get((shopper, kind, arm), 0) + 0.5) / (shown.get((shopper, kind, arm), 0) + 1)
        ratio[shopper, kind] = rate(second) / rate(first)
    bands = {}
    for kind in {k for _, k in ratio}:
        ordered = sorted(v for (_, k), v in ratio.items() if k == kind)
        low, high = ordered[len(ordered) // 3], ordered[2 * len(ordered) // 3]
        bands.update({key: "lo" if v < low else "hi" if v >= high else "mid" for key, v in ratio.items() if key[1] == kind})
    return bands


def oracle_numbers(seed: int = 7) -> dict:
    rng = random.Random(seed)
    shoppers, products = make_shoppers(rng), make_products(rng)
    by_sku, by_id = {p.sku: p for p in products}, {s.shopper_id: s for s in shoppers}
    showings = make_showings(rng, shoppers, products)
    train = [r for r in showings if r["session"] < SESSIONS - HELD_OUT]
    held = [r for r in showings if r["session"] >= SESSIONS - HELD_OUT]
    winner = observed_winner(train, by_sku)
    policies = {"P0 control": lambda s, p: ARMS[p.kind][0], "P1 winner": lambda s, p: winner[p.sku],
                "P3 oracle": lambda s, p: max(ARMS[p.kind], key=lambda arm: profit(s, p, arm))}
    value = {name: sum(profit(by_id[r["shopper"]], by_sku[r["sku"]], choose(by_id[r["shopper"]], by_sku[r["sku"]])) for r in held) / len(held)
             for name, choose in policies.items()}
    return {"showings": len(showings), "train": len(train), "held_out": len(held), "profit_per_showing": value,
            "purchases_in_train": sum(r["purchased"] for r in train), "winner_arms": {k: sum(winner[p.sku] == ARMS[k][1] for p in products if p.kind == k) for k in KINDS}}


if __name__ == "__main__":
    import json
    print(json.dumps(oracle_numbers(), indent=1))
