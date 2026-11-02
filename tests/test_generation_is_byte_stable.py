"""A fresh seed-42 generation reproduces the committed fixtures byte for byte.

The data's planted effects, the Aito env's row counts and the release file
all assume one generator run gives one dataset. Slow (one full generation,
about a minute).
"""

import contextlib
import io
from pathlib import Path

import pytest

import data.generate_fixtures as generator

DATA = Path(__file__).resolve().parent.parent / "data"


def test_a_fresh_seed_42_generation_matches_the_committed_fixtures(tmp_path, monkeypatch):
    committed = sorted(p.relative_to(DATA) for p in [*DATA.glob("*.json"), *DATA.glob("answer_key/*.json")]
                       if p.name != "release-env.json")
    if not (DATA / "impressions.json").exists():
        pytest.skip("impressions.json missing: run ./do generate-fixtures")
    monkeypatch.setattr(generator, "RNG_SEED", 42)
    monkeypatch.setattr(generator, "DATA_DIR", tmp_path)
    with contextlib.redirect_stdout(io.StringIO()):
        generator.main()
    differing = [str(f) for f in committed if (tmp_path / f).read_bytes() != (DATA / f).read_bytes()]
    assert not differing, differing
