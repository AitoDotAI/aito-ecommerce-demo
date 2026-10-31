"""The app waits for its data (ADR 0035).

During a cutover the new container starts a few minutes before the
release env is promoted onto `master`; during a rollback the new code
keeps running for a few minutes after the old data is promoted back. In
both windows the code would read data it wasn't built for and answer
with numbers that look fine and are wrong.

So the app compares the env it reads with its release file
(`data/release-env.json`, see `src/release_file.py`):

- **pending**: the tables or counts differ. Data routes answer 503
  `{"error": "data release pending", ...}`; `/api/version` and
  `/api/health` answer as usual.
- **ready**: they match. On the change to ready the app warms its caches.

The check runs at startup. While the data is pending it runs every 60
seconds, so a cutover sees the data arrive within a minute. Once ready it
runs every 15 minutes (`RELEASE_GATE_RECHECK_SECONDS`; 0 stops checking
once ready, which `./do dev` sets), and whenever `/api/health` is polled and
the last check is over a minute old, so a deploy script watching a rollback
sees it at once. Each check reads the schema and one count per data table,
per app instance, so a gate that polled every minute forever put about 17
calls a minute on the shared Aito for every instance anyone left running.
On a change from ready back to pending, the in-memory caches are dropped,
so nothing warmed on one dataset is served on another.

Which env is compared: the one the app reads, `AITO_ENV` (default
`master`). In production that is `master`. On staging, or in local dev
with `AITO_ENV=observable ./do dev`, it is the release env itself, which
matches right away. On the `unified` branch a plain `./do dev` (master,
before the promote) stays pending, which is the point.

The sandbox database (ADR 0043) has a gate of its own, on its master:
the template its branches are made from. It is ready once
`./do sandbox-template-load` has loaded the release, and a request that
names a sandbox branch is gated by it, not by PetNord's. (A branch is a
copy of the template, plus the levers' rows.)

When the counts can't be read (Aito unreachable, an error) the state is
left as it was and the error is logged and reported in `status()`: one
failed read is not evidence that the data changed.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Mapping
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from src.aito_client import AitoError
from src.release_file import Release, differences

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60                  # while pending: a cutover is waiting for the data
READY_CHECK_INTERVAL_SECONDS = 900           # once ready: a rollback is caught within this, or sooner by a health probe
RECHECK_ENV = "RELEASE_GATE_RECHECK_SECONDS"


def recheck_seconds_from_env(environ: Mapping[str, str]) -> float:
    """How often a ready gate reads the counts again, from `RELEASE_GATE_RECHECK_SECONDS` (0: never)."""
    raw = environ.get(RECHECK_ENV)
    if raw is None:
        return READY_CHECK_INTERVAL_SECONDS
    try:
        seconds = float(raw)
    except ValueError:
        seconds = -1.0
    if seconds < 0:
        raise ValueError(f"{RECHECK_ENV} must be a number of seconds, 0 or more (0: never re-check once ready); got {raw!r}")
    return seconds

PENDING = "pending"
READY = "ready"


class DataReleaseGate:
    """Tracks whether the data matches the release, and acts on changes.

    `read_counts` returns the live row count per table. `on_ready` runs
    on each change to ready (warm the caches); `on_mismatch` on each
    change from ready to pending (drop the in-memory caches). All three
    are injected, so tests drive the gate without Aito or a clock.
    """

    def __init__(
        self,
        release: Release,
        *,
        read_counts: Callable[[], dict[str, int]],
        on_ready: Callable[[], None],
        on_mismatch: Callable[[], None],
        ready_interval: float = READY_CHECK_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.release = release
        self._read_counts = read_counts
        self._on_ready = on_ready
        self._on_mismatch = on_mismatch
        self.ready_interval = ready_interval
        self._clock = clock
        self._last_checked: float | None = None
        self.state = PENDING
        self.differences: list[str] = ["not checked yet"]
        self.last_error: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.state == READY

    def check(self) -> None:
        """Read the counts once and update the state."""
        self._last_checked = self._clock()
        try:
            actual = self._read_counts()
        except AitoError as exc:
            self.last_error = str(exc)
            logger.error("Data release check failed; staying %s: %s", self.state, exc)
            return
        self.last_error = None
        self.differences = differences(self.release.counts, actual)

        if not self.differences and self.state == PENDING:
            self.state = READY
            logger.warning("Data matches release %r; serving data routes", self.release.env)
            self._on_ready()
        elif self.differences and self.state == READY:
            self.state = PENDING
            logger.error("Data no longer matches release %r: %s", self.release.env, "; ".join(self.differences))
            self._on_mismatch()

    def check_if_older_than(self, seconds: float) -> None:
        """Check now unless the last check was less than `seconds` ago: what a health probe asks for."""
        if self._last_checked is None or self._clock() - self._last_checked >= seconds:
            self.check()

    def status(self) -> dict:
        """The gate's state, for the 503 body and `/api/health`."""
        return {
            "state": self.state,
            "release_env": self.release.env,
            "differences": self.differences,
            "last_error": self.last_error,
        }

    def run_forever(self, *, interval: float = CHECK_INTERVAL_SECONDS, sleep: Callable[[float], None] = time.sleep) -> None:
        """Check, then wait `interval` while pending and `ready_interval` once ready; with `ready_interval` 0, stop once ready."""
        while True:
            self.check()
            if self.is_ready and self.ready_interval == 0:
                return
            sleep(self.ready_interval if self.is_ready else interval)

    def start(self, *, name: str = "data-release-gate") -> threading.Thread:
        """Check now, then at the intervals above, on a daemon thread."""
        thread = threading.Thread(target=self.run_forever, name=name, daemon=True)
        thread.start()
        return thread


# Routes that answer whatever the data: the build and the connection.
# `/api/uci/` reads env `uci`, which a release of the pet shop's data
# doesn't touch (ADR 0034).
UNGATED_PATHS = frozenset({"/api/version", "/api/health", "/api/sandbox"})
UNGATED_PREFIX = "/api/uci/"


def is_data_route(path: str) -> bool:
    return path.startswith("/api/") and path not in UNGATED_PATHS and not path.startswith(UNGATED_PREFIX)


def release_gate_middleware(gate: DataReleaseGate, sandbox_gate_for: Callable[[Request], DataReleaseGate | None]
                            = lambda request: None):
    """An HTTP middleware: 503 on data routes while the request's gate is
    pending. `sandbox_gate_for` returns the sandbox's gate for a request that
    reads the sandbox, None for one that reads master."""
    async def middleware(request: Request, call_next):
        if is_data_route(request.url.path):
            request_gate = sandbox_gate_for(request) or gate
            if not request_gate.is_ready:
                return JSONResponse(
                    status_code=503,
                    content={"error": "data release pending", **request_gate.status()},
                    headers={"Retry-After": "60"},
                )
        return await call_next(request)
    return middleware
