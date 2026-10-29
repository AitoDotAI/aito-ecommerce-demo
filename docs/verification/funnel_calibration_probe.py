"""How far are the Funnel's estimates from what happened? (ADR 0050)

Run from the repo root, read-only:

    AITO_ENV=master PYTHONPATH=. uv run python docs/verification/funnel_calibration_probe.py

For 70 random products it compares April 2026's counted showings, clicks,
purchases and units with the funnel's estimate, the `_estimate units_index`
route and the product's mean of earlier months, and checks `_predict
clicked|purchased` calibration by probability decile. The report that
quotes its output is `funnel-calibration.md`.
"""

import collections
import random
import statistics

from src.aito_client import AitoClient
from src.config import load_config
from src.product_funnel import get_product_funnel
from src.product_kpi import get_product_kpis

MONTH = "2026-04"
SAMPLE = 70
SEED = 11

client = AitoClient(load_config())
print(client._base_url, "env", client._config.aito_env)

sales = client.search("monthly_sales", where={"month": MONTH}, limit=1000)["hits"]
random.Random(SEED).shuffle(sales)
rows = []
for sale in sales[:SAMPLE]:
    sku = sale["product_sku"]
    funnel = get_product_funnel(client, sku)
    kpis = get_product_kpis(client, sku, MONTH, {})
    clicked, purchased = kpis.estimates["clicked"], kpis.estimates["purchased"]
    rows.append(dict(
        sku=sku, est=funnel.now, act=funnel.actual, chk=funnel.check_units, mean_u=funnel.mean_units,
        p_c=clicked.p, p_p=purchased.p, shown=clicked.product_shown,
        hc=clicked.product_hits, hp=purchased.product_hits))
print(len(rows), "products")


def total(f):
    return sum(f(r) for r in rows)


print("April sums, actual vs funnel estimate:")
for name, est, act in (
        ("impressions", lambda r: r["est"].impressions, lambda r: r["act"].impressions),
        ("clicks", lambda r: r["est"].clicks, lambda r: r["act"].clicks),
        ("purchases", lambda r: r["est"].purchases, lambda r: r["act"].purchases),
        ("units", lambda r: r["est"].units, lambda r: r["act"].units)):
    print(f"  {name:12s} est {total(est):8.1f}  actual {total(act):8.1f}  ratio {total(est) / total(act):.2f}")

have = [r for r in rows if r["chk"] is not None]


def mean_abs_error(f):
    return statistics.mean(abs(f(r)) for r in have)


print("units, mean absolute error per product:",
      "_estimate route", round(mean_abs_error(lambda r: r["chk"] - r["act"].units), 2),
      "funnel", round(mean_abs_error(lambda r: r["est"].units - r["act"].units), 2),
      "mean of earlier months", round(mean_abs_error(lambda r: r["mean_u"] - r["act"].units), 2))

print("raw _predict calibration (ranked impressions, product ever):")
for kpi, p, hits in (("clicked", "p_c", "hc"), ("purchased", "p_p", "hp")):
    expected, observed = total(lambda r: r[p] * r["shown"]), total(lambda r: r[hits])
    print(f"  {kpi}: sum p x shown {expected:.1f}  observed {observed}  ratio {expected / observed:.2f}")
    deciles = collections.defaultdict(lambda: [0.0, 0, 0])
    for r in rows:
        d = min(int(r[p] * 10), 6)
        deciles[d][0] += r[p] * r["shown"]
        deciles[d][1] += r[hits]
        deciles[d][2] += 1
    print("   p-decile: (expected, observed, products)",
          {d / 10: (round(v[0], 1), v[1], v[2]) for d, v in sorted(deciles.items())})
