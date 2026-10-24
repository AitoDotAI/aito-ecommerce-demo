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

from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.aito_client import AitoClient, AitoError
from src.aito_client import WRITES_ANY, WRITES_ENVS, WRITES_NONE
from src.demo_mode import ENV_HEADER, DemoClients, requested_sandbox
from src.lever_routes import router as lever_router
from src.sandbox_config import load_sandbox_setting
from src.sandbox_envs import SandboxBranches, SandboxEnvError
from src.sandbox_warmup import warm_resumed
from src.shop_history import NEXT_MONTH
from src import cache, timing, precompute_store
from src.data_release_gate import DataReleaseGate, release_gate_middleware
from src.release_file import load_release, read_counts
from src.build_info import build_info
from src.config import load_config
from src.rate_limit import check_rate_limit
from src.overview_headlines import owner_headlines
from src.overview_service import get_overview
from src.search_service import smart_search
from src.recommend_service import get_for_you
from src.evidence import result_file as evidence_file
from src.filling_service import get_filling
from src.product_service import DEFAULT_SKU, get_product_view, product_view_payload
from src.shop_grid import get_shop_grid
from src.shop_personas import SHOPPERS, UnknownShopperError
from src.shop_product import get_product_drawer
from src.shop_search import search_shop
from src.shop_suggestions import get_suggestions
from src.basket_pairs import get_basket_section
from src.search_words import get_search_words_section
from src.shop_analytics_service import get_funnel_section, get_who_section
from src.review_triage_service import get_review_triage
from src.lookup_errors import ProductNotOnSaleError, UnknownPersonaError, UnknownProductError, UnknownReviewError
from src.demand_forecast import LATEST_MONTH
from src.demand_service import get_demand
from src.retention_service import get_retention
from src.supply_service import get_supply
from src.price_curve import get_price_curve
from src.price_what_if import get_price_what_if
from src.uci_bought_together import bought_together
from src.uci_buyers import pick_buyers
from src.uci_products import UnknownStockCodeError
from src.uci_reorder_service import UnknownBuyerError, draft_order


config = load_config()
# The levers' sandbox database (ADR 0043). While one is configured,
# PetNord's database is read through a read-only client, the sandbox
# database's master (the template) only creates and deletes branches, and
# data is written only in a `tmp-` branch (src/sandbox_envs.py).
sandbox_setting = load_sandbox_setting(config)
petnord_writes = WRITES_NONE if sandbox_setting.config else WRITES_ANY
aito = AitoClient(config, writes=petnord_writes)
sandbox_template = AitoClient(sandbox_setting.config, writes=WRITES_ENVS) if sandbox_setting.config else None
sandbox_branches = SandboxBranches(sandbox_template, on_resume=warm_resumed) if sandbox_template else None
demo_clients = DemoClients(petnord=aito, branches=sandbox_branches)
if sandbox_template is None:
    print(f"  Sandbox mode off: {sandbox_setting.off_reason}.")
else:
    print(f"  Sandboxes on: branches of {sandbox_setting.database}; PetNord's database is read-only.")
# Business reorders (ADR 0034) reads real data, UCI Online Retail II, from
# its own env on the same instance. The pet shop's client stays on its env.
uci_aito = AitoClient(replace(config, aito_env="uci"), writes=petnord_writes)

# Register the Aito-backed persistent cache layer. No-op when
# PUBLIC_DEMO=1 so the demo runs against a read-only API key.
if aito.check_connectivity():
    cache.init_persistent_cache(aito)
    # Register the read-only precompute-and-serve store for the seven
    # precomputed views — the six heavy endpoints plus the dashboard
    # landing page (ADR 0024). Reads only — populated by `./do precompute`,
    # never written at request time.
    precompute_store.init(aito)
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


def _drop_memory_caches() -> None:
    """Forget every answer held in this process. The Aito-side tables
    are left alone: `./do clear-cache` clears those during a cutover."""
    cache.clear()
    precompute_store.invalidate()


# The app waits for its data (ADR 0035): data routes answer 503 until
# the env the app reads matches `data/release-env.json`, and the caches
# are warmed only then. A malformed release file stops the startup here.
release = load_release()
# On the release env itself, the snapshots its release filed for master are its own.
precompute_store.read_release_snapshots(precompute_store.release_snapshot_namespace(config, release.env))
release_gate = DataReleaseGate(
    release,
    read_counts=lambda: read_counts(aito),
    on_ready=_warm_cache,
    on_mismatch=_drop_memory_caches,
)
release_gate.start()

