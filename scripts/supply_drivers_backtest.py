"""Do the things that drive demand (the product's state and the season) predict next month's sales range better than "same as last month"? (ADR 0061.)

    uv run python scripts/supply_drivers_backtest.py

Aito `_evaluate` on monthly_sales, predicting `units_bucket`, over seven test months, each trained ONLY on months before it (`{"month": {"$lt": m}}`: a
time split with no future in it). The product's state is read through the link (`product_state.rating_band`...), not as the state's own id, which is
unique to each product-month and carries no evidence. Read-only: it queries the shared instance's master.
"""
import sys
sys.path.insert(0, ".")
from src.aito_client import AitoClient
from src.config import load_config
from src.demand_evaluation import _naive_accuracy
c = AitoClient(load_config())
tests = ["2025-10","2025-11","2025-12","2026-01","2026-02","2026-03","2026-04"]
S = lambda f: f"product_state.{f}"
sets = {
 "bucket+season+category": ("units_last_month_bucket","season","category"),
 "+rating,age":   ("units_last_month_bucket","season","category",S("rating_band"),S("age")),
 "+offer,rival":  ("units_last_month_bucket","season","category",S("rating_band"),S("age"),S("on_offer"),S("rival_launched")),
 "+label,stock,discount": ("units_last_month_bucket","season","category",S("rating_band"),S("age"),S("on_offer"),S("rival_launched"),S("label"),S("stock"),S("discount_band")),
}
print("naive", round(sum(_naive_accuracy(c, m)[0] for m in tests)/len(tests),3))
for name, feats in sets.items():
    accs=[]
    for m in tests:
        try:
            r=c.evaluate(table="monthly_sales", where={f:{"$get":f} for f in feats}, predict_field="units_bucket",
                         train={"month":{"$lt":m}}, test={"month":m})
        except Exception as e:
            print(name, "ERR", str(e)[:200]); break
        accs.append(round(float(r["accuracy"]),3))
    else:
        print(f"{name:26}", accs, "mean", round(sum(accs)/len(accs),3))
