#!/usr/bin/env python3
"""Shop scenarios: who sees what, and how the cart is described. Read-only.

    AITO_ENV=observable PYTHONPATH=. python scripts/shop_scenarios.py

Each scenario (a shopper, a month, a cart) is ranked twice: the cart as
SKUs + category words, and as words only. Reported per scenario: how much
of the top 12 is for the household's declared pets, where the kit add-ons
rank, the first dental treat after dog food (planted), and rule-breaking
food for a diet household. Aito core's acceptance harness for sparse joint
contexts (aito-core .ai/results/recommend-sparse-joint-context-2026-10-20.md).
"""
import json
from src.aito_client import AitoClient
from src.config import load_config
from src.shop_ranking import shop_scope
c = AitoClient(load_config())
P = {p["sku"]: p for p in json.load(open("data/products.json"))}
CUST = {x["customer_id"]: x for x in json.load(open("data/customers.json"))}
from src.shop_personas import shopper

def sku_like(pred):
    return next(s for s, p in P.items() if pred(p))

GP_FOOD = "SKU-PT-0533"
HIDEOUT = sku_like(lambda p: p["name"] == "PetNord Hideout")
CAGE = "SKU-PT-0555"
DOG_DRY = sku_like(lambda p: p["pet_type"] == "dog" and p["category"] == "dry-food" and "Grain Free" in p["name"])
DOG_DRY_ANY = sku_like(lambda p: p["pet_type"] == "dog" and p["category"] == "dry-food" and "Grain" not in p["name"])
LITTER = sku_like(lambda p: p["category"] == "litter")
SCENARIOS = [
    ("paivi", "2026-04", [], "kit"), ("paivi", "2026-04", [GP_FOOD], "kit"), ("paivi", "2026-04", [HIDEOUT], "kit"),
    ("paivi", "2026-02", [CAGE], "kit"),
    ("janne", "2026-04", [], "rule"), ("janne", "2026-04", [DOG_DRY], "dental"),
    ("helena", "2026-04", [], "pets"), ("olli", "2026-04", [DOG_DRY_ANY], "dental"), ("maija", "2026-04", [LITTER], "pets"),
]

def run(key, month, cart, look):
    s = shopper(key); pets = set(CUST[s.customer_id]["pets"].split())
    scope = shop_scope(c, key, month, cart)
    words = scope.where()   # the Shop states the cart as words (td-20261020210945109481)
    with_skus = {**words, "context.basket": {"$and": [{"$match": sku} for sku in cart]}} if cart else words
    out = []
    for label, where in (("SKUs+words", with_skus), ("words only", words)):
        hits = c.recommend("impressions", where, "product_sku", {"purchased": True}, select=["sku", "name", "pet_type", "category", "$p"], limit=40)["hits"]
        top = hits[:12]
        fit = sum(h["pet_type"] in pets for h in top)
        note = ""
        if look == "kit":
            note = "kit ranks " + str([(i + 1, h["name"].split()[-1] if "Wheel" not in h["name"] else "Wheel") for i, h in enumerate(hits)
                                       if any(k in h["name"] for k in ("Hideout", "Exercise Wheel", "Tunnel", "Water Bottle"))][:4])
        if look == "dental":
            d = [i + 1 for i, h in enumerate(hits) if h["category"] == "dental-treats"]
            note = f"first dental treat at #{d[0] if d else '-'}"
        if look == "rule":
            note = f"rule-breaking food in top 12: {sum(h['category'] in ('dry-food','wet-food') and h['pet_type'] in ('dog','cat') and 'Grain' not in h['name'] for h in top)}"
        out.append(f"  {label:<11} fits pets {fit:>2}/12  {note}\n              top 4: {[h['name'][-24:] for h in top[:4]]}")
    cart_names = [P[x]["name"] for x in cart]
    print(f"\n{s.name} ({' '.join(sorted(pets))}), {month}, cart {cart_names or 'empty'}")
    print("\n".join(out))

for sc in SCENARIOS:
    run(*sc)
