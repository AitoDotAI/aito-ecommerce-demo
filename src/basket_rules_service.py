"""Basket Rules — association-rule mining as a live query.

Where Bought Together (ADR 0008) is a single-anchor drill-down, this
view *mines* the catalogue for the strongest basket rules `A → B` and
ranks them by lift. No Apriori batch job — each rule's support,
confidence, and lift come straight out of one `_relate` per anchor.

The mining query (ADR 0022), verified live — the order-level
co-occurrence relate over the denormalised category-token bag:

  `_relate from orders
     where  {line_categories: {$match: "<A token>"}}
     relate "line_categories"`

Conditions on orders containing token A, relates the other tokens in
those orders. Order-granular (`fs.n` = total orders), so each hit gives
the rule directly:
  confidence = fs.fOnCondition / fs.fCondition  (= P(B in order | A))
  support    = fs.fOnCondition / total_orders
  lift       = lift

(Anchoring per-SKU via link traversal — `from order_lines ... relate
"order_id.line_categories"` — does NOT condition the stats per anchor;
it returns the related token's global frequencies. The order-bag relate
above is the right shape for category->category rules. SKU->SKU is a
follow-up needing an `orders.line_skus` field — ADR 0022.)

A rule is emitted only when it is both *concentrated* (lift > 1,
confidence high) AND *frequent enough* to trust (absolute count gate) —
a thin anchor must not produce a spurious 100%/n=2 "rule".

Cached 10 minutes (same TTL as the other `_relate` views).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict

from src.aito_client import AitoClient
from src import cache


# ── Mining configuration ───────────────────────────────────────────

# The (pet_type, category) anchors we mine. Curated to the catalogue's
# high-volume pairs so the sweep is fast and every anchor has the
# support to yield real rules. NOT an exhaustive itemset enumeration —
# we surface strong pairwise rules; see ADR 0022 §"Out of scope".
_ANCHORS: list[tuple[str, str]] = [
    ("dog", "dry-food"), ("dog", "wet-food"), ("dog", "treats"),
    ("dog", "dental-treats"), ("dog", "accessories"),
    ("cat", "dry-food"), ("cat", "wet-food"), ("cat", "litter"),
    ("cat", "treats"),
    ("aquarium", "aquarium"),
]

# A rule must clear ALL THREE gates. The absolute-count gate is the
# load-bearing one: it stops a thin anchor (few orders, all sharing a
# token) from publishing as a confident "rule" (the rule-mining
# pitfall — see ADR 0022 / the accounting demo's guide).
MIN_LIFT = 1.0          # strictly positive association (> 1)
MIN_CONFIDENCE = 0.30   # P(B in order | A on line)
MIN_COUNT = 50          # absolute fOnCondition — no spurious thin slices

MAX_RULES = 15          # how many top rules the view returns

_CATEGORIES = (
    "dry-food", "wet-food", "treats", "dental-treats",
    "litter", "accessories", "health", "grooming", "toys", "aquarium",
)
_CLEAN_TO_HYPHENATED: dict[str, str] = {c.replace("-", ""): c for c in _CATEGORIES}


def _token(pet_type: str, category: str) -> str:
    """`("dog", "dry-food")` → `"dog_dryfood"` — the hyphen-stripped
    Text token used in `orders.line_categories` (ADR 0008)."""
    return f"{pet_type}_{category.replace('-', '')}"


def _decode(token: str) -> tuple[str, str] | None:
    """`"dog_dryfood"` → `("dog", "dry-food")`. `rpartition` splits on
    the LAST `_` because pet types like `small_animal` carry one."""
    pet, _, clean_cat = token.rpartition("_")
    if not clean_cat:
        return None
    return pet, _CLEAN_TO_HYPHENATED.get(clean_cat, clean_cat)


def _humanise(pet_type: str, category: str) -> str:
    if pet_type == "aquarium" and category == "aquarium":
        return "Aquarium products"
    label_pet = "Aquarium" if pet_type == "aquarium" else pet_type.replace("_", " ").capitalize()
    return f"{label_pet} {category}"


# ── DTOs ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BasketRule:
    antecedent: str        # "Dog dry-food"
    consequent: str        # "Dog dental treats"
    confidence: float      # P(consequent | antecedent), 0..1
    lift: float
    support_orders: int    # fOnCondition — # orders the rule holds in
    support_pct: float     # support_orders / total_orders


@dataclass
class BasketRulesResponse:
    rules: list[BasketRule]
    anchors_mined: int
    total_orders: int
    last_query: dict
    last_response_ms: int

    def to_dict(self) -> dict:
        return {
            "rules": [asdict(r) for r in self.rules],
            "anchors_mined": self.anchors_mined,
            "total_orders": self.total_orders,
            "last_query": self.last_query,
            "last_response_ms": self.last_response_ms,
        }


# ── Mining ─────────────────────────────────────────────────────────


def _mine_anchor(
    client: AitoClient,
    pet_type: str,
    category: str,
    total_orders: int,
) -> list[BasketRule]:
    """One order-level `_relate` for a single anchor → its rules."""
    anchor_token = _token(pet_type, category)
    res = client.relate(
        table="orders",
        where={"line_categories": {"$match": anchor_token}},
        relate_field="line_categories",
        limit=12,
    )

    rules: list[BasketRule] = []
    for hit in res.get("hits", []):
        rel = hit.get("related", {}).get("line_categories", {})
        token = rel.get("$has") if isinstance(rel, dict) else None
        if not token or token == anchor_token:
            continue  # skip the self-token

        lift = float(hit.get("lift", 0))
        fs = hit.get("fs", {}) or {}
        f_cond = float(fs.get("fCondition", 0))
        f_on = float(fs.get("fOnCondition", 0))
        confidence = f_on / f_cond if f_cond else 0.0

        # The three gates — concentrated AND frequent enough to trust.
        if lift <= MIN_LIFT or confidence < MIN_CONFIDENCE or f_on < MIN_COUNT:
            continue

        decoded = _decode(token)
        if decoded is None:
            continue
        rules.append(BasketRule(
            antecedent=_humanise(pet_type, category),
            consequent=_humanise(*decoded),
            confidence=round(confidence, 3),
            lift=round(lift, 2),
            support_orders=int(f_on),
            support_pct=round(f_on / total_orders, 3) if total_orders else 0.0,
        ))
    return rules


def get_basket_rules(client: AitoClient) -> BasketRulesResponse:
    cache_key = "basket_rules:all"
    cached = cache.get(cache_key)
    if cached:
        return _from_dict(cached)

    started = time.perf_counter()

    # Support denominator — total orders in the table.
    total_orders = int(
        client._request("POST", "/_query", json={"from": "orders", "limit": 0}).get("total", 0)
    )

    # Mine every anchor in parallel (cf. the Dashboard's relate fan-out).
    with ThreadPoolExecutor(max_workers=min(8, len(_ANCHORS))) as pool:
        per_anchor = pool.map(
            lambda pc: _mine_anchor(client, pc[0], pc[1], total_orders), _ANCHORS
        )
    all_rules = [r for rules in per_anchor for r in rules]

    # Rank by lift, then confidence — the most *concentrated* rules first.
    all_rules.sort(key=lambda r: (r.lift, r.confidence), reverse=True)
    elapsed = int((time.perf_counter() - started) * 1000)

    # Representative query body for the Aito panel (the first anchor's).
    sample_pet, sample_cat = _ANCHORS[0]
    body = {
        "from": "orders",
        "where": {"line_categories": {"$match": _token(sample_pet, sample_cat)}},
        "relate": "line_categories",
        "limit": 12,
    }

    resp = BasketRulesResponse(
        rules=all_rules[:MAX_RULES],
        anchors_mined=len(_ANCHORS),
        total_orders=total_orders,
        last_query={"endpoint": "_relate", "body": body},
        last_response_ms=elapsed,
    )
    cache.set(cache_key, resp.to_dict(), ttl=600)
    return resp


# ── Cache round-trip ──────────────────────────────────────────────


def _from_dict(d: dict) -> BasketRulesResponse:
    return BasketRulesResponse(
        rules=[BasketRule(**r) for r in d["rules"]],
        anchors_mined=d["anchors_mined"],
        total_orders=d["total_orders"],
        last_query=d["last_query"],
        last_response_ms=d["last_response_ms"],
    )