# The sandbox template's gate: ready once `./do sandbox-template-load` has
# loaded the release. A request that names a sandbox branch is gated by it.
sandbox_gate = None
if sandbox_template is not None:
    sandbox_gate = DataReleaseGate(load_release(), read_counts=lambda: read_counts(sandbox_template),
                                   on_ready=lambda: None, on_mismatch=lambda: None)
    sandbox_gate.start(name="sandbox-release-gate")
    # Branches older than three hours are deleted at start-up, then every 10 minutes.
    import threading
    threading.Thread(target=sandbox_branches.reap_forever, name="sandbox-reaper", daemon=True).start()


def _sandbox_gate_for(request: Request) -> DataReleaseGate | None:
    """The template's gate for a request that names a sandbox."""
    if sandbox_gate is None:
        return None
    try:
        named = requested_sandbox(request)
    except SandboxEnvError:
        return None    # the route answers the 400
    return sandbox_gate if named or request.url.path.startswith("/api/levers/") else None


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
    allow_headers=["Content-Type", ENV_HEADER, "X-Admin-Token"],
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


# 503 on data routes until the data matches the release (ADR 0035).
app.middleware("http")(release_gate_middleware(release_gate, _sandbox_gate_for))
app.state.demo_clients = demo_clients


@app.exception_handler(SandboxEnvError)
async def sandbox_env_error(request: Request, exc: SandboxEnvError):
    """A sandbox name that isn't a live branch: 400, never PetNord's data."""
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.exception_handler(AitoError)
async def uncaught_aito_error(request: Request, exc: AitoError):
    """An Aito failure no route mapped itself, e.g. reading the sandbox's
    env list to check a `?db=` name: 502, as the routes answer it."""
    return JSONResponse(status_code=502, content={"error": str(exc), "status_code": exc.status_code})


app.state.sandbox_gate = sandbox_gate
app.state.admin_token = sandbox_setting.admin_token
app.include_router(lever_router)


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


@app.get("/version")
@app.get("/api/version")
def version():
    """What is this process, and what is it talking to?

    Mirrors Aito's own `GET /version`, so asking a demo and asking the
    database it runs on are the same gesture. Cheap and Aito-free, like
    /health — the answer must still arrive when Aito does not.

    It exists because "which build is live?" has twice been answerable
    only by inference. Both times the deployed demo served behaviour
    that was in no git branch, and both times it was caught by noticing
    impossible output in the UI rather than by asking. `api` answers the
    companion question — which engine and env produced a result — which
    is the first thing worth knowing when a number looks wrong.

    Not gated by PUBLIC_DEMO: a commit id is not a secret, and a build
    that will not say what it is cannot be checked by anyone.
    """
    info = build_info()
    return {
        "build": info,
        "api": aito._config.api_namespace,
        # Say it plainly rather than making a reader infer it from a
        # null sha: on a deployment this means BUILD_SHA was not set at
        # build time, so provenance is unverifiable.
        "pinned": info.get("source") == "BUILD_SHA",
        # Whether pages open in presentation mode (DEMO_MODE=1); `?demo=` overrides per tab.
        "demo_mode": config.demo_mode,
    }


@app.get("/api/health")
def health():
    """Cheap liveness probe + Aito connectivity check.

    Cached for 60s to avoid hammering Aito's `/schema` from health-check
    pingers. The cache miss path is the only one that actually calls
    Aito — happy path returns from memory.
    """
    cached = cache.get("health")
    if cached:
        return {**cached, "data_release": release_gate.status()}
    connected = aito.check_connectivity()
    result = {
        "status": "ok",
        "aito_connected": connected,
        "aito_url": aito._base_url if not _PUBLIC else None,
        # Provenance, deliberately NOT hidden in PUBLIC_DEMO: a commit
        # id is not a secret, and being able to ask the deployed demo
        # which commit it runs is the whole point (see src/build_info).
        "build": build_info(),
        # Which backend answers — v1@master / v2@v2. Same reason: when
        # results look wrong, the first question is which engine and env
        # produced them.
        "api": aito._config.api_namespace,
    }
    cache.set("health", result, ttl=60)
    # Outside the 60 s cache: a cutover polls this to see the data arrive.
    return {**result, "data_release": release_gate.status()}


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

def _view_data(name: str) -> dict | None:
    """What a heavy view serves, without computing it: its snapshot, else its
    live answer once a visit to the view has cached it (`_precomputed_view`),
    else None."""
    entry = precompute_store.get(name)
    if isinstance(entry, dict) and "data" in entry:
        return entry["data"]
    return cache.get(f"{name}:view")


@app.get("/api/overview")
def overview_endpoint():
    """Overview (ADR 0041): the shop's last 12 months, best sellers,
    households, and one headline per owner view. The payload is
    precomputed; the Supply and Retention headlines read what those views
    serve, so each headline matches the view it links to."""
    try:
        overview = precompute_store.serve("overview", lambda: get_overview(aito))
        return {**overview, "headlines": owner_headlines(overview, _view_data)}
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
    except UnknownPersonaError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/for-you")
