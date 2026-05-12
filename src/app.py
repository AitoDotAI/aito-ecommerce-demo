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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
