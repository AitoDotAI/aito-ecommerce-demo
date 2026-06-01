"""FastAPI application — Predictive E-commerce demo backend (PetNord).

Thin API layer that delegates to Aito. Each endpoint is a direct
window into an Aito capability, not an abstraction over it.

Single-tenant: one Aito DB, one persona. Multi-tenant routing was
intentionally dropped vs. `aito-erp-demo`; see ADR 0001.

Lifecycle:
  - On import we load `Config`, build one `AitoClient`, register it
    with the persistent cache, and ship the app.
  - View services (`*_service.py`) get added under "View routes" as
    each view lands. Build order is in `TASK.md`.
"""

import os

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.aito_client import AitoClient, AitoError
from src import cache, timing
from src.config import load_config
from src.rate_limit import check_rate_limit
from src.overview_service import get_dashboard
from src.search_service import smart_search
from src.recommend_service import get_for_you
from src.bought_together_service import get_bought_together
from src.filling_service import get_filling
from src.eval_service import run_evaluation
from src.analytics_service import get_analytics
from src.pattern_service import get_patterns
from src.feedback_service import get_feedback
from src.churn_service import get_churn
from src.demand_service import get_demand
from src.cart_completion_service import get_cart_completion
from src.inventory_service import get_inventory
from src.markdown_service import get_markdowns
from src.price_service import get_prices, get_price_detail
from src.winback_service import get_winback


config = load_config()
aito = AitoClient(config)

# Register the Aito-backed persistent cache layer. No-op when
# PUBLIC_DEMO=1 so the demo runs against a read-only API key.
if aito.check_connectivity():
    cache.init_persistent_cache(aito)
else:
    # Don't fail startup — the public-demo container may be racing the
    # Aito DNS record, and the health endpoint will surface the state
    # via `aito_connected: false` until Aito is reachable. The first
    # data-bearing request will retry through the in-memory cache miss
    # path and either succeed or surface its own AitoError.
    print(f"  Aito unreachable at {aito._base_url} — continuing in degraded mode.")


def _warm_cache() -> None:
    """Spawn a daemon thread that pre-computes every cacheable
    endpoint via `cache_warmup.warm_all`.

    Daemon thread so the server keeps responding to non-data
    routes (health, schema) while warmup runs in the background.
    The actual warmup logic lives in `src/cache_warmup.py` so the
    `./do reset-data` CLI can call it synchronously after upload
    (the L2 cache then stays warm across uvicorn restarts).
    """
    import threading
    from src.cache_warmup import warm_all
    threading.Thread(
        target=lambda: warm_all(aito, verbose=True),
        daemon=True,
    ).start()


# Kick off the warmup thread. Daemon so the server keeps responding
# to non-data routes (health, schema) while warmup runs.
_warm_cache()


app = FastAPI(
    title="Predictive E-commerce — Aito Demo API",
    version="0.1.0",
)

# CORS: locked to specific origins in PUBLIC_DEMO mode (set via
# CORS_ORIGINS, comma-separated). Permissive default locally so dev
# tooling and curl-from-the-shell still work.
_PUBLIC = os.environ.get("PUBLIC_DEMO", "").lower() in ("1", "true", "yes")
_cors_origins_env = os.environ.get("CORS_ORIGINS", "").strip()
if _PUBLIC and _cors_origins_env:
    _allow_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
else:
    _allow_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    # X-Aito-Calls carries per-request timing data the browser reads to
    # render the latency pill. CORS hides custom response headers from
    # JS unless explicitly exposed.
    expose_headers=["X-Aito-Calls"],
)


@app.middleware("http")
async def aito_timing_middleware(request: Request, call_next):
    """Bind a fresh per-request timing bucket and ship it back as a header.

    Every Aito HTTP call made while serving this request appends to the
    bucket via `timing.record_call`. On the way out we render the bucket
    as `X-Aito-Calls: _predict:28,_relate:142` — the frontend's latency
    pill reads it. When no Aito calls were made (cache hit) the header
    is omitted, so the pill knows to render a "cached" indicator.
    """
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    timing.start_request()
    response = await call_next(request)
    header_value = timing.render_header()
    if header_value:
        response.headers["X-Aito-Calls"] = header_value
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        client_ip = request.client.host if request.client else "unknown"
        allowed, reason = check_rate_limit(client_ip)
        if not allowed:
            messages = {
                "ip":     "Rate limit exceeded for your IP. Try again in a minute.",
                "global": "Demo is at capacity. Please try again in a minute.",
            }
            return JSONResponse(
                status_code=429,
                content={"error": messages.get(reason, "Rate limit exceeded.")},
                headers={"Retry-After": "60"},
            )
    return await call_next(request)


# ── Health & schema ──────────────────────────────────────────────

@app.get("/health")
def liveness():
    """Cheap liveness probe — does not touch Aito.

    Matches the /health convention shared by all aito-demo-server demos so
    the unified container's nginx per-demo health proxies work uniformly.
    For an Aito-connectivity readiness check see /api/health below.
    """
    return {"ok": True}


@app.get("/api/health")
def health():
    """Cheap liveness probe + Aito connectivity check.

    Cached for 60s to avoid hammering Aito's `/schema` from health-check
    pingers. The cache miss path is the only one that actually calls
    Aito — happy path returns from memory.
    """
    cached = cache.get("health")
    if cached:
        return cached
    connected = aito.check_connectivity()
    result = {
        "status": "ok",
        "aito_connected": connected,
        "aito_url": aito._base_url if not _PUBLIC else None,
    }
    cache.set("health", result, ttl=60)
    return result