def for_you_endpoint(customer: str = "maija"):
    """Personalised tile grid: `_recommend` with the customer as context.

    Customer: one of `maija` / `olli` / `saara`.
    """
    try:
        return get_for_you(aito, persona_id=customer).to_dict()
    except UnknownPersonaError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
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
    except UnknownProductError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/evidence/{entry}")
def evidence_endpoint(entry: str):
    """An Evidence page's committed result file (ADR 0037 §2): the page
    never runs a benchmark live. `./do evidence <entry>` rewrites it."""
    try:
        return evidence_file.served(entry)
    except KeyError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc.args[0])})


# ── Shop (ADR 0031) ─────────────────────────────────────────────────

MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


def _shop(compute):
    """The Shop endpoints' shared error mapping: an unknown shopper or
    product is a 404 with its message, an Aito failure a 502."""
    try:
        return compute().to_dict()
    except (UnknownShopperError, UnknownProductError) as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except ValueError as exc:    # a malformed request, e.g. a product twice in the cart
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc), "status_code": exc.status_code})


def _cart_skus(cart: str) -> list[str]:
    return [s for s in cart.split(",") if s]


def _reader(request: Request) -> AitoClient:
    """PetNord's database, or the sandbox branch the request names (src/demo_mode.py).
    Raises SandboxEnvError (a ValueError: 400) for a name that isn't a live branch."""
    return demo_clients.reader(request)


def _shop_reader(request: Request, month: str) -> AitoClient:
    """The Shop's reader. The sandbox's month, 2026-05, exists only in a sandbox."""
    reader = _reader(request)
    if month == NEXT_MONTH and reader is aito:
        raise ValueError(f"{NEXT_MONTH} is the sandbox's month: open a sandbox to see it")
    return reader


@app.get("/api/shop/shoppers")
def shop_shoppers_endpoint():
    """The shoppers the Shop view lets you be, each with a story."""
    return {"shoppers": [s.to_dict() for s in SHOPPERS]}


@app.get("/api/shop/grid")
def shop_grid_endpoint(request: Request, shopper: str, month: str = Query(pattern=MONTH), cart: str = ""):
    """What to show this shopper now: `_recommend` with profile, month and
    cart as context, the household rule as a filter, recency re-asked. In
    sandbox mode for 2026-05, re-scored by the levers' states (ADR 0043)."""
    return _shop(lambda: get_shop_grid(_shop_reader(request, month), shopper, month, _cart_skus(cart),
                                       rescored=month == NEXT_MONTH))


@app.get("/api/shop/search")
def shop_search_endpoint(request: Request, q: str, shopper: str, month: str = Query(pattern=MONTH), cart: str = ""):
    """The products whose name the query matches, ranked as the grid ranks them."""
    return _shop(lambda: search_shop(_shop_reader(request, month), shopper, month, _cart_skus(cart), q))


@app.get("/api/shop/product")
def shop_product_endpoint(request: Request, sku: str, shopper: str, month: str = Query(pattern=MONTH), cart: str = ""):
    """A product's drawer: details, alternatives for this shopper, often in
    the same basket, and in your orders before `month`."""
    return _shop(lambda: get_product_drawer(_shop_reader(request, month), sku, shopper, month, _cart_skus(cart)))


@app.get("/api/shop/suggestions")
def shop_suggestions_endpoint(request: Request, shopper: str, month: str = Query(pattern=MONTH), cart: str = ""):
    """The usual basket, and what's next for the shopper's pet, as of `month` and with `cart`."""
    return _shop(lambda: get_suggestions(_shop_reader(request, month), shopper, month, _cart_skus(cart)))


@app.get("/api/product")
def product_endpoint(request: Request, sku: str | None = None, month: str = Query(LATEST_MONTH, pattern=MONTH)):
    """The Product view (ADR 0041): one product in one month, the discount
    decision, the discount and price what-ifs, its history and its buyers.
    In sandbox mode it reads the sandbox, uncached: a lever changes it."""
    try:
        reader = _reader(request)
        if reader is not aito:
            return get_product_view(reader, sku or DEFAULT_SKU, month).to_dict()
        return product_view_payload(aito, sku, month)
    except (UnknownProductError, ProductNotOnSaleError) as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/product/price-curve")
def product_price_curve_endpoint(request: Request, sku: str):
    """Next month's units at seven prices (`_estimate units_sold`, regression
    model), beside the product's own months. See ADR 0029."""
    try:
        return get_price_curve(_reader(request), sku).to_dict()
    except UnknownProductError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/product/price-what-if")
