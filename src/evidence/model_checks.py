"""`./do evidence model-checks`: held-out accuracy of the demo's prediction models.

Writes `data/evidence/model-checks.json`, which the Model checks page
renders (ADR 0037 §2: a page never runs a benchmark live). Three parts,
each against the baseline that makes its number mean something:

- **Catalogue and returns** (ADR 0010, `eval_service`): three `_evaluate`
  models against always guessing the most common value; pass at ≥ 10 pp.
  Return Risk is meant to fail, and the page shows it.
- **Churn** (ADR 0013): `_evaluate churned_in_3_months` on the customer-month
  panel, with the features the Retention view's `_predict` uses, against
  always guessing "stays".
- **Demand** (ADR 0014, `demand_evaluation`): a time split on the last
  month, against "same range as last month" (naive) and the most common range.

These used to sit inside the Churn and Demand views. ADR 0041 moved them
here: the 360° views carry no accuracy numbers. Reads only.
"""

from __future__ import annotations

import sys
from dataclasses import asdict

from src.aito_client import AitoClient, AitoError
from src.config import load_config
from src.demand_evaluation import evaluate_demand
from src.demand_forecast import LATEST_MONTH
from src.eval_service import PASS_THRESHOLD_PP, run_evaluation
from src.evidence import result_file
from src.evidence.wording import accuracy_interval, difference_sentence, unpaired_difference

# The Retention view's `_predict churned_in_3_months` features (ADR 0013).
CHURN_FEATURES = ("pets", "region", "tenure_months_at_month", "visits", "purchases", "spent_eur")
CHURN_TEST_ROWS = 300


def evaluate_churn(client: AitoClient) -> dict:
    """One `_evaluate` over the panel; `$get` reads each held-out row's own value."""
    where = {f: {"$get": f} for f in CHURN_FEATURES}
    res = client.evaluate(table="customer_months", where=where, predict_field="churned_in_3_months",
                          test_n=CHURN_TEST_ROWS)
    missing = [k for k in ("accuracy", "baseAccuracy", "n") if k not in res]
    if missing:
        raise AitoError(f"_evaluate churned_in_3_months answered without {missing}: {str(res)[:300]}")
    accuracy, base = float(res["accuracy"]), float(res["baseAccuracy"])
    return {
        "label": "Churn in the next 3 months",
        "table": "customer_months",
        "predict": "churned_in_3_months",
        "features": list(CHURN_FEATURES),
        "accuracy": accuracy,
        "base_accuracy": base,
        "gain_pp": (accuracy - base) * 100,
        "n": int(res["n"]),
        "method": f"{CHURN_TEST_ROWS} customer-months held out at random by Aito's `_evaluate`; "
                  "the baseline always guesses the most common answer (stays).",
    }


def evaluate_demand_model(client: AitoClient) -> dict:
    e = evaluate_demand(client, LATEST_MONTH)
    return {"label": "Next month's sales range", "table": "monthly_sales", "predict": "units_bucket",
            **asdict(e), "test_month": LATEST_MONTH,
            # Said for this page: Supply's unit forecast is an `_estimate`, which `_evaluate` can't score yet.
            "method": f"Aito predicting each product's sales range (0, 1, 2-3, 4-7, 8-15, 16-31, 32+) in "
                      f"{LATEST_MONTH} from last month's range and the product, trained on every earlier month. "
                      "It scores the range, not Supply's unit forecast, which `_evaluate` can't score yet."}


def with_intervals(accuracy: float, n: int, comparisons: dict[str, float], label: str) -> dict:
    """The accuracy's interval, and each `{baseline name: its accuracy}` as a worded difference."""
    low, high = accuracy_interval(accuracy, n)
    worded = []
    for name, base in comparisons.items():
        d, d_low, d_high = unpaired_difference(accuracy, base, n)
        shown = f"{d * 100:+.1f} pp [{d_low * 100:+.1f}, {d_high * 100:+.1f}]"
        worded.append({"baseline": name, "difference": d, "low": d_low, "high": d_high,
                       "sentence": difference_sentence(label, name, d, d_low, d_high, shown)})
    return {"accuracy_low": low, "accuracy_high": high, "comparisons": worded}


def main() -> int:
    client = AitoClient(load_config())
    catalogue = run_evaluation(client).to_dict()
    errored = [m["id"] for m in catalogue["models"] if m["error"] is not None]
    if errored:
        raise AitoError(f"_evaluate failed for {errored}: a result file must not hold an errored model")
    result = {
        "entry": "model-checks",
        "data": "Synthetic",
        "adr": "ADR 0010, 0013, 0014",
        "script": "src/evidence/model_checks.py",
        "run": result_file.run_info(client, "./do evidence model-checks"),
        "threshold_pp": PASS_THRESHOLD_PP,
        "models": [{**m, **with_intervals(m["accuracy"], m["n"], {"the most common value": m["base_accuracy"]},
                                          m["label"])} for m in catalogue["models"]],
    }
    churn, demand = evaluate_churn(client), evaluate_demand_model(client)
    result["churn"] = {**churn, **with_intervals(churn["accuracy"], churn["n"],
                                                 {"always “stays”": churn["base_accuracy"]}, "Aito")}
    result["demand"] = {**demand, **with_intervals(demand["accuracy"], demand["n"],
                                                   {"naive (last month's range)": demand["naive_accuracy"],
                                                    "the most common range": demand["base_accuracy"]}, "Aito")}
    path = result_file.write("model-checks", result)
    print(f"Wrote {path}")
    for m in result["models"]:
        print(f"  {m['label']}: {m['accuracy']:.3f} vs {m['base_accuracy']:.3f} ({m['verdict']})")
    for part in ("churn", "demand"):
        for c in result[part]["comparisons"]:
            print(f"  {part}: {c['sentence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
