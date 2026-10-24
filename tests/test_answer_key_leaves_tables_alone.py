"""The answer key may grow; the tables Aito loads may not move (ADR 0037 §3).

The personalised-search benchmark's ceiling reads the generator's hidden
inputs for each shopper (favourite brands, pet size, diet rule) from
`data/answer_key/`, which is never loaded into Aito. Adding them must not
change a byte of any loaded table: otherwise the benchmark would score a
different dataset from the one the release loads.

Regenerates the whole dataset into a temporary directory (~45 s).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import data.generate_fixtures as generator
from src.schema import SCHEMAS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("regenerated")
    original = generator.DATA_DIR
    generator.DATA_DIR = out
    try:
        generator.main()
    finally:
        generator.DATA_DIR = original
    return out


def test_regenerating_writes_every_committed_loaded_table_byte_for_byte(regenerated):
    # impressions.json is too big to commit (ADR 0021); it is checked below.
    committed = [t for t in SCHEMAS if (DATA_DIR / f"{t}.json").exists() and t != "impressions"]
    assert len(committed) >= 10, f"expected the committed tables, found {committed}"
    moved = [t for t in committed
             if (regenerated / f"{t}.json").read_bytes() != (DATA_DIR / f"{t}.json").read_bytes()]
    assert moved == [], f"regenerating changed loaded tables: {moved}"


def test_regenerated_impressions_match_the_release(regenerated):
    release = json.loads((DATA_DIR / "release-env.json").read_text(encoding="utf-8"))
    rows = json.loads((regenerated / "impressions.json").read_text(encoding="utf-8"))
    assert len(rows) == release["counts"]["impressions"]
    local = DATA_DIR / "impressions.json"
    if local.exists():
        assert (regenerated / "impressions.json").read_bytes() == local.read_bytes()


def test_the_answer_key_carries_what_the_ceiling_reads(regenerated):
    rows = json.loads((regenerated / "answer_key" / "customer_traits.json").read_text(encoding="utf-8"))
    loyal = [r for r in rows if r["brand_loyalty"] == "loyal"]
    assert loyal and all(r["favorite_brands"] for r in loyal)
    assert all(isinstance(r["favorite_brands"], list) for r in rows)
    assert any("pet_size" in r for r in rows) and any("diet_rule" in r for r in rows)
