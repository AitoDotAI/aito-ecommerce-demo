"""What offer brings a customer back? Retention's action on an at-risk row.

`winback_campaigns` holds past re-engagement emails: who got which
product, and whether they ordered (`responded`) and for how much. Three
questions per customer:

  1. `_recommend product_sku … goal {responded: true}`: which products to
     consider, among those for the customer's own pets (a `product_sku.*`
     key filters the candidates). Without that filter a small-animal home
     was offered cat litter. Its `$p` ranks; it is normalised against
     goal-positives and ran near 100 % (the old Win-back view showed it as
     a response rate and was hidden for it), so it is never shown.
  2. `_predict responded` with the product in the `where`: the chance this
     customer orders after that email, a calibrated rate (the cheatsheet's
     "Calibrated rate" pattern).
  3. `_estimate order_value_eur` given `responded: true`: the order's size
     if they do.

The offer is the candidate with the highest expected return:
chance × order value − the email's cost. Every at-risk customer ordered in
the last three months, so the sends are asked as recency "0-90d".
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from src.aito_client import AitoClient, AitoError
from src.catalogue_reads import read_all

EMAIL_COST_EUR = 0.50          # a representative cost per automated email
CANDIDATES = 3
RECENCY_OF_AN_ACTIVE_CUSTOMER = "0-90d"


@dataclass(frozen=True)
class WinbackOffer:
    sku: str
    name: str
    category: str
    price_eur: float
    response_p: float          # calibrated chance they order after the email
    order_value_eur: float     # expected order if they do
    expected_return_eur: float  # response_p × order_value − email cost


def staples_by_customer(client: AitoClient) -> dict[str, str]:
    """The staple each customer's sends record ("dog/dry-food"), derived from their orders."""
    return {r["customer_id"]: r["customer_staple_category"] for r in read_all(client, "winback_campaigns")}


def customer_where(customer_id: str, staple: str) -> dict:
    return {"customer_id": customer_id, "customer_staple_category": staple,
            "recency_bucket": RECENCY_OF_AN_ACTIVE_CUSTOMER}


def recommend_body(where: dict, pets: list[str]) -> dict:
    return {"from": "winback_campaigns", "where": {**where, "product_sku.pet_type": {"$or": pets}},
            "recommend": "product_sku", "goal": {"responded": True}, "limit": CANDIDATES}


def offers_for(client: AitoClient, pets_by_customer: dict[str, list[str]]) -> dict[str, WinbackOffer | None]:
    """The best offer per customer (id → their declared pets), or None when
    no past email sent a product for their pets, so there is nothing to
    learn a response from. Recommends and predicts go in one `_batch` each;
    `_estimate` isn't a batch item (400), so those run in parallel."""
    customer_ids = sorted(pets_by_customer)
    if not customer_ids:
        return {}
    staples = staples_by_customer(client)
    wheres = {cid: customer_where(cid, staples.get(cid, "none")) for cid in customer_ids}
    recommended = dict(zip(customer_ids, client.batch(
        [recommend_body(wheres[c], pets_by_customer[c]) for c in customer_ids])))
    # A batch item's `_recommend` hit is just `$p` and `$value` (the SKU),
    # without the linked product's columns that a direct call returns.
    pairs = [(cid, hit["$value"]) for cid in customer_ids for hit in recommended[cid]["hits"]]
    best: dict[str, WinbackOffer | None] = {cid: None for cid in customer_ids}
    if not pairs:
        return best
    products = {p["sku"]: p for p in client.search(
        "products", where={"sku": {"$or": sorted({sku for _, sku in pairs})}}, limit=len(pairs))["hits"]}

    predicted = client.batch([{"from": "winback_campaigns", "where": {**wheres[cid], "product_sku": sku},
                               "predict": "responded", "limit": 2, "select": ["$p", "feature"]}
                              for cid, sku in pairs])
    with ThreadPoolExecutor(max_workers=8) as pool:
        order_values = list(pool.map(lambda pair: _order_value(client, wheres[pair[0]], pair[1]), pairs))

    for (cid, sku), answer, value in zip(pairs, predicted, order_values, strict=True):
        offer = _offer(products[sku], _true_p(answer, cid, sku), value)
        if best[cid] is None or offer.expected_return_eur > best[cid].expected_return_eur:
            best[cid] = offer
    return best


def _true_p(answer: dict, customer_id: str, sku: str) -> float:
    hit = next((h for h in answer["hits"] if h["feature"] is True), None)
    if hit is None:
        raise AitoError(f"_predict responded for {customer_id} × {sku} has no true hit: {answer}")
    return float(hit["$p"])


def _order_value(client: AitoClient, where: dict, sku: str) -> float:
    res = client.estimate("winback_campaigns", where={**where, "product_sku": sku, "responded": True},
                          estimate_field="order_value_eur", with_why=False)
    if res.get("estimate") is None:
        raise AitoError(f"_estimate order_value_eur returned no estimate for {where['customer_id']} × {sku}: {res}")
    return max(0.0, float(res["estimate"]))


def _offer(product: dict, response_p: float, order_value: float) -> WinbackOffer:
    return WinbackOffer(
        sku=product["sku"], name=product["name"], category=f"{product['pet_type']}/{product['category']}",
        price_eur=round(float(product["price_eur"]), 2), response_p=round(response_p, 3),
        order_value_eur=round(order_value, 2),
        expected_return_eur=round(response_p * order_value - EMAIL_COST_EUR, 2),
    )
