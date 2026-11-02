"""Put a data release's env onto `master`, after a backup of master (ADR 0035). A write to the shared instance.

    ./do env-promote release4            # dry run: the checks, and what it would do
    ./do env-promote release4 --apply    # back up master, then promote the env onto it

Refuses `master`, an env that does not exist, an env whose row counts are not `data/release-env.json`'s (it is not the
release), and a backup name that is taken. The backup is a branch of master named `master-backup-<date and time>`:
rolling back is promoting it (ADR 0035, "Rollback, data first"). The app waits for its data release, so the new image
answers 503 until the promote, and the old one after it. Afterwards: `./do release-check master`, `./do clear-cache`, warm up.
"""
from __future__ import annotations

import dataclasses
import datetime
import sys
from collections.abc import Callable

import httpx

from src.release_file import Release, differences, load_release

TARGET = "master"


class NotTheRelease(RuntimeError):
    """The env's row counts are not the release file's."""


class BackupExists(RuntimeError):
    """An env with the backup's name exists already."""


def promote(http: httpx.Client, base: str, env: str, release: Release, read_counts: Callable[[str], dict[str, int]],
            apply: bool, backup_name: str) -> str:
    """Check, then (with `apply`) back up master and promote `env`. Returns the plan or what was done."""
    if env == TARGET:
        raise ValueError(f"Cannot promote {TARGET!r} onto itself.")
    listed = http.get(f"{base}/_envs")
    if listed.status_code >= 400:
        raise RuntimeError(f"Listing envs answered {listed.status_code}: {listed.text[:300]}")
    names = {e.get("name") for e in listed.json().get("envs", [])}
    if env not in names:
        raise ValueError(f"There is no env {env!r} on {base}; it has {sorted(n for n in names if n)}.")
    if backup_name in names:
        raise BackupExists(f"An env named {backup_name!r} exists already: not backing master up over it.")
    if env != release.env:
        raise NotTheRelease(f"data/release-env.json is the release {release.env!r}, not {env!r}.")
    wrong = differences(release.counts, read_counts(env))
    if wrong:
        raise NotTheRelease(f"Env {env!r} is not the release; row counts differ: " + "; ".join(wrong))
    plan = (f"Env {env!r} matches data/release-env.json ({len(release.counts)} tables). Would back {TARGET} up as {backup_name!r} "
            f"(a branch of env.{TARGET}), then promote {env!r} onto {TARGET} on {base}.")
    if not apply:
        return f"Dry run: {plan} Re-run with --apply."
    backup = http.post(f"{base}/_envs", json={"name": backup_name, "basedOn": f"env.{TARGET}"})
    if backup.status_code >= 400:
        raise RuntimeError(f"The backup of {TARGET} answered {backup.status_code}: {backup.text[:300]}. Nothing was promoted.")
    done = http.post(f"{base}/_envs/{env}/promote")
    if done.status_code >= 400:
        raise RuntimeError(f"Promoting {env!r} answered {done.status_code}: {done.text[:300]}. {TARGET} is backed up as {backup_name!r}.")
    return (f"Backed {TARGET} up as {backup_name!r} and promoted {env!r} onto {TARGET}. Next: ./do release-check {TARGET}; "
            f"./do clear-cache; warm up. To go back: promote {backup_name!r}.")


def main(argv: list[str]) -> int:
    names = [a for a in argv if not a.startswith("--")]
    if len(names) != 1:
        print(__doc__)
        return 2
    from src.aito_client import AitoClient
    from src.config import load_config
    from src.release_file import read_counts

    config = load_config()
    base = f"{config.aito_api_url}/api/v1"
    http = httpx.Client(headers={"x-api-key": config.aito_api_key, "content-type": "application/json"}, timeout=120)

    def counts(env: str) -> dict[str, int]:
        return read_counts(AitoClient(dataclasses.replace(config, aito_env=env)))

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M")
    try:
        print(promote(http, base, names[0], load_release(), counts, "--apply" in argv, f"master-backup-{stamp}"))
    except (ValueError, RuntimeError) as exc:
        print(f"Refused: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
