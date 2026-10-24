"""Warm a sandbox up before the room sees it (ADR 0043).

The first queries after a load or a new branch rebuild Aito's in-memory
models, and are the slow ones. This sends the ones Flows 1 and 2 of the
demo send first: Päivi's Shop in 2026-05 (its `_recommend`, the kit's
`_predict` and the shop-wide band lifts), and the Product view's discount
what-if for the hideout her kit needs next. Reads only.
"""

from __future__ import annotations

import logging
import time

from src.aito_client import AitoClient, AitoError
from src.discount_what_if import get_discount_what_if
from src.shop_grid import get_shop_grid
from src.shop_history import NEXT_MONTH
from src.shop_state_lifts import read_state_lifts
from src.shop_suggestions import get_suggestions

logger = logging.getLogger(__name__)

# The guinea-pig shopper, and the product her kit needs next (docs/demo-script.md).
SHOPPER = "paivi"
TARGET_SKU = "SKU-PT-0563"


def warm_resumed(client: AitoClient) -> None:
    """A branch idle for half an hour is evicted from Aito's memory and its
    next query re-links it cold: re-link it before the room's first click,
    with a count and the shop-wide band lifts the Shop and Product views read."""
    start = time.perf_counter()
    try:
        client.search("impressions", limit=0)
        read_state_lifts(client)
    except AitoError as exc:
        logger.error("Re-warming sandbox %s failed: %s", client.env, exc)
        return
    logger.warning("Re-warmed sandbox %s in %.1f s", client.env, time.perf_counter() - start)


def warm_up(client: AitoClient) -> list[tuple[str, float]]:
    """Runs each step once; returns (step, seconds) for the operator to read."""
    steps = [
        ("Shop grid, 2026-05", lambda: get_shop_grid(client, SHOPPER, NEXT_MONTH, [], rescored=True)),
        ("Next for their kit", lambda: get_suggestions(client, SHOPPER, NEXT_MONTH, [])),
        ("Band lifts", lambda: read_state_lifts(client)),
        (f"Discount what-if {TARGET_SKU}", lambda: get_discount_what_if(client, TARGET_SKU)),
    ]
    timings = []
    for label, step in steps:
        start = time.perf_counter()
        step()
        timings.append((label, time.perf_counter() - start))
    return timings
