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

The check runs at startup and every 60 seconds. On a change from ready
back to pending, the in-memory caches are dropped, so nothing warmed on
one dataset is served on another.

Which env is compared: the one the app reads, `AITO_ENV` (default
`master`). In production that is `master`. On staging, or in local dev
with `AITO_ENV=observable ./do dev`, it is the release env itself, which
matches right away. On the `unified` branch a plain `./do dev` (master,
before the promote) stays pending, which is the point.

When the counts can't be read (Aito unreachable, an error) the state is
left as it was and the error is logged and reported in `status()`: one
failed read is not evidence that the data changed.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from src.aito_client import AitoError
from src.release_file import Release, differences

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60

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
    ) -> None:
        self.release = release
        self._read_counts = read_counts
        self._on_ready = on_ready
        self._on_mismatch = on_mismatch
        self.state = PENDING
        self.differences: list[str] = ["not checked yet"]
        self.last_error: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.state == READY

    def check(self) -> None:
        """Read the counts once and update the state."""
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

    def status(self) -> dict:
        """The gate's state, for the 503 body and `/api/health`."""
        return {
            "state": self.state,
            "release_env": self.release.env,
            "differences": self.differences,
            "last_error": self.last_error,
        }

    def run_forever(self, *, interval: float = CHECK_INTERVAL_SECONDS, sleep: Callable[[float], None] = time.sleep) -> None:
        while True:
            self.check()
            sleep(interval)

    def start(self) -> threading.Thread:
        """Check now, then every `CHECK_INTERVAL_SECONDS`, on a daemon thread."""
        thread = threading.Thread(target=self.run_forever, name="data-release-gate", daemon=True)
        thread.start()
        return thread


# Routes that answer whatever the data: the build and the connection.
# `/api/uci/` reads env `uci`, which a release of the pet shop's data
# doesn't touch (ADR 0034).
UNGATED_PATHS = frozenset({"/api/version", "/api/health"})
UNGATED_PREFIX = "/api/uci/"


def is_data_route(path: str) -> bool:
    return path.startswith("/api/") and path not in UNGATED_PATHS and not path.startswith(UNGATED_PREFIX)


def release_gate_middleware(gate: DataReleaseGate):
    """An HTTP middleware: 503 on data routes while `gate` is pending."""
    async def middleware(request: Request, call_next):
        if is_data_route(request.url.path) and not gate.is_ready:
            return JSONResponse(
                status_code=503,
                content={"error": "data release pending", **gate.status()},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
    return middleware
