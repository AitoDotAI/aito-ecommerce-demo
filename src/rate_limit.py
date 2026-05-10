"""Two-tier in-memory rate limiter for the public demo API.

Two sliding-window counters protect against two abuse patterns:

  1. **Per-IP** — one client can't drown everyone else.
  2. **Global** — a botnet hammering thousands of IPs each below the
     per-IP cap still hits the global ceiling and gets shed cleanly.

The per-tenant tier from `aito-erp-demo` is dropped — this demo is
single-tenant. Restore it from there if multi-tenancy ever returns.

Trusted-source bypass: localhost / 127.0.0.1 traffic skips the
per-IP cap so screenshot/booktest tooling doesn't trip itself.
"""

import os
import time
from collections import defaultdict


def _intenv(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


PER_IP_MAX = _intenv("RATE_LIMIT_PER_IP", 60)        # req / 60s / IP
GLOBAL_MAX = _intenv("RATE_LIMIT_GLOBAL", 1500)      # req / 60s total
WINDOW_SECONDS = 60

_TRUSTED = {"127.0.0.1", "::1", "localhost"}


_per_ip: dict[str, list[float]] = defaultdict(list)
_global: list[float] = []


def _trim(timestamps: list[float], cutoff: float) -> list[float]:
    return [t for t in timestamps if t > cutoff]


def check_rate_limit(client_ip: str) -> tuple[bool, str | None]:
    """Return `(allowed, reason)` — `reason` tells the caller which
    tier tripped, so the API response can be specific without revealing
    internal thresholds.
    """
    now = time.monotonic()
    cutoff = now - WINDOW_SECONDS

    global_now = _trim(_global, cutoff)
    if len(global_now) >= GLOBAL_MAX:
        _global[:] = global_now
        return False, "global"

    ip_now: list[float] = []
    if client_ip not in _TRUSTED:
        ip_now = _trim(_per_ip[client_ip], cutoff)
        if len(ip_now) >= PER_IP_MAX:
            _per_ip[client_ip] = ip_now
            _global[:] = global_now
            return False, "ip"

    global_now.append(now)
    _global[:] = global_now
    if client_ip not in _TRUSTED:
        ip_now.append(now)
        _per_ip[client_ip] = ip_now
    return True, None
