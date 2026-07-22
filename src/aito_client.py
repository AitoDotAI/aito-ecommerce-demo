"""HTTP client for Aito's predictive database API.

Thin wrapper — each method maps directly to an Aito REST endpoint.
No abstraction beyond authentication and error handling. An outside
developer reading this file should see exactly what HTTP calls are
made and what response shapes come back.

Aito API docs: https://aito.ai/docs/api/

Single-tenant: this client is constructed once at startup from
`Config` and shared across every request. Multi-tenant routing was
dropped vs. `aito-erp-demo`; if you need it back, lift it whole from
that repo rather than half-implementing it here.
"""

import time
from typing import Any

import httpx

from src.config import Config
from src import timing


class AitoError(Exception):
    """Raised when an Aito API call fails.

    Includes the HTTP status and response body so the caller has enough
    context to diagnose without a debugger.
    """

    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        self.status_code = status_code
        self.body = body
        super().__init__(message)


class AitoClient:
    """Synchronous client for the Aito REST API."""

    def __init__(self, config: Config) -> None:
        self._base_url = config.aito_api_url
        self._headers = {
            "x-api-key": config.aito_api_key,
            "content-type": "application/json",
        }
        # Pooled `httpx.Client` — keeps the TCP+TLS connection alive
        # across requests. Without this each call pays a ~150 ms TLS
        # handshake (measured: 200-300 ms net vs 57 ms net with the
        # pool warm) which dominates server-side query latency. See
        # docs/notes/aito-perf-findings.md.
        self._client = httpx.Client(headers=self._headers, timeout=90.0)

    def _url(self, path: str) -> str:
        return f"{self._base_url}/api/v1{path}"

    def _request(self, method: str, path: str, json: dict | list | None = None) -> Any:
        """Make an HTTP request to Aito and return the parsed JSON response.

        Per-call timing is recorded onto the per-request timing context
        (when called inside a FastAPI handler) so the browser can render
        a latency pill from the `X-Aito-Calls` response header.

        We prefer Aito's own `x-aitoai-response-time` header (server-side
        processing time, in ms) over the httpx wall-clock, because the
        wall-clock includes server→Aito network round-trip which is not
        what the demo wants to surface as "this is what a query costs".
        We fall back to wall-clock when the header is absent (errors,
        connection failures, mocked responses).

        Raises `AitoError` on non-2xx status or connection failure.
        """
        start = time.perf_counter()
        try:
            # 90 s timeout is set once on the pooled client (see
            # __init__). `_evaluate` against `order_lines` (37 k rows,
            # 200 held-out cases) routinely takes 20-60 s; other
            # endpoints are well under a second.
            response = self._client.request(method, self._url(path), json=json)
        except httpx.HTTPError as exc:
            timing.record_call(path, (time.perf_counter() - start) * 1000)
            raise AitoError(
                f"Aito request failed: {method} {path}: {exc}"
            ) from exc

        aito_ms_header = response.headers.get("x-aitoai-response-time")
        if aito_ms_header:
            try:
                ms = float(aito_ms_header)
            except ValueError:
                ms = (time.perf_counter() - start) * 1000
        else:
            ms = (time.perf_counter() - start) * 1000
        timing.record_call(path, ms)

        if response.status_code >= 400:
            raise AitoError(
                f"Aito returned {response.status_code} for {method} {path}: "
                f"{response.text[:500]}",
                status_code=response.status_code,
                body=response.text,
            )

        return response.json()

    # ── Schema -------------------------------------------------------

    def get_schema(self) -> dict:
        """Fetch the database schema. Returns table definitions."""
        return self._request("GET", "/schema")

    def check_connectivity(self) -> bool:
        """True if the configured Aito instance is reachable + authenticated."""
        try:
            self.get_schema()
            return True
        except AitoError:
            return False

    # ── Query endpoints ---------------------------------------------
    #
    # Each method maps 1:1 to one Aito endpoint. Method signatures
    # mirror the JSON-body keys so the call site reads like the body
    # it sends. Every endpoint's body shape + response shape is
    # documented in `docs/aito-cheatsheet.md`.
    #
    # No method swallows errors or substitutes empty results on
    # failure — they all raise `AitoError`. Silent fallbacks teach
    # the wrong pattern to a reader of this code (CLAUDE.md prime
    # directive #2).

    def predict(
        self,
        table: str,
        where: dict,
        predict_field: str,
        *,
        limit: int = 10,
    ) -> dict:
        """Run a `_predict` query.

        Example:
            client.predict(
                table="products",
                where={"name": "Acana Large Breed Adult", "pet_type": "dog"},
                predict_field="dietary",
            )

        Returns Aito's response with hits like
        ``{"$p": 0.94, "feature": "large-breed", "$why": {...}}``.

        Note: the predicted value comes back in ``feature``, not in
        a key named after the field. Selecting ``$why`` includes the
        per-pattern lift decomposition that powers ``WhyTooltip``.
        """
        body = {
            "from": table,
            "where": where,
            "predict": predict_field,
            "select": [
                "$p",
                "feature",
                {
                    "$why": {
                        "highlight": {
                            # Sentinel tags — frontend splits and renders
                            # without dangerouslySetInnerHTML. Both
                            # positive (lift > 1) AND negative (lift < 1)
                            # sentinels are set so the frontend never has
                            # to parse Aito's default `<font color>` HTML.
                            # See `docs/aito-cheatsheet.md` §Highlight.
                            "posPreTag":  "«",
                            "posPostTag": "»",
                            "negPreTag":  "‹",
                            "negPostTag": "›",
                        }
                    }
                },
            ],
            "limit": limit,
        }
        return self._request("POST", "/_predict", json=body)

    def recommend(
        self,
        table: str,
        where: dict,
        recommend_field: str,
        goal: dict,
        *,
        select: list | None = None,
        based_on: list[str] | None = None,
        limit: int = 8,
    ) -> dict:
        """Run a `_recommend` query — goal-driven ranking.

        For each candidate value of ``recommend_field``, Aito returns
        the probability that ``goal`` is satisfied given ``where``.
        Hits come back ranked by that probability.

        When ``recommend_field`` is a link column, Aito's default
        ``select`` already returns every column of the linked table
        — so the typical caller leaves ``select=None`` and reads
        ``hit["name"]``, ``hit["category"]``, etc. straight off.

        ``based_on`` lets the caller restrict (or skip) the
        prior-feature inference Aito applies on top of the goal
        probability. Field names are *relative to the recommend
        target*, e.g. ``["category", "brand"]`` when recommending
        ``product_sku``. Pass ``based_on=[]`` to skip prior-feature
        inference entirely — useful when the ``where`` clause
        already narrows the candidate pool tightly and you want the
        ranking to come purely from ``P(goal | candidate)``.

        Example (For You):
            client.recommend(
                table="order_lines",
                where={"orders.customer_id": "CUST-00001"},
                recommend_field="product_sku",
                goal={"returned": False},
                limit=8,
            )
        """
        body: dict = {
            "from": table,
            "where": where,
            "recommend": recommend_field,
            "goal": goal,
            "limit": limit,
        }
        if select is not None:
            body["select"] = select
        if based_on is not None:
            body["basedOn"] = based_on
        return self._request("POST", "/_recommend", json=body)

    def relate(
        self,
        table: str,
        where: dict,
        relate_field: str | dict,
        *,
        limit: int = 20,
    ) -> dict:
        """Run a `_relate` query — discover statistical co-occurrence.

        Example (Bought Together):
            client.relate(
                table="order_lines",
                where={"category": "dental-treats"},
                relate_field={
                    "$context": {"orders.order_lines.{category}": True}
                },
            )

        Hits include lift / fs (frequency stats) / ps (probability
        stats) so the UI can quote the actual multiplicative effect.
        """
        body: dict = {
            "from": table,
            "where": where,
            "relate": relate_field,
            "limit": limit,
        }
        return self._request("POST", "/_relate", json=body)

    def search(
        self,
        table: str,
        *,
        where: dict | None = None,
        order_by: str | dict | list | None = None,
        limit: int = 10,
        offset: int = 0,
        select: list | None = None,
    ) -> dict:
        """Run a `_search` query — retrieve matching rows.

        Smart Search uses this with a ``where`` that mixes free-text
        token matching on ``products.name`` and the customer's
        segment context.

        Example (Smart Search re-ranked for a large-breed dog owner):
            client.search(
                table="products",
                where={
                    "name": "food",
                    "$context": {
                        "order_lines.{customer_segment}": "dog_owner",
                        "order_lines.{customer_pet_size}": "large",
                    },
                },
                limit=10,
            )
        """
        body: dict = {"from": table, "limit": limit, "offset": offset}
        if where is not None:
            body["where"] = where
        if order_by is not None:
            body["orderBy"] = order_by
        if select is not None:
            body["select"] = select
        return self._request("POST", "/_search", json=body)

    def match(
        self,
        table: str,
        where: dict,
        match_field: str,
        *,
        select: list | None = None,
        limit: int = 10,
    ) -> dict:
        """Run a `_match` query — find rows where ``match_field`` is
        statistically likely given ``where``.

        Distinct from ``_search``: ``_match`` ranks by the *match
        score* (Aito's belief that this row is what the query is
        looking for), not by the raw token-overlap score that
        ``_search`` uses. Use it when the query is "find similar"
        rather than "find matching tokens".
        """
        body: dict = {
            "from": table,
            "where": where,
            "match": match_field,
            "limit": limit,
        }
        if select is not None:
            body["select"] = select
        return self._request("POST", "/_match", json=body)

    def estimate(
        self,
        table: str,
        where: dict,
        estimate_field: str,
        *,
        model: str | None = None,
        with_why: bool = True,
    ) -> dict:
        """Run an `_estimate` query — expected-value regression.

        Where `_predict` returns ranked discrete hits with `$p`,
        `_estimate` returns the **expected value** of a numeric
        field given the `where` context. Natural fit for continuous
        regression (units sold, price, revenue) — `_predict` on
        Int columns picks one specific integer; `_estimate` returns
        the mean.

        K-NN under the hood by default. Set ``model="regression"``
        to use a linear-regression model with cleaner per-field
        contribution explanations in the response's `why` tree.

        Example (Demand Forecast):
            client.estimate(
                table="monthly_sales",
                where={"product_sku": "SKU-PT-0042",
                       "month": "2026-05", "season": "spring"},
                estimate_field="units_sold",
            )
            # → {"estimate": 3.76, "why": {...weightedAverage tree...}}

        Returns ``{"estimate": float, "why": {...}}`` when
        ``with_why=True``; just ``{"estimate": float}`` otherwise.
        Setting ``with_why=False`` is cheaper — Aito skips the
        neighbor / coefficient computation.
        """
        body: dict = {
            "from": table,
            "where": where,
            "estimate": estimate_field,
            "select": ["estimate", "why"] if with_why else ["estimate"],
        }
        if model is not None:
            body["model"] = model
        return self._request("POST", "/_estimate", json=body)

    def aggregate(
        self,
        table: str,
        where: dict | None,
        aggregate_fields: list[str],
    ) -> dict:
        """Run an `_aggregate` query — server-side stats per column.

        Each entry in ``aggregate_fields`` is ``"<column>.<stat>"``
        where stat is one of ``$mean``, ``$min``, ``$max``,
        ``$variance``, ``$standardDeviation``. Aito computes them
        in one pass — much cheaper than fetching all rows and
        aggregating client-side.

        Example (Price Intelligence fair band):
            client.aggregate(
                table="price_history",
                where={"product_sku": "SKU-PT-0001"},
                aggregate_fields=[
                    "price_eur.$mean", "price_eur.$min",
                    "price_eur.$max", "price_eur.$standardDeviation",
                ],
            )
            # Response keys mirror the requested field spec exactly:
            # → {"price_eur.$mean": 5.92, "price_eur.$min": 4.48,
            #    "price_eur.$max": 6.61,
            #    "price_eur.$mean.samples": 19,
            #    "price_eur.$mean.standardDeviation": 0.70, ...}
        """
        body: dict = {
            "from": table,
            "aggregate": aggregate_fields,
        }
        if where is not None:
            body["where"] = where
        return self._request("POST", "/_aggregate", json=body)

    def batch(self, queries: list[dict]) -> list:
        """Run several queries in one HTTP request via `_batch`.

        ``queries`` is a list of query bodies — the same shapes the
        single-endpoint methods send, minus the endpoint routing
        (``from`` / ``where`` / ``search`` / ``predict`` / ``recommend``
        / ``relate`` / ``get`` / ``limit`` / …). Aito runs them in order
        and returns a list of results in the same order.

        Use it to collapse a sequential fan-out of independent reads into
        one round-trip. The win is network latency, not server time: on
        the shared instance a small query is ~2 ms of work but ~100 ms on
        the wire, so N sequential reads otherwise cost N × RTT.

        Note: `_aggregate` is a *separate* endpoint — its ``aggregate``
        field is not a valid batch item (Aito 400s it). Keep aggregates
        as their own `aggregate()` calls; batch the plain reads.

        Example (five per-segment customer counts in one call):
            client.batch([
                {"from": "customers", "where": {"segment": s}, "limit": 0}
                for s in segments
            ])
            # → [{"total": 1263}, {"total": 894}, ...]
        """
        return self._request("POST", "/_batch", json=queries)

    def evaluate(
        self,
        table: str,
        where: dict,
        predict_field: str,
        *,
        test_limit: int = 200,
        test_where: dict | None = None,
    ) -> dict:
        """Run an `_evaluate` query — accuracy on a held-out test set.

        Aito requires a `testSource` describing which rows to hold
        out. Each row from `testSource` is then evaluated against
        the `evaluate` block: the target field is hidden, predicted
        from the `where` (which typically reads other fields off
        the held-out row via `$get`), and compared to ground truth.

        Used for the Evaluation view: per-model accuracy +
        baseline accuracy + accuracy_gain. Returns
        ``{"accuracy": float, "baseAccuracy": float, "n": int, ...}``.
        """
        test_source: dict = {"from": table, "limit": test_limit}
        if test_where is not None:
            test_source["where"] = test_where
        body = {
            "testSource": test_source,
            "evaluate": {
                "from": table,
                "where": where,
                "predict": predict_field,
            },
            "select": ["accuracy", "baseAccuracy", "n"],
        }
        return self._request("POST", "/_evaluate", json=body)
