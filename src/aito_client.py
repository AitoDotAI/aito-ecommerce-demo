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
            response = httpx.request(
                method,
                self._url(path),
                headers=self._headers,
                json=json,
                timeout=30.0,
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

    # ── Query endpoints (filled in as views land) -------------------
    #
    # Each new endpoint method must:
    #   1. Be documented in `docs/aito-cheatsheet.md` first.
    #   2. Have a sanity-check assertion in `./do aito-check` in the
    #      same PR that adds it.
    #
    # Add `predict`, `recommend`, `relate`, `search`, `evaluate`,
    # `match` here as their first calling view appears.
