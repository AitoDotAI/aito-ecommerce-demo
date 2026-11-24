#!/usr/bin/env python3
"""A timing check to run a few minutes before a demo: where does the time go, call by call?

    ./do demo-check                          # https://ecommerce.aito.ai, two calls per path
    ./do demo-check --base http://localhost:8500 --calls 1

Every call is a GET and curl's own clock splits it into DNS, connect, TLS, wait for the first byte
and transfer. Any stage over one second is named, and the verdict says whose it probably is: a slow
DNS lookup is the resolver of the machine this runs on, not the demo (a stall of 5 s or 10 s is a
resolver timeout, measured 2026-11-24); a slow connect or TLS is the network or the host's proxy; a
slow wait is the server; a slow transfer is the payload or the network. It does not judge the
content of the views: `scripts/live_smoke.py` does that.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass

LIVE_BASE = "https://ecommerce.aito.ai"
SLOW_STAGE_SECONDS = 1.0
# The paths the demo opens, with the trailing slash on pages so a call is not a 307 and a second round trip.
PATHS = (
    "/api/version",
    "/api/shop/grid?shopper=saara&month=2026-04&cart=",
    "/api/shop/suggestions?shopper=paivi&month=2026-04&cart=",
    "/api/shop/search?q=food&shopper=saara&month=2026-04&cart=",
    "/api/supply",
    "/api/retention",
    "/api/customer-profiles",
    "/api/shop-analytics/baskets",
    "/api/feedback-patterns",
    "/shop/", "/supply/", "/customers/", "/retention/",
)
CURL_FORMAT = "%{time_namelookup} %{time_connect} %{time_appconnect} %{time_starttransfer} %{time_total} %{http_code} %{size_download}"
WHOSE = {
    "dns": "the DNS lookup is the resolver of the machine running this check, not the demo",
    "connect": "the TCP connect is slow: the network or the host's proxy, not the app",
    "tls": "the TLS handshake is slow: the network or the host's proxy",
    "server": "the server took long to answer after connecting",
    "transfer": "the response was slow to arrive: its size or the network",
}


@dataclass(frozen=True)
class Call:
    path: str
    dns: float
    connect: float
    tls: float            # curl's time_appconnect: 0 for plain http
    ttfb: float
    total: float
    status: int
    size_bytes: int


def parse_curl_timing(path: str, output: str) -> Call:
    fields = output.split()
    try:
        if len(fields) != 7:
            raise ValueError
        dns, connect, tls, ttfb, total = (float(f) for f in fields[:5])
        return Call(path, dns, connect, tls, ttfb, total, int(fields[5]), int(fields[6]))
    except ValueError:
        raise ValueError(f"{path}: expected 7 numbers from curl, got {output!r}") from None


def stage_durations(call: Call) -> dict[str, float]:
    """Seconds spent in each stage; curl's marks are cumulative from the start."""
    connected = max(call.connect, call.tls)
    return {
        "dns": call.dns,
        "connect": call.connect - call.dns,
        "tls": call.tls - call.connect if call.tls else 0.0,
        "server": call.ttfb - connected,
        "transfer": call.total - call.ttfb,
    }


def slow_stage(call: Call) -> str | None:
    """The stage that took over a second, or the slowest if several did; None if none did."""
    stage, seconds = max(stage_durations(call).items(), key=lambda item: item[1])
    return stage if seconds > SLOW_STAGE_SECONDS else None


def verdict(calls: list[Call]) -> str:
    failed = sorted({c.status for c in calls if not 200 <= c.status < 400})
    if failed:
        return "FAILED: " + ", ".join(f"HTTP {s} on {sorted({c.path for c in calls if c.status == s})}" for s in failed)
    slow = [(c, slow_stage(c)) for c in calls if slow_stage(c)]
    if not slow:
        return f"READY: {len(calls)} calls, none with a stage over {SLOW_STAGE_SECONDS:.0f} s; slowest total {max(c.total for c in calls):.1f} s"
    stages = sorted({stage for _, stage in slow})
    return (f"SLOW: {len(slow)} of {len(calls)} calls had a stage over {SLOW_STAGE_SECONDS:.0f} s ("
            + "; ".join(f"{stage}: {WHOSE[stage]}" for stage in stages) + "). Run it again: a stall that does not repeat is intermittent.")


def curl_command(base: str, path: str) -> list[str]:
    # --compressed sends Accept-Encoding like a browser: the host gzips (435 KB raw is 65 KB on the wire).
    return ["curl", "-s", "--compressed", "-o", "/dev/null", "-m", "60", "-w", CURL_FORMAT, base + path]


def run_curl(base: str, path: str) -> Call:
    result = subprocess.run(curl_command(base, path), capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed for {base + path} (exit {result.returncode}): {result.stderr.strip()}")
    return parse_curl_timing(path, result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default=LIVE_BASE)
    parser.add_argument("--calls", type=int, default=2, help="calls per path (default 2)")
    args = parser.parse_args()

    calls: list[Call] = []
    print(f"{'path':58} {'dns':>5} {'conn':>5} {'tls':>5} {'wait':>5} {'xfer':>5} {'total':>6}  status")
    for path in PATHS:
        for _ in range(args.calls):
            call = run_curl(args.base, path)
            s = stage_durations(call)
            mark = f"  <- {slow_stage(call)}" if slow_stage(call) else ""
            print(f"{path[:58]:58} {s['dns']:5.2f} {s['connect']:5.2f} {s['tls']:5.2f} {s['server']:5.2f} {s['transfer']:5.2f} {call.total:6.2f}  {call.status}{mark}")
            calls.append(call)
    text = verdict(calls)
    print("\n" + text)
    return 0 if text.startswith("READY") else 1


if __name__ == "__main__":
    sys.exit(main())
