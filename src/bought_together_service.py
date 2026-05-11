"""Bought Together — order-level co-occurrence via `_relate`.

Driven by the denormalised `orders.line_categories` Text column.
See `docs/adr/0008-bought-together.md` for the live query shape +
the denormalisation rationale.

One live Aito call per request:
  `_relate from orders where {line_categories: {$match: <anchor>}}
   relate line_categories`

Cached per anchor for 10 minutes.
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path

from src.aito_client import AitoClient
from src import cache


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ── Anchors the picker shows ───────────────────────────────────────


@dataclass(frozen=True)
class AnchorOption:
    anchor_id: str    # token form, e.g. "dog_dryfood"
    pet_type: str
    category: str     # the original hyphenated form, e.g. "dry-food"
    display: str      # "Dog dry-food"


ANCHORS: list[AnchorOption] = [
    AnchorOption("dog_dryfood",     "dog",          "dry-food",      "Dog dry-food"),
    AnchorOption("cat_wetfood",     "cat",          "wet-food",      "Cat wet-food"),
    AnchorOption("cat_litter",      "cat",          "litter",        "Cat litter"),
    AnchorOption("dog_dentaltreats","dog",          "dental-treats", "Dog dental treats"),
    AnchorOption("aquarium_aquarium","aquarium",    "aquarium",      "Aquarium food"),
    AnchorOption("dog_accessories", "dog",          "accessories",   "Dog accessories"),
]

DEFAULT_ANCHOR = "dog_dryfood"


# ── DTOs ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SkuSample:
    sku: str
    name: str
    brand: str
    price_eur: float


@dataclass(frozen=True)
class CrossSell:
    label: str
    token: str
    lift: float
    support: dict
    sample_skus: list[SkuSample]


@dataclass(frozen=True)
class Anchor:
    id: str
    pet_type: str
    category: str
    display: str
    sample_skus: list[SkuSample]


@dataclass
class BoughtTogetherResponse:
    anchor: Anchor
    cross_sells: list[CrossSell]
    available_anchors: list[dict]
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "anchor": {
                **{k: v for k, v in asdict(self.anchor).items() if k != "sample_skus"},
                "sample_skus": [asdict(s) for s in self.anchor.sample_skus],
            },
            "cross_sells": [
                {
                    "label":   c.label,
                    "token":   c.token,
                    "lift":    c.lift,
                    "support": c.support,
                    "sample_skus": [asdict(s) for s in c.sample_skus],
                }
                for c in self.cross_sells
            ],
            "available_anchors": self.available_anchors,
            "last_query":        self.last_query,
            "last_response_ms":  self.last_response_ms,
        }


# ── Token utilities ────────────────────────────────────────────────


_TOKEN_TO_PAIR: dict[str, tuple[str, str]] = {
    a.anchor_id: (a.pet_type, a.category) for a in ANCHORS
}


def _token_to_pair(token: str) -> tuple[str, str] | None:
    """Decode `<pet>_<cleanedcategory>` → (pet_type, category_hyphenated).

    The token form strips hyphens from the category (`dry-food` →
    `dryfood`) so Aito treats the pair as one Text feature. To
    decode we need the catalog of known categories; we read it from
    `products.json` once at module load.
    """
    if token in _TOKEN_TO_PAIR:
        return _TOKEN_TO_PAIR[token]
    # Generic decode for any (pet, cat) pair the fixtures emit.
    pet, _, clean_cat = token.partition("_")
    if not clean_cat:
        return None
    return pet, _CLEAN_TO_HYPHENATED.get(clean_cat, clean_cat)


# Build the cleaned→hyphenated map from the static category list in
# `data/generate_fixtures.py`. Keeps the service from importing the
# whole generator module.
_CLEAN_TO_HYPHENATED: dict[str, str] = {
    cat.replace("-", ""): cat
    for cat in (
        "dry-food", "wet-food", "treats", "dental-treats",
        "litter", "accessories", "health", "grooming",
        "toys", "aquarium",
    )
}


# ── Local catalog snapshot ─────────────────────────────────────────


def _load_products() -> list[dict]:
    return json.loads((DATA_DIR / "products.json").read_text())


def _sample_skus_for_pair(
    products: list[dict],
    pet_type: str,
    category: str,
    limit: int = 3,
) -> list[SkuSample]:
    matching = [
        p for p in products
        if p.get("pet_type") == pet_type and p.get("category") == category
    ]
    # Stable sort by name so the sample doesn't churn between cache
    # windows.
    matching.sort(key=lambda p: p.get("name", ""))
    return [
        SkuSample(
            sku=p["sku"],
            name=p["name"],
            brand=p.get("brand", ""),
            price_eur=round(float(p.get("price_eur", 0)), 2),
        )
        for p in matching[:limit]
    ]


# ── Public entry point ────────────────────────────────────────────


def get_bought_together(
    client: AitoClient,
    *,
    anchor_id: str = DEFAULT_ANCHOR,
) -> BoughtTogetherResponse:
    cache_key = f"bought_together:{anchor_id}"
    cached = cache.get(cache_key)
    if cached:
        return _from_dict(cached)

    pair = _token_to_pair(anchor_id)
    if pair is None:
        raise ValueError(f"Unknown anchor: {anchor_id!r}")
    pet_type, category = pair

    body = {
        "from": "orders",
        "where": {"line_categories": {"$match": anchor_id}},
        "relate": "line_categories",
        "limit": 12,
    }

    started = time.perf_counter()
    res = client.relate(
        table="orders",
        where=body["where"],
        relate_field="line_categories",
        limit=12,
    )
    elapsed = int((time.perf_counter() - started) * 1000)

    products = _load_products()

    cross_sells: list[CrossSell] = []
    for hit in res.get("hits", []):
        rel = hit.get("related", {}).get("line_categories", {})
        token = rel.get("$has") if isinstance(rel, dict) else None
        if not token or token == anchor_id:
            continue   # skip self-anchor
        lift = float(hit.get("lift", 0))
        if lift < 1.2:
            # Genuinely positive cross-sells only. Lifts between 0.5
            # and 1.2 read as "neither bought together nor
            # protective" — noise for this view. Real anti-
            # correlated patterns ("people who bought X did NOT buy
            # Y") belong in Pattern Explorer.
            continue
        decoded = _token_to_pair(token)
        if decoded is None:
            continue
        cs_pet, cs_cat = decoded
        fs = hit.get("fs", {}) or {}
        cross_sells.append(CrossSell(
            label=_humanise(cs_pet, cs_cat),
            token=token,
            lift=round(lift, 2),
            support={
                "f":               int(fs.get("f", 0)),
                "f_on_condition":  int(fs.get("fOnCondition", 0)),
            },
            sample_skus=_sample_skus_for_pair(products, cs_pet, cs_cat),
        ))
        if len(cross_sells) >= 4:
            break

    anchor_obj = Anchor(
        id=anchor_id,
        pet_type=pet_type,
        category=category,
        display=_humanise(pet_type, category),
        sample_skus=_sample_skus_for_pair(products, pet_type, category),
    )

    resp = BoughtTogetherResponse(
        anchor=anchor_obj,
        cross_sells=cross_sells,
        available_anchors=[
            {"id": a.anchor_id, "display": a.display}
            for a in ANCHORS
        ],
        last_query={"endpoint": "_relate", "body": body},
        last_response_ms=elapsed,
    )

    cache.set(cache_key, resp.to_dict(), ttl=600)
    return resp


def _humanise(pet_type: str, category: str) -> str:
    """`("dog", "dry-food")` → `"Dog dry-food"`. Capitalises the pet
    label; keeps the category verbatim (it's already lowercase + hyphen
    where applicable, which reads naturally as a product-section name)."""
    label_pet = "Aquarium" if pet_type == "aquarium" else pet_type.replace("_", " ").capitalize()
    label_cat = category
    if pet_type == "aquarium" and category == "aquarium":
        return "Aquarium products"   # avoid "Aquarium aquarium"
    return f"{label_pet} {label_cat}"


# ── Cache round-trip ──────────────────────────────────────────────


def _from_dict(d: dict) -> BoughtTogetherResponse:
    anchor = d["anchor"]
    return BoughtTogetherResponse(
        anchor=Anchor(
            id=anchor["id"],
            pet_type=anchor["pet_type"],
            category=anchor["category"],
            display=anchor["display"],
            sample_skus=[SkuSample(**s) for s in anchor["sample_skus"]],
        ),
        cross_sells=[
            CrossSell(
                label=c["label"],
                token=c["token"],
                lift=c["lift"],
                support=c["support"],
                sample_skus=[SkuSample(**s) for s in c["sample_skus"]],
            )
            for c in d["cross_sells"]
        ],
        available_anchors=d["available_anchors"],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
