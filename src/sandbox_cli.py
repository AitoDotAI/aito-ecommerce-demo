"""The operator's sandbox commands (ADR 0043), behind `./do sandbox-*`.

    ./do sandbox-template-load   load the release fixtures into the sandbox
                                 database's master (the template), once
    ./do sandbox-new             branch a sandbox off the template, warm it,
                                 and print its `?db=` link
    ./do sandbox-list            the live sandboxes and when they expire
    ./do sandbox-time            time the lever → reaction loop 5× on a
                                 throwaway branch, then delete it

Every command refuses unless AITO_SANDBOX_URL names a sandbox database
(`src/sandbox_config.py`). The template load is the only write to the
sandbox database's master, and it is never run by the app.
"""

from __future__ import annotations

import os
import sys
import time

from src.aito_client import WRITES_ENVS, AitoClient
from src.config import load_config
from src.release_file import differences, load_release, read_counts
from src.sandbox_config import load_sandbox_setting
from src.sandbox_envs import SandboxBranches, expires_at
from src.sandbox_warmup import warm_up


def _setting():
    setting = load_sandbox_setting(load_config())
    if setting.config is None:
        sys.exit(f"Refusing: {setting.off_reason}.")
    return setting


def template_load() -> None:
    setting = _setting()
    print(f"Loading the release fixtures into {setting.database} (its master: the template)")
    # The loader reads its target from the environment: point it at the sandbox database.
    os.environ.update(AITO_API_URL=setting.config.aito_api_url, AITO_API_KEY=setting.config.aito_api_key,
                      AITO_ENV="master")
    from src import data_loader
    start = time.perf_counter()
    data_loader.run(reset=True)
    print(f"Loaded in {time.perf_counter() - start:.0f} s")

    template = AitoClient(setting.config, writes=WRITES_ENVS)
    require_v2_engine(template)
    found = differences(load_release().counts, read_counts(template))
    if found:
        sys.exit("The template doesn't match data/release-env.json:\n  " + "\n  ".join(found))
    print("The template matches the release. Warming it up:")
    _print_timings(warm_up(template))


# The tables the levers' queries read: they must be on Aito's v2 storage,
# where a branch's write rebuilds only the new segment (Aito core, 2.11.8).
ENGINE_CHECKED = ("impressions", "product_states", "order_lines", "monthly_sales")


def require_v2_engine(client: AitoClient) -> None:
    """`GET /schema/<table>?meta=true` answers `"engine": "v2"` per table (read-only)."""
    engines = {t: client._request("GET", f"/schema/{t}?meta=true").get("engine") for t in ENGINE_CHECKED}
    wrong = {t: e for t, e in engines.items() if e != "v2"}
    if wrong:
        sys.exit(f"Refusing: these template tables aren't on engine v2: {wrong}. Reload with ./do sandbox-template-load.")
    print(f"Engine v2 on {', '.join(ENGINE_CHECKED)}.")


def new() -> None:
    setting = _setting()
    branches = SandboxBranches(AitoClient(setting.config, writes=WRITES_ENVS))
    start = time.perf_counter()
    name = branches.create()
    print(f"Created {name} in {time.perf_counter() - start:.1f} s; it expires at {expires_at(name):%H:%M} UTC")
    _print_timings(warm_up(branches.client(name)))
    print(f"\nOpen:  http://localhost:8500/shop/?shopper=paivi&month=2026-05&db={name}")


def time_loop(runs: int = 5) -> None:
    """The ADR's Sunday check: the lever → reaction loop, timed on a branch of
    its own (so the demo's sandboxes keep no test rows), then deleted."""
    from src.discount_what_if import get_discount_what_if
    from src.product_levers import add_review, set_offer
    from src.shop_grid import get_shop_grid
    from src.shop_history import NEXT_MONTH
    from src.sandbox_warmup import SHOPPER, TARGET_SKU

    setting = _setting()
    branches = SandboxBranches(AitoClient(setting.config, writes=WRITES_ENVS))
    name = branches.create()
    print(f"Timing on {name}, then deleting it")
    try:
        branch = branches.client(name)
        _print_timings(warm_up(branch))
        bands = ["20+", "none", "10-15", "20+", "15-20"]
        print(f"\n  run  band   write+read-back  what-if  Shop (_recommend + re-score)   total")
        for run, band in enumerate(bands[:runs], start=1):
            t0 = time.perf_counter()
            set_offer(branch, TARGET_SKU, band)
            t1 = time.perf_counter()
            get_discount_what_if(branch, TARGET_SKU, NEXT_MONTH)
            t2 = time.perf_counter()
            grid = get_shop_grid(branch, SHOPPER, NEXT_MONTH, [], rescored=True)
            t3 = time.perf_counter()
            rank = next((i for i, item in enumerate(grid.items, 1) if item.sku == TARGET_SKU), None)
            print(f"  {run:3}  {band:5}  {t1 - t0:15.2f}  {t2 - t1:7.2f}  {t3 - t2:28.2f}   {t3 - t0:5.2f} s"
                  f"   (its grid rank: {rank or 'not in the top 12'})")
        t0 = time.perf_counter()
        review = add_review(branch, TARGET_SKU, 1, "Timing run: too small.")
        t1 = time.perf_counter()
        get_shop_grid(branch, SHOPPER, NEXT_MONTH, [], rescored=True)
        print(f"  review (1 star, band {review.rating_band_before} → {review.state['rating_band']}): "
              f"write+read-back {t1 - t0:.2f} s, Shop {time.perf_counter() - t1:.2f} s")
    finally:
        branches.delete(name)
        print(f"Deleted {name}")


def list_live() -> None:
    setting = _setting()
    branches = SandboxBranches(AitoClient(setting.config, writes=WRITES_ENVS))
    live = branches.live()
    print(f"{len(live)} live sandbox(es) in {setting.database}:")
    for name in live:
        print(f"  {name}  expires {expires_at(name):%Y-%m-%d %H:%M} UTC")


def _print_timings(timings: list[tuple[str, float]]) -> None:
    for label, seconds in timings:
        print(f"  {label:32s} {seconds:5.1f} s")


if __name__ == "__main__":
    commands = {"template-load": template_load, "new": new, "list": list_live, "time": time_loop}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(f"Usage: python -m src.sandbox_cli {{{'|'.join(commands)}}}")
    commands[sys.argv[1]]()
