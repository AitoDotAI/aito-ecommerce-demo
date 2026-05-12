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

    def _url(self, path: str) -> str:
        return f"{self._base_url}/api/v1{path}"

    def _request(self, method: str, path: str, json: dict | None = None) -> Any:
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
            # 90 s window — `_evaluate` against `order_lines` (37 k rows,
            # 200 held-out cases) routinely takes 20-60 s. Other endpoints
            # are well under a second; the wider timeout costs nothing on
            # the fast paths.
            response = httpx.request(
                method,
                self._url(path),
                headers=self._headers,
                json=json,
                timeout=90.0,
            )
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