@app.get("/api/schema")
def schema():
    """Raw Aito schema. Useful in dev for inspecting column types.
    404 in PUBLIC_DEMO mode — don't leak the table layout."""
    if _PUBLIC:
        return JSONResponse(
            status_code=404,
            content={"error": "Not available in public demo mode."},
        )
    try:
        return aito.get_schema()
    except AitoError as exc:
        return {"error": str(exc), "status_code": exc.status_code}


# ── View routes ──────────────────────────────────────────────────
#
# Each view in TASK.md (Dashboard, Smart Search, For You, Bought
# Together, Purchase Analytics, Pattern Explorer, Product Filling,
# Evaluation) lands here as it's built. One service module per view;
# routes stay in this single file so the table-of-contents is
# greppable.

@app.get("/api/dashboard")
def dashboard():
    """Dashboard summary — KPIs + top patterns + segments + recent orders.

    Cached for 10 minutes per `overview_service.get_dashboard`.
    """
    try:
        return get_dashboard(aito).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/smart-search")
def smart_search_endpoint(q: str = "food", customer: str = "saara"):
    """Side-by-side baseline `_search` vs predictive `_recommend`.

    Query: free-text token match on `products.name`.
    Customer: one of `maija` / `olli` / `saara` (the three demo personas).
    """
    try:
        return smart_search(aito, query=q, persona_id=customer).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/for-you")
def for_you_endpoint(customer: str = "maija"):
    """Personalised tile grid via `_recommend` ranked by segment-fit.

    Customer: one of `maija` / `olli` / `saara`.
    """
    try:
        return get_for_you(aito, persona_id=customer).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/bought-together")
def bought_together_endpoint(anchor: str = "dog_dryfood"):
    """Order-level co-occurrence via `_relate` over the denormalised
    `orders.line_categories` Text column. See ADR 0008."""
    try:
        return get_bought_together(aito, anchor_id=anchor).to_dict()
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/product-filling")
def product_filling_endpoint(sku: str | None = None):
    """Multi-field `_predict` for catalog enrichment. See ADR 0009."""
    try:
        return get_filling(aito, sku=sku).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/evaluation")
def evaluation_endpoint():
    """Run four `_evaluate` models in parallel and return pass/fail
    per the +10 pp accuracy-gain threshold. See ADR 0010."""
    try:
        return run_evaluation(aito).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/purchase-analytics")
def purchase_analytics_endpoint():
    """Monthly orders + top products + per-segment KPIs. See ADR 0011."""
    try:
        return get_analytics(aito).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/pattern-explorer")
def pattern_explorer_endpoint(anchor: str = "dog_dryfood"):
    """Ad-hoc `_relate` over `orders.line_categories` — full lift
    band (positive + neutral + protective). See ADR 0011."""
    try:
        return get_patterns(aito, anchor_id=anchor).to_dict()
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/feedback")
def feedback_endpoint(review: str | None = None):
    """Multi-field `_predict` over a review's text — three parallel
    predicts return category, sentiment, and the suggested assignee.
    See ADR 0012."""
    try:
        return get_feedback(aito, review_id=review).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/churn")
def churn_endpoint():
    """KPI strip + at-risk leaderboard (per-customer `_predict
    churned`) + drivers (`_relate` × 3) + honest accuracy
    (`_evaluate`). See ADR 0013."""
    try:
        return get_churn(aito).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/demand")
def demand_endpoint():
    """Per-SKU next-month units forecast + seasonality drivers +
    held-out accuracy. See ADR 0014."""
    try:
        return get_demand(aito).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/inventory")
def inventory_endpoint():
    """KPI strip + reorder queue (critical SKUs with `_predict
    units_sold` next month) + overstock list with tied-capital €.
    See ADR 0015."""
    try:
        return get_inventory(aito).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/winback")
def winback_endpoint():
    """Win-back campaign view — for each churned customer, top-3
    product recommendations + predicted response rate + expected
    revenue. Empirical impact from `winback_campaigns` historical
    table. See ADR 0020."""
    try:
        return get_winback(aito).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/cart-completion")
def cart_completion_endpoint():
    """4 preset checkout scenarios × `_recommend product_sku`
    conditioned on cart's line_categories. See ADR 0019."""
    try:
        return get_cart_completion(aito).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/markdown")
def markdown_endpoint():
    """Markdown decision view — overstock SKUs + proposed discount
    levels driven by Aito's `_estimate units_sold` at multiple price
    points + clearance-revenue math. See ADR 0018."""
    try:
        return get_markdowns(aito).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/price")
def price_endpoint():
    """Per-SKU fair-band stats + sweet-spot `_relate` over
    discount band ↔ category. See ADR 0016."""
    try:
        return get_prices(aito).to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/price/detail")
def price_detail_endpoint(sku: str):
    """Per-SKU detail for the Price scatter chart — historical
    (price, units, profit) pairs + 7-point demand curve via
    parallel `_estimate units_sold` at price adjustments."""
    try:
        detail = get_price_detail(aito, sku)
        if detail is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"sku not found: {sku}"},
            )
        return detail.to_dict()
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


# ── Static files ─────────────────────────────────────────────────
#
# In production, FastAPI serves the Next.js static export from a
# single port (matches `aito-accounting-demo` + `aito-erp-demo`).
# When `frontend/out/` doesn't exist (typical local dev), this is
# a no-op and the Next dev server on 8500 proxies API calls back
# to this backend on 8501 instead.

_frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "out"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
