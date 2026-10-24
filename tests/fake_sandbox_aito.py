"""A fake sandbox branch for the lever tests: an in-memory `product_states`
and `reviews`, answering the v2 shapes the levers send (ADR 0043):

    POST /_search          {"from", "where", "limit", "select"?} → {"total", "hits"}
    POST /data/_modify     {"into", "insert"}                      → insert one row
                           {"update", "set", "where"}              → update the rows matching

A `where` here is field equality, or `{"$or": [...]}` on one field: the
forms the levers use. Every request is recorded, so a test can assert
which URL (which env) each write went to.
"""

from __future__ import annotations

import json

import httpx

BRANCH = "tmp-2026-10-26-15-30-00-3f9c2a1b7d4e6f80"
SANDBOX_URL = "https://shared.aito.ai/db/aito-ecommerce-sandbox"
BRANCH_API = f"{SANDBOX_URL}/env/{BRANCH}/api/v2"


def april_state(sku: str, *, rating_band: str = "3", band: str = "none") -> dict:
    return {"product_state_id": f"{sku}-2026-04", "product_sku": sku, "month": "2026-04",
            "price_eur": 20.0, "list_price_eur": 20.0, "discount_pct": 0.0, "on_offer": False,
            "discount_band": band, "rating_band": rating_band, "age": "established",
            "rival_launched": False, "price_change": "none"}


def review(sku: str, n: int, rating: int) -> dict:
    return {"review_id": f"REV-{sku}-{n}", "product_sku": sku, "rating": rating}


class FakeBranch:
    def __init__(self, states: list[dict], reviews: list[dict]) -> None:
        self.tables = {"product_states": list(states), "reviews": list(reviews)}
        self.requests: list[tuple[str, str, object]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read()) if request.content else None
        path = request.url.path.split("/api/v2", 1)[1]
        self.requests.append((request.method, str(request.url), body))
        if path == "/_search":
            hits = [r for r in self.tables[body["from"]] if _matches(r, body.get("where", {}))]
            shown = hits[: body.get("limit", 10)]
            if "select" in body:
                shown = [{k: r[k] for k in body["select"]} for r in shown]
            return httpx.Response(200, json={"kind": "rows", "total": len(hits), "hits": shown})
        if path == "/data/_modify" and "into" in body:
            self.tables[body["into"]].append(dict(body["insert"]))
            return httpx.Response(200, json={"total": 1})
        if path == "/data/_modify" and "update" in body:
            rows = [r for r in self.tables[body["update"]] if _matches(r, body["where"])]
            for row in rows:
                row.update(body["set"])
            return httpx.Response(200, json={"total": len(rows)})
        return httpx.Response(404, json={"error": f"the fake doesn't serve {path}"})

    def writes(self) -> list[tuple[str, str]]:
        return [(method, url) for method, url, _ in self.requests if "/data/" in url]


def _matches(row: dict, where: dict) -> bool:
    for field, wanted in where.items():
        if isinstance(wanted, dict) and "$or" in wanted:
            if row.get(field) not in wanted["$or"]:
                return False
        elif row.get(field) != wanted:
            return False
    return True
