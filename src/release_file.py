"""The release file: which data a build was made for (ADR 0035).

A release that changes the data model ships its data as a new Aito env,
which is promoted onto `master` during the cutover. The code and the data
must go live together, so the code carries a description of its data:
`data/release-env.json`, the release env's name and the row count of each
table.

    {
      "env": "observable",
      "counts": {"customers": 3000, "orders": 11909, ...}
    }

Two readers use it:

- **aito-azure's cutover pre-flight** checks that the release env holds
  exactly these counts before it promotes anything.
- **The running app** (`src/data_release_gate.py`) holds its data routes
  at 503 until the env it reads matches, so new code never serves
  answers computed on old data.

`./do release-file <env>` writes the file from an env's live counts.
The counts are read with `_search` and `limit: 0`, which returns the
table's `total` without any rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.aito_client import AitoClient
from src.cache import CACHE_TABLE
from src.precompute_store import PRECOMPUTE_TABLE

RELEASE_FILE = Path(__file__).resolve().parent.parent / "data" / "release-env.json"

# Tables the app and `./do precompute` write while running. Their row
# counts change without a release, so they are not part of one.
OPERATIONAL_TABLES = frozenset({CACHE_TABLE, PRECOMPUTE_TABLE})


class ReleaseFileError(ValueError):
    """The release file is missing or not in the expected shape."""


@dataclass(frozen=True)
class Release:
    env: str
    counts: dict[str, int]

    def to_dict(self) -> dict:
        return {"env": self.env, "counts": dict(sorted(self.counts.items()))}


def load_release(path: Path = RELEASE_FILE) -> Release:
    """Read and validate the release file. Raises `ReleaseFileError`.

    Strict on purpose: a release file that parses loosely would let the
    app or the pre-flight compare against the wrong numbers and pass.
    """
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ReleaseFileError(f"Release file {path} does not exist; write it with ./do release-file <env>") from exc
    except json.JSONDecodeError as exc:
        raise ReleaseFileError(f"Release file {path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict) or set(raw) != {"env", "counts"}:
        keys = sorted(raw) if isinstance(raw, dict) else type(raw).__name__
        raise ReleaseFileError(f"Release file {path} must be an object with exactly 'env' and 'counts'; got {keys}")
    env, counts = raw["env"], raw["counts"]
    if not isinstance(env, str) or not env:
        raise ReleaseFileError(f"Release file {path}: 'env' must be a non-empty string; got {env!r}")
    if not isinstance(counts, dict) or not counts:
        raise ReleaseFileError(f"Release file {path}: 'counts' must be a non-empty object; got {counts!r}")
    for table, count in counts.items():
        # `bool` is an `int` in Python; `true` is not a row count.
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ReleaseFileError(f"Release file {path}: count of '{table}' must be a non-negative integer; got {count!r}")
    if OPERATIONAL_TABLES & set(counts):
        raise ReleaseFileError(
            f"Release file {path} lists {sorted(OPERATIONAL_TABLES & set(counts))}, "
            "which change while the app runs and can't be part of a release"
        )
    return Release(env=env, counts=counts)


def write_release(release: Release, path: Path = RELEASE_FILE) -> None:
    path.write_text(json.dumps(release.to_dict(), indent=2) + "\n")


def read_counts(client: AitoClient) -> dict[str, int]:
    """Row count of every data table in the env the client addresses."""
    tables = sorted(set(client.get_schema()["schema"]) - OPERATIONAL_TABLES)
    return {table: client.search(table, limit=0)["total"] for table in tables}


def differences(expected: dict[str, int], actual: dict[str, int]) -> list[str]:
    """How `actual` differs from the release's counts, one line per table.

    An empty list means the data is the release's.
    """
    lines = []
    for table in sorted(set(expected) | set(actual)):
        if table not in actual:
            lines.append(f"{table}: missing (release has {expected[table]} rows)")
        elif table not in expected:
            lines.append(f"{table}: not in the release ({actual[table]} rows)")
        elif expected[table] != actual[table]:
            lines.append(f"{table}: {actual[table]} rows, release has {expected[table]}")
    return lines
