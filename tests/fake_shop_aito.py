"""A fake Aito for the Shop's tests: the shapes Aito 2.11.4 returned on the
ADR 0030 data, trimmed to what the Shop reads. The live behaviour of the
same queries is checked in test_aito_check.py.
"""

CUSTOMERS = {
    # Declared and recorded fields only (ADR 0033).
    "CUST-00828": {"customer_id": "CUST-00828", "pets": "dog", "dog_size": "medium", "diet": "grain-free"},
    "CUST-00053": {"customer_id": "CUST-00053", "pets": "cat"},
}


def product(sku, p=0.0, category="dry-food", pet_type="cat", reason=("context.month", "2026-04", 1.3), name=None):
    """A `_recommend` hit, with a `$why` holding one reason for it."""
    field, value, lift = reason
    return {"sku": sku, "name": name or f"Brand {sku}", "brand": "Brand", "pet_type": pet_type,
            "category": category, "price_eur": 4.0, "avg_rating": 4.2, "$p": p,
            "$why": {"type": "product", "factors": [
                {"type": "hitPropositionLift", "proposition": {"product_sku": {"$has": sku}}, "value": 2.0,
                 "factors": [{"type": "relatedPropositionLift", "proposition": {field: value}, "value": lift}]}]}}


class FakeShopAito:
    def __init__(self, ranked, last_order="SKU-B SKU-X", reasked_p=0.02, offers=None, text_scores=None):
        self.ranked = ranked
        self.last_order = last_order
        self.reasked_p = reasked_p
        self.offers = offers or {}               # {sku: discount_pct} this month
        self.text_scores = text_scores or {}     # {sku: $score} for a name query
        self.recommends: list[dict] = []
        self.batches: list[list[dict]] = []

    def search(self, table, *, where=None, limit=10, **kwargs):
        if table == "customers":
            return {"hits": [CUSTOMERS[where["customer_id"]]]}
        if table == "products" and "order_by" in kwargs:
            hits = [{"sku": s, "$score": score} for s, score in self.text_scores.items()]
            return {"hits": hits, "total": len(hits)}
        if table == "products":
            skus = where["sku"]["$or"] if isinstance(where["sku"], dict) else [where["sku"]]
            return {"hits": [product(s) for s in skus if s.startswith("SKU-")]}
        if table == "product_states":
            rows = [{"product_sku": s, "discount_pct": self.offers.get(s, 0.0), "on_offer": s in self.offers}
                    for s in where["product_sku"]["$or"]]
            return {"hits": rows, "total": len(rows)}
        orders = [{"month": "2026-03", "skus": self.last_order}, {"month": "2025-11", "skus": "SKU-OLD"}]
        return {"hits": orders, "total": len(orders)}

    def recommend(self, table, where, recommend_field, goal, *, select=None, limit=8, **_):
        self.recommends.append(where)
        hits = self.ranked
        if isinstance(where.get("product_sku"), dict) and "$or" in where["product_sku"]:
            hits = [h for h in hits if h["sku"] in where["product_sku"]["$or"]]
        return {"hits": hits[:limit]}

    def batch(self, queries):
        self.batches.append(queries)
        return [{"hits": [{"feature": False, "$p": 1 - self.reasked_p}, {"feature": True, "$p": self.reasked_p}]}
                for _ in queries]
