#!/usr/bin/env python3
"""Live smoke of the deployed ecommerce demo: every view a visitor opens, read-only.

    python scripts/live_smoke.py                          # https://ecommerce.aito.ai
    python scripts/live_smoke.py --base http://localhost:8500

Fails when a view errors OR comes back hollow where the data guarantees
content. Board td-20260929184223822327: on 29.9 every route here answered 200,
yet Churn had no drivers, Demand no seasonality, and Evaluation served a stale
snapshot whose headline model read "fail" (pet type 0.06 vs 0.0). A status-code
check sees none of that.

Read-only: every call is a GET. With PUBLIC_DEMO the server writes nothing to
Aito (src/cache.py), and precompute writes happen only from `./do precompute`.
No key is needed: the deployed server uses its own.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

LIVE_BASE = "https://ecommerce.aito.ai"
SLOW_SECONDS = 20.0


@dataclass
class Step:
    name: str
    path: str
    check: Callable[[Any], str]
    params: dict | None = None


def _list(body: dict, key: str, what: str, at_least: int = 1) -> list:
    value = body.get(key)
    assert isinstance(value, list), f"{what}: no `{key}` list in {sorted(body)[:8]}"
    assert len(value) >= at_least, f"{what}: `{key}` has {len(value)} items, expected >= {at_least}"
    return value


def nonempty(*keys: str, what: str) -> Callable[[dict], str]:
    def check(body: dict) -> str:
        return ", ".join(f"{len(_list(body, k, what))} {k}" for k in keys)
    return check


# Models that clear the threshold comfortably on correct data (pet type 0.85 vs
# 0.40, diet 0.65 vs 0.26, segment 0.82 vs 0.46) and would otherwise regress
# silently. return_risk is a DELIBERATE honest failure, so it isn't held to
# "pass"; every model is held to "no error, has a sample".
MUST_PASS = ("pet_type_from_name", "dietary_from_name", "segment_from_product")


def check_evaluation(body: dict) -> str:
    models = _list(body, "models", "evaluation")
    errored = [m.get("id") for m in models if m.get("error")]
    assert not errored, f"evaluation errored for {errored}"
    unsampled = [m.get("id") for m in models if not m.get("n")]
    assert not unsampled, f"evaluation has no sample for {unsampled}"
    by_id = {m.get("id"): m for m in models}
    missing = [m for m in MUST_PASS if m not in by_id]
    assert not missing, f"evaluation lacks {missing}"
    failing = [f"{m} {by_id[m].get('accuracy')} vs {by_id[m].get('base_accuracy')}"
               for m in MUST_PASS if by_id[m].get("verdict") != "pass"]
    assert not failing, f"not passing: {failing}. Stale snapshot? last_run {body.get('last_run')}"
    return f"{len(models)} models, {len(MUST_PASS)} held to pass all pass"


def check_dashboard(body: dict) -> str:
    """Since #37 an unavailable panel is a tile marked available:false, so a
    non-empty list can be all-unavailable: require one real pattern."""
    patterns = _list(body, "top_patterns", "dashboard")
    real = [p for p in patterns if p.get("available", True) is True]
    assert real, f"all {len(patterns)} dashboard patterns are unavailable"
    _list(body, "segments", "dashboard")
    return f"{len(real)}/{len(patterns)} patterns available"


def shape_only(*keys: str, what: str) -> Callable[[dict], str]:
    """For views hidden until their unhide criteria pass (ADR 0027, #38): the
    route must answer without an error in the right shape, but its content
    isn't gated on (demand's seasonality is one row just past its threshold)."""
    def check(body: dict) -> str:
        assert not body.get("error"), f"{what}: {body.get('error')}"
        for key in keys:
            assert isinstance(body.get(key), list), f"{what}: no `{key}` list in {sorted(body)[:8]}"
        return "shape ok (hidden view: content not gated)"
    return check


def check_version(body: dict) -> str:
    # informational: an unpinned build can't say what is live, but that is not a broken view
    sha = (body.get("build") or {}).get("sha")
    return f"build {sha or 'UNPINNED'}, api {body.get('api')}"


STEPS = [
    Step("version", "/api/version", check_version),
    Step("dashboard", "/api/dashboard", check_dashboard),
    Step("evaluation", "/api/evaluation", check_evaluation),
    Step("churn", "/api/churn", nonempty("at_risk", "drivers", what="churn")),
    # hidden views (ADR 0027): shape only, until their unhide criteria pass
    Step("demand", "/api/demand", shape_only("top_movers", "seasonality", what="demand")),
    Step("inventory", "/api/inventory", nonempty("reorder_queue", what="inventory")),
    Step("winback", "/api/winback", shape_only("targets", what="winback")),
    Step("markdown", "/api/markdown", shape_only("proposals", what="markdown")),
    Step("basket-rules", "/api/basket-rules", nonempty("rules", what="basket rules")),
    Step("cart-completion", "/api/cart-completion", shape_only("scenarios", what="cart completion")),
    Step("price", "/api/price", shape_only("fair_bands", "sweet_spots", what="price")),
    Step("product-filling", "/api/product-filling", nonempty("fields", what="product filling")),
    Step("feedback", "/api/feedback", nonempty("fields", what="feedback")),
    Step("smart-search", "/api/smart-search", nonempty("baseline", "predictive", what="smart search"),
         {"q": "food", "customer": "saara"}),
    Step("for-you", "/api/for-you", nonempty("tiles", what="for you"), {"customer": "maija"}),
    Step("bought-together", "/api/bought-together", nonempty("cross_sells", what="bought together"),
         {"anchor": "dog_dryfood"}),
    Step("pattern-explorer", "/api/pattern-explorer", nonempty("patterns", what="pattern explorer"),
         {"anchor": "dog_dryfood"}),
]


def fetch(base: str, step: Step, timeout: float) -> Any:
    url = base + step.path + ("?" + urllib.parse.urlencode(step.params) if step.params else "")
    req = urllib.request.Request(url, headers={"user-agent": "ecommerce-live-smoke"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.load(res)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default=LIVE_BASE)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    print(f"Ecommerce live smoke — {args.base}, {len(STEPS)} views\n")
    failures = []
    for step in STEPS:
        started = time.monotonic()
        try:
            summary = step.check(fetch(args.base, step, args.timeout))
            elapsed = time.monotonic() - started
            print(f"  {'SLOW' if elapsed > SLOW_SECONDS else 'ok  '}  {step.name:<18} {summary}  ({elapsed:.1f}s)")
        except (urllib.error.URLError, TimeoutError, ValueError, AssertionError, KeyError, TypeError) as exc:
            reason = f"{type(exc).__name__}: {exc}"
            failures.append((step.name, reason))
            print(f"  FAIL  {step.name:<18} {reason}  ({time.monotonic() - started:.1f}s)")

    print()
    if failures:
        print(f"{len(failures)} of {len(STEPS)} views FAILED:")
        for name, reason in failures:
            print(f"  {name}: {reason}")
        return 1
    print(f"All {len(STEPS)} views answered with content.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
