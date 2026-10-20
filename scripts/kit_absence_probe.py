#!/usr/bin/env python3
"""Does Aito use what a household's kit LACKS? Read-only probe (ADR 0033, K1).

    AITO_ENV=observable PYTHONPATH=. python scripts/kit_absence_probe.py

`context.owned` is the full set of kit items a household owns. The query
states it as `$match` tokens, then also as `$not $match` for the missing ones;
the kit's next item should rank higher with the absences stated. Aito core
uses it as the acceptance test for absence inference on `_recommend` and
link paths (docs/notes/aito-core-findings-2026-10-18.md; aito-core
.ai/results/recommend-absence-in-text-context-2026-10-20.md).
"""
import json
from src.aito_client import AitoClient
from src.config import load_config
c = AitoClient(load_config())
owns = [{"$match": "small_animal_cage"}, {"$match": "small_animal_water_bottle"}]
lacks = [{"$not": {"$match": f"small_animal_{k}"}} for k in ("hideout", "exercise_wheel", "tunnel")]
for label, owned in (("owns cage + bottle", {"$and": owns}),
                     ("owns cage + bottle, lacks hideout/wheel/tunnel", {"$and": owns + lacks})):
    where = {"context.owned": owned, "product_sku.pet_type": "small_animal"}
    hits = c.recommend("impressions", where, "product_sku", {"purchased": True},
                       select=["name", "$p", "$why"], limit=40)["hits"]
    print(f"\n{label}")
    for i, h in enumerate(hits[:12]):
        own = next(f for f in h["$why"]["factors"] if f["type"] == "hitPropositionLift" and "$not" not in json.dumps(f["proposition"]))
        ctx = own["factors"][0]["value"] if own.get("factors") else 1.0
        print(f"  {i + 1:>2}. {h['name']:<36} p {h['$p']:.3f}  context lift ×{ctx:.2f}")
    n = c.search("impressions", where={"context.owned": owned}, limit=0)["total"]
    print(f"  impressions matching the context: {n}")