def product_price_what_if_endpoint(request: Request, sku: str, price: float = Query(gt=0, allow_inf_nan=False)):
    """Units, revenue and profit next month at `price`, with the factors
    behind the estimate (regression `_estimate`). See ADR 0029."""
    try:
        return get_price_what_if(_reader(request), sku, price).to_dict()
    except UnknownProductError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


def _shop_analytics_section(cache_key: str, load):
    """Shop analytics sections share their caching and error mapping.

    Cached for 30 minutes, as Product Insights is: a section takes 1.5–3 s
    alone but 4–8 s when the page asks all four at once (measured on
    `shoppers`, 2026-10-13). A bad `kpi` or `who` in a link is a 400, an
    unexpected Aito answer a 502."""
    try:
        return cache.get_or_compute(f"shop-analytics:{cache_key}", lambda: load().to_dict(), ttl=1800)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/shop-analytics/funnel")
def shop_analytics_funnel_endpoint(kpi: str = "purchased"):
    """What goes with a purchase (or click): parallel `_relate`s on
    impressions. See ADR 0031."""
    return _shop_analytics_section(f"funnel:{kpi}", lambda: get_funnel_section(aito, kpi=kpi))


@app.get("/api/shop-analytics/who")
def shop_analytics_who_endpoint(who: str = "summer"):
    """Which categories a season, segment or diet rule buys more or less."""
    return _shop_analytics_section(f"who:{who}", lambda: get_who_section(aito, who=who))


@app.get("/api/shop-analytics/baskets")
def shop_analytics_baskets_endpoint():
    """Category pairs bought together more or less often than chance."""
    return _shop_analytics_section("baskets", lambda: get_basket_section(aito))


@app.get("/api/shop-analytics/search-words")
def shop_analytics_search_words_endpoint():
    """Search words that convert above or below the average search."""
    return _shop_analytics_section("search-words", lambda: get_search_words_section(aito))


@app.get("/api/review-triage")
def review_triage_endpoint(review: str | None = None):
    """Route a review: three parallel `_predict`s over its text return the
    category, sentiment and suggested assignee. See ADR 0012."""
    try:
        return get_review_triage(aito, review_id=review).to_dict()
    except UnknownReviewError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


def _precomputed_view(name: str, compute):
    """A heavy view: its precompute snapshot, else computed live and cached
    for 30 minutes (ADR 0024). An Aito failure is a 502."""
    try:
        return precompute_store.serve(
            name, lambda: cache.get_or_compute(f"{name}:view", lambda: compute().to_dict(), ttl=1800))
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


@app.get("/api/supply")
def supply_endpoint():
    """What to reorder, what is overstocked and what markdown clears it:
    `_estimate units_sold` per SKU, at several prices for the overstock,
    with each SKU's fair price band. See ADR 0041."""
    return _precomputed_view("supply", lambda: get_supply(aito))


@app.get("/api/retention")
def retention_endpoint():
    """Who is about to leave, why, and the offer that brings them back:
    `_predict churned_in_3_months` per active customer, `_relate` drivers,
    and a win-back email per listed customer. See ADR 0041."""
    return _precomputed_view("retention", lambda: get_retention(aito))


@app.get("/api/demand")
def demand_endpoint():
    """Per-SKU next-month units forecast + seasonality drivers +
    held-out accuracy. See ADR 0014. Supply shows the forecast; the
    seasonality moves to Patterns (ADR 0041)."""
    try:
        return precompute_store.serve("demand", lambda: get_demand(aito).to_dict())
    except AitoError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "status_code": exc.status_code},
        )


# ── Business reorders, on UCI Online Retail II (ADR 0034) ──────────


def _uci(compute):
    """An unknown customer or StockCode is a 404 with its message, an
    Aito failure a 502. Not cached: the cache is scoped to the pet shop's env."""
    try:
        return compute()
    except (UnknownBuyerError, UnknownStockCodeError) as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except AitoError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc), "status_code": exc.status_code})


@app.get("/api/uci/buyers")
def uci_buyers_endpoint():
    """The buyers the page offers, chosen by a fixed rule (src/uci_buyers.py)."""
    return {"buyers": [b.to_dict() for b in pick_buyers()]}


@app.get("/api/uci/draft")
def uci_draft_endpoint(customer: str):
    """Aito's draft of the buyer's next order, against what they ordered next."""
    return _uci(lambda: draft_order(uci_aito, customer).to_dict())


@app.get("/api/uci/bought-together")
def uci_bought_together_endpoint(code: str):
    """What is ordered with a StockCode: `_relate` over `baskets`."""
    return _uci(lambda: bought_together(uci_aito, code).to_dict())


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
