"""Which database a request reads: PetNord's, or one sandbox branch (ADR 0043).

A sandbox is named in the request, as `?db=<branch>` in the URL (so a link
can be shared in a meeting) or an `X-Aito-Env: <branch>` header (the
frontend sends it on every call while the page's URL carries `?db`):

    GET /api/shop/grid?shopper=paivi&month=2026-05&db=tmp-2026-10-26-15-30-00-3f9c2a1b7d4e6f80

- No sandbox named: PetNord's database, through its read-only client.
- A live `tmp-` branch named: that branch, for reads and writes.
- Anything else (a malformed name, an expired branch, a server without a
  sandbox, the two places disagreeing): 400. Never PetNord's database,
  so a stale link can't show a room PetNord's data as if it were theirs.

The caches are PetNord's only: a sandbox's answers never enter them.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from src.aito_client import AitoClient
from src.sandbox_envs import SandboxBranches, SandboxEnvError

ENV_HEADER = "X-Aito-Env"
ENV_QUERY = "db"


def requested_sandbox(request: Request) -> str | None:
    """The sandbox the request names, or None. Raises when the two places disagree."""
    in_query = request.query_params.get(ENV_QUERY)
    in_header = request.headers.get(ENV_HEADER)
    if in_query and in_header and in_query != in_header:
        raise SandboxEnvError(f"The request names two sandboxes: ?{ENV_QUERY}={in_query} and {ENV_HEADER}: {in_header}")
    return in_query or in_header or None


@dataclass(frozen=True)
class DemoClients:
    petnord: AitoClient                   # read-only whenever `branches` is set
    branches: SandboxBranches | None      # None: sandbox mode is off on this server

    def __post_init__(self) -> None:
        if self.branches is not None and not self.petnord.read_only:
            raise ValueError("With sandboxes configured, PetNord's client must be read-only (ADR 0043)")

    def reader(self, request: Request) -> AitoClient:
        """The client this request reads and writes; raises SandboxEnvError (400)."""
        name = requested_sandbox(request)
        if name is None:
            return self.petnord
        if self.branches is None:
            raise SandboxEnvError(f"This server has no sandboxes, so ?{ENV_QUERY}={name} can't be served")
        return self.branches.client(name)

    def sandbox(self, request: Request) -> AitoClient:
        """The branch a lever writes; raises SandboxEnvError unless the request names one."""
        client = self.reader(request)
        if client is self.petnord:
            raise SandboxEnvError(f"A lever needs a sandbox: name one with ?{ENV_QUERY}= or {ENV_HEADER}")
        return client
