"""Stage the v2 (Rep2) migration in a separate Aito env — ADR 0025.

    ./do v2-env            # show what would happen (default)
    ./do v2-env --apply    # create the env, then migrate each table's engine

The live demo and every local checkout share ONE Aito instance, and the
Layer-2 prediction cache is a table on it. So v2 cannot be tried against
`master`. Instead we use Aito's envs feature — one instance, several
named envs — and clone a `v2` env from master:

    POST {url}/api/v1/_envs   {"name": "v2", "basedOn": "env.master"}

TWO CORRECTIONS TO ADR 0025, learned by actually running it:

1. **The clone brings the data.** `basedOn: env.master` is copy-on-write
   over the tables AND their rows, so there is no upload step. ADR 0025
   describes uploading a collection-typed schema plus fixtures; in
   practice `PUT /schema/{t}` answers
   `schema.create_failed: Table 'products' already exists`.

2. **What makes a table "v2" is its ENGINE, not its schema `type`.**
   `/api/v2` is engine-dispatched: a table still on `engine: v1` served
   over `/api/v2` runs the v1 ADAPTER, so pointing the demo at v2
   without migrating proves almost nothing — it exercises the
   compatibility path, not native Rep2. Migrate with:

       POST {url}/env/v2/api/v2/schema/{table}/_migrate  {"engine": "v2"}

   This is ALSO the real customer migration path: migrate the storage,
   change no application code, keep calling the same API.

Engine migration is IRREVERSIBLE per table — there is no reverse
migration. It is safe here only because it happens inside a cloned env:
`master` is untouched, and the whole env can be dropped and re-cloned:

    DELETE {url}/api/v1/_envs/v2

Writes are opt-in; `--dry-run` is the default precisely because this
targets the shared instance that fronts the public demo.
"""

from __future__ import annotations

import argparse
import sys

import httpx

from src.config import load_config
from src.data_loader import SCHEMAS


def tables_to_migrate() -> list[str]:
    """Every table the loader creates, in a stable order.

    Derived from `data_loader.SCHEMAS` so a table added to the demo can
    never be silently left behind on the old engine.
    """
    return sorted(SCHEMAS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="./do v2-env", description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="actually create the env and migrate (default is a dry run)",
    )
    parser.add_argument("--env", default=None, help="env name (default: v2)")
    parser.add_argument("--based-on", default="env.master")
    args = parser.parse_args(argv)

    cfg = load_config()
    env_name = args.env or (cfg.aito_env if cfg.use_v2 else "v2")

    if env_name == "master":
        print(
            "REFUSING: env name is 'master'. Engine migration is irreversible "
            "and this would migrate the LIVE demo. Pass --env <name>.",
            file=sys.stderr,
        )
        return 2

    tables = tables_to_migrate()
    env_base = f"{cfg.aito_api_url}/env/{env_name}/api/v2"

    print(f"  instance : {cfg.aito_api_url}")
    print(f"  env      : {env_name}  (basedOn {args.based_on})")
    print(f"  env base : {env_base}")
    print(f"  tables   : {len(tables)} -> {', '.join(tables)}")
    print(f"  mode     : {'APPLY (writes)' if args.apply else 'dry run (no HTTP)'}")

    if not args.apply:
        print(f"\n  would POST {cfg.aito_api_url}/api/v1/_envs")
        print(f'       {{"name": "{env_name}", "basedOn": "{args.based_on}"}}')
        print(f"\n  then for each table, POST {env_base}/schema/<table>/_migrate")
        print('       {"engine": "v2"}')
        print("\n  Re-run with --apply. Engine migration is IRREVERSIBLE per "
              "table (the env can be deleted and re-cloned; master is untouched).")
        return 0

    headers = {"x-api-key": cfg.aito_api_key, "content-type": "application/json"}
    with httpx.Client(headers=headers, timeout=300.0) as client:
        existing = client.get(f"{cfg.aito_api_url}/api/v1/_envs")
        existing.raise_for_status()
        names = {e.get("name") for e in existing.json().get("envs", [])}

        if env_name in names:
            print(f"  env '{env_name}' already exists — skipping create")
        else:
            print(f"  creating env '{env_name}' (clones tables + data)...")
            resp = client.post(
                f"{cfg.aito_api_url}/api/v1/_envs",
                json={"name": env_name, "basedOn": args.based_on},
            )
            if resp.status_code >= 400:
                print(f"  FAILED {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
                return 1

        failed = []
        for table in tables:
            resp = client.post(
                f"{env_base}/schema/{table}/_migrate", json={"engine": "v2"}
            )
            if resp.status_code >= 400:
                print(f"  {table}: FAILED {resp.status_code} {resp.text[:160]}")
                failed.append(table)
                continue
            body = resp.json()
            print(
                f"  {table}: {body.get('status')} "
                f"engine={body.get('engine')} rows={body.get('rows')}"
            )

        if failed:
            print(f"\n  {len(failed)} table(s) failed: {', '.join(failed)}",
                  file=sys.stderr)
            return 1

    print(f"\n  Done. Point the app at it with:  AITO_USE_V2=1 ./do dev")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
