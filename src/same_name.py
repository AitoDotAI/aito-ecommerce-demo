"""One card per product name in the Shop's lists.

PetNord's generated catalogue gives some products the same name and the
same details under different SKUs: "Trixie Hideout" is SKU-PT-0563 and
SKU-PT-0564. Aito ranks each SKU on its own rows, so a list ranked by
Aito can show one name twice. A shopper can't tell the two apart, so each
list shows one card per name:

- The card is the **highest-ranked** SKU of its name: its own `$p`, its
  own reasons, its own link. Scores are never summed or blended, because
  each one is Aito's answer for that SKU only.
- The card keeps its own place in the ranking, and lists the other SKUs
  it stands for in `same_name_skus`, so the page can say "+1 variant".
- `wins` picks a different SKU for a group: in the sandbox's re-scored
  Shop, the product a lever changed shows, even when its twin ranked above
  it (`src/shop_grid.py`).

Rows that are per SKU on purpose (Supply's reorders, the best sellers)
aren't collapsed; they show the SKU beside the name instead.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, TypeVar

Item = TypeVar("Item")   # a frozen dataclass with `sku`, `name` and `same_name_skus`


def one_per_name(ranked: list[Item], *, wins: Callable[[Item], bool] = lambda item: False) -> list[Item]:
    """`ranked`, best first, with one item per name.

    Each name's item is the first one `wins` holds for, else its first
    (highest-ranked) item, carrying the SKUs of the others it stands for.
    """
    by_name: dict[str, list[Item]] = {}
    for item in ranked:
        by_name.setdefault(item.name, []).append(item)

    kept = []
    for item in ranked:
        group = by_name[item.name]
        winner = next((i for i in group if wins(i)), group[0])
        if item is winner:
            others = [i.sku for i in group if i is not winner]
            kept.append(replace(item, same_name_skus=others))
    return kept
