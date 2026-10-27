"""Make a new Aito env for a data release: a copy-on-write branch of `master` (ADR 0035), ready for `./do env-load`.

    ./do env-new release3a            # dry run: says what it would do
    ./do env-new release3a --apply    # creates the env (a write to the shared instance)

A branch of master costs milliseconds (v2 branches copy on write); `./do env-load` then drops and reloads every
table in it, so master's data is not what the release ends up holding. Refuses `master` and an env that exists.
"""
from __future__ import annotations

import sys

import httpx

from src.config import load_config

SOURCE = "master"


def main(argv: list[str]) -> int:
    names = [a for a in argv if not a.startswith("--")]
    if len(names) != 1 or names[0] == SOURCE:
        print(__doc__)
        return 2
    name, apply = names[0], "--apply" in argv
    config = load_config()
    http = httpx.Client(headers={"x-api-key": config.aito_api_key, "content-type": "application/json"}, timeout=60)
    existing = http.get(f"{config.aito_api_url}/api/v1/_envs")
    if existing.status_code >= 400:
        raise RuntimeError(f"Listing envs answered {existing.status_code}: {existing.text[:300]}")
    if name in {e.get("name") for e in existing.json().get("envs", [])}:
        print(f"Env {name!r} exists on {config.aito_api_url}: nothing to do (./do env-load fills it).")
        return 1
    if not apply:
        print(f"Dry run: would create env {name!r} (a branch of env.{SOURCE}) on {config.aito_api_url}. Re-run with --apply.")
        return 0
    made = http.post(f"{config.aito_api_url}/api/v1/_envs", json={"name": name, "basedOn": f"env.{SOURCE}"})
    if made.status_code >= 400:
        raise RuntimeError(f"Creating env {name!r} answered {made.status_code}: {made.text[:300]}")
    print(f"Created env {name!r}. Next: AITO_ENV={name} ./do env-load")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
