"""Stage the v2 (Rep2) migration in a separate Aito env — ADR 0025.

    ./do v2-env --dry-run     # show exactly what would be sent (default)
    ./do v2-env --apply       # actually create the env + upload

The live demo and every local checkout share ONE Aito instance, and the
Layer-2 prediction cache is a table on it. So v2 cannot be tried against
`master`: a collection-typed schema and experimental queries would
disturb the running demo. Instead we use Aito's envs feature — one
instance, several named envs — and clone a `v2` env from master:

    POST {url}/api/v1/_envs   {"name": "v2", "basedOn": "env.master"}

The env is then addressed at `{url}/env/v2/api/v2/...`, which is exactly
what `Config.api_base` assembles when `AITO_USE_V2=1`.

Schema is derived from `data_loader.SCHEMAS` rather than duplicated into
a `schema-v2.json`: the ONLY difference is `type: table` -> `collection`,
and a copy would drift the moment a column changes.

Writes are opt-in. `--dry-run` is the default precisely because this
targets the shared instance that fronts the public demo.
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

from src.config import load_config
from src.data_loader import SCHEMAS


def collection_schemas() -> dict[str, dict]:
    """`SCHEMAS` with every table retyped as a Rep2 collection.

    v1 declares `"type": "table"`; Rep2 declares `"type": "collection"`.
    Columns are identical — that is the point of the comparison.
    """
    out: dict[str, dict] = {}
    for table, schema in SCHEMAS.items():
        v2 = dict(schema)
        v2["type"] = "collection"
        out[table] = v2
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="./do v2-env", description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="actually create the env and upload (default is a dry run)",
    )
    parser.add_argument("--env", default=None, help="env name (default: v2)")
    parser.add_argument("--based-on", default="env.master")
    args = parser.parse_args(argv)

    cfg = load_config()
    env_name = args.env or (cfg.aito_env if cfg.use_v2 else "v2")

    if env_name == "master":
        print(
            "REFUSING: env name is 'master'. This uploads a collection-typed "
            "schema and would overwrite the live demo's data. Pass --env <name>.",
            file=sys.stderr,
        )
        return 2

    schemas = collection_schemas()
    env_base = f"{cfg.aito_api_url}/env/{env_name}/api/v2"

    print(f"  instance : {cfg.aito_api_url}")
    print(f"  env      : {env_name}  (basedOn {args.based_on})")
    print(f"  env base : {env_base}")
    print(f"  tables   : {len(schemas)} -> {', '.join(sorted(schemas))}")
    print(f"  mode     : {'APPLY (writes)' if args.apply else 'dry run (no HTTP)'}")

    if not args.apply:
        first = sorted(schemas)[0]
        print(f"\n  would POST {cfg.aito_api_url}/api/v1/_envs")
        print(f"       {json.dumps({'name': env_name, 'basedOn': args.based_on})}")
        print(f"\n  would PUT  {env_base}/schema/{first}")
        print(f"       {json.dumps(schemas[first])[:200]}...")
        print("\n  Re-run with --apply to execute. This writes to the SHARED "
              "instance that fronts the public demo.")
        return 0

    headers = {"x-api-key": cfg.aito_api_key, "content-type": "application/json"}
    with httpx.Client(headers=headers, timeout=90.0) as client:
        existing = client.get(f"{cfg.aito_api_url}/api/v1/_envs")
        existing.raise_for_status()
        names = {e.get("name") for e in existing.json().get("envs", [])}

        if env_name in names:
            print(f"  env '{env_name}' already exists — skipping create")
        else:
            print(f"  creating env '{env_name}'...")
            resp = client.post(
                f"{cfg.aito_api_url}/api/v1/_envs",
                json={"name": env_name, "basedOn": args.based_on},
            )
            if resp.status_code >= 400:
                print(f"  FAILED {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
                return 1

        for table, schema in schemas.items():
            print(f"  PUT schema/{table} (collection)...")
            resp = client.put(f"{env_base}/schema/{table}", json=schema)
            if resp.status_code >= 400:
                print(f"  FAILED {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
                return 1

    print("\n  Schema staged. Data upload is the next step (see ADR 0025).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
