"""Data release 6, C2: fictional brands (docs/verification/release6-prereg.md, section 4; td-20261124130721630361).

The mapping is applied when the release is WRITTEN, after every draw: the generator keeps drawing with the release-5
brands, so no draw can see a different string and the sales stay byte-identical (check S1). Only two kinds of string
change:

- a value of a brand column (`brand`, `product_brand`, `favorite_brands`) that is exactly a release-5 brand;
- a FULL product name inside any string (product names, review and NPS texts, experiment titles ...). A product name
  starts with its brand (`_compose_name`), so the new name is the new brand plus the same rest.

A bare brand word anywhere else is NOT rewritten (a customer may be called Felix): `scan_for_real_brands` finds it,
and the release fails (check B1). The PetNord house label stays.

THE TABLE IS A DRAFT until Antti's OK (CPO 2026-11-24): the EU and Finnish registers are not yet checked. Do not
cut or pin a release with it before then.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from urllib.parse import unquote_plus

# DRAFT, see the module doc. release 5 -> release 6, same tier and categories.
RELEASE6_BRANDS: dict[str, str] = {
    "Royal Canin": "Aurelian Vet",
    "Hill's Science Plan": "Fernholm Nutrition Plan",
    "Acana": "Tundrafield",
    "Orijen": "Wildmarrow",
    "Eukanuba": "Kestrova",
    "Whiskas": "Purrsy",
    "Felix": "Nyamzo",
    "Sheba": "Velvetbowl",
    "Whimzees": "Chewbrite Twists",
    "Kong": "Fetchaboo",
    "Trixie": "Tassuliini",
    "JBL": "Rippleward",
    "Tetra": "Aquadotte",
    "Beaphar": "Herbellon",
}
HOUSE_LABEL = "PetNord"
BRAND_KEYS = frozenset({"brand", "product_brand", "favorite_brands"})


def _brand_pattern(brand: str) -> str:
    """A brand as a reader or a URL might spell it: any case, words joined by a space, '-', '_', '+', '%20' or nothing,
    an apostrophe of either kind or none. "Hill's Science Plan" also matches "Hill's" alone ("hills" alone does not:
    a common word)."""
    words = [re.escape(w).replace("'", "['’]?") for w in brand.split()]
    full = r"(?:[\s_+\-]|%20)*".join(words)
    if brand == "Hill's Science Plan":
        return rf"(?:{full}|hill['’]s)"
    return full


REAL_BRANDS = re.compile(r"(?<![a-z0-9])(?:" + "|".join(_brand_pattern(b) for b in RELEASE6_BRANDS) + r")(?![a-z0-9])", re.IGNORECASE)


def check_mapping(mapping: dict[str, str] = RELEASE6_BRANDS, brands: Iterable[str] | None = None) -> None:
    """B2: one to one; no new name equals or contains a release-5 name; the house label is not mapped; every brand
    of the generator (when given) is mapped except the house label. Raises on any breach."""
    new = list(mapping.values())
    if len(set(new)) != len(new):
        raise ValueError("two release-5 brands map to the same name")
    for name in new:
        if REAL_BRANDS.search(name):
            raise ValueError(f"the new name {name!r} contains a release-5 brand")
        if name.lower() == HOUSE_LABEL.lower():
            raise ValueError("a brand maps onto the house label")
    if HOUSE_LABEL in mapping:
        raise ValueError("the house label is not to be mapped")
    if brands is not None:
        missing = set(brands) - {HOUSE_LABEL} - set(mapping)
        extra = set(mapping) - set(brands)
        if missing or extra:
            raise ValueError(f"the mapping does not match the generator's brands: missing {sorted(missing)}, unknown {sorted(extra)}")


def product_name_map(products: Iterable[dict], mapping: dict[str, str] = RELEASE6_BRANDS) -> dict[str, str]:
    """Release-5 product name -> release-6 name, for every product of a mapped brand. A name that does not start with
    its brand cannot be mapped safely: raises."""
    out: dict[str, str] = {}
    for p in products:
        brand, name = p["brand"], p["name"]
        if brand not in mapping:
            continue
        if not name.startswith(brand + " "):
            raise ValueError(f"{p.get('sku') or p.get('id')}: the name {name!r} does not start with its brand {brand!r}")
        out[name] = mapping[brand] + name[len(brand):]
    return out


class Rebrander:
    """Rewrites rows: brand columns by value, full product names inside any string (longest name first)."""

    def __init__(self, name_map: dict[str, str], mapping: dict[str, str] = RELEASE6_BRANDS):
        self.mapping = mapping
        self.name_map = name_map
        names = sorted(name_map, key=len, reverse=True)
        self._names = re.compile("|".join(re.escape(n) for n in names)) if names else None

    def text(self, s: str) -> str:
        return self._names.sub(lambda m: self.name_map[m.group(0)], s) if self._names else s

    def value(self, v, key: str | None = None):
        if isinstance(v, str):
            if key in BRAND_KEYS and v in self.mapping:
                return self.mapping[v]
            return self.text(v)
        if isinstance(v, list):
            return [self.value(x, key) for x in v]
        if isinstance(v, dict):
            return {k: self.value(x, k) for k, x in v.items()}
        return v

    def rows(self, rows: list[dict]) -> list[dict]:
        return [self.value(r) for r in rows]


def scan_for_real_brands(obj, where: str = "") -> Iterator[tuple[str, str]]:
    """B1 (CPO 2026-11-24): every string of a written release, case-insensitive, also URL-decoded and as slugs:
    (path, the matched text) for each release-5 brand that survived. Keys are scanned too."""
    if isinstance(obj, str):
        for form in (obj, unquote_plus(obj)):
            m = REAL_BRANDS.search(form)
            if m:
                yield where, m.group(0)
                return
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from scan_for_real_brands(k, f"{where}.<key>")
            yield from scan_for_real_brands(v, f"{where}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from scan_for_real_brands(v, f"{where}[{i}]")
