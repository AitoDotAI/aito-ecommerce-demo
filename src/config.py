"""Configuration loaded from environment variables.

Single-tenant: one Aito DB serves the whole PetNord demo. The
multi-tenant routing in `aito-erp-demo` was dropped here intentionally
— see `docs/adr/0001-scaffold-and-stack.md`. If you ever need the
multi-tenant shape, lift it from `aito-erp-demo/src/config.py` whole;
don't half-implement it.

Fails loudly when no credentials are configured. The demo cannot do
anything useful without an Aito DB to talk to.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Fill the environment from a dotenv file without overriding it.

    A variable the caller set wins over the file, so
    `AITO_API_URL=http://localhost:8080 uv run ...` really reaches the
    local engine. This used `load_dotenv(override=True)`, where the file
    won: on 2026-09-20 a loader run pointed at localhost silently wrote to
    the production instance (shared.aito.ai) instead.

    An empty variable counts as unset, so a blank export still picks up
    the file's value rather than shadowing it.
    """
    for key, value in dotenv_values(path).items():
        if value is not None and not os.environ.get(key):
            os.environ[key] = value


@dataclass(frozen=True)
class Config:
    aito_api_url: str
    aito_api_key: str
    public_demo: bool
    # API v2 (Rep2) — ADR 0025, and the DEFAULT since 2026-09-16.
    # `AITO_USE_V2=0` opts back out to v1, which stays a supported path:
    # the compat layer keeps both working, and since master's storage is
    # rep2 the v1 endpoints reach it through the engine-dispatched
    # adapter — "migrate the storage, change no application code".
    use_v2: bool = True
    # `master` since 2026-09-23, when the staged `v2` env was PROMOTED
    # onto master (POST /_envs/v2/promote). There is no longer a separate
    # env to point at: master IS the migrated database. `AITO_ENV`
    # overrides for a feature-branch sandbox.
    aito_env: str = "master"

    @property
    def api_base(self) -> str:
        """The one base path every Aito call is built on.

        Named envs are addressed with an `/env/<name>` prefix; `master`
        is unprefixed. So:

            v1 / master → {url}/api/v1
            v2 / v2 env → {url}/env/v2/api/v2

        Assembling it here (rather than hardcoding `/api/v1` at the call
        site) is what makes the toggle total — no module may reintroduce
        a literal `/api/v1/`, which would silently opt its call out.
        """
        env_path = "" if self.aito_env == "master" else f"/env/{self.aito_env}"
        return f"{self.aito_api_url}{env_path}/api/{self.api_version}"

    @property
    def api_version(self) -> str:
        return "v2" if self.use_v2 else "v1"

    @property
    def api_namespace(self) -> str:
        """Identifies WHICH backend an answer came from — `v1@master`,
        `v2@v2`.

        Cached responses must be scoped by this. The two APIs return
        genuinely different answers from genuinely different data, so a
        cache keyed only on the question replays one version's answer
        under the other — silently, because both are well-formed. That
        is how a v2 run can look correct while serving v1's results.
        """
        return f"{self.api_version}@{self.aito_env}"


def load_config(*, use_dotenv: bool = True) -> Config:
    """Load config from environment, with `.env` file fallback.

    An explicitly set environment variable wins over `.env`.

    Set `use_dotenv=False` in tests to prevent `.env` from interfering
    with monkeypatched environment variables.
    """
    if use_dotenv:
        _load_dotenv(_PROJECT_ROOT / ".env")

    api_url = os.environ.get("AITO_API_URL", "").rstrip("/")
    api_key = os.environ.get("AITO_API_KEY", "")
    public_demo = os.environ.get("PUBLIC_DEMO", "").lower() in ("1", "true", "yes")
    # Default ON: only an explicit falsey value opts back out, so a
    # deployment that sets nothing gets v2.
    use_v2 = os.environ.get("AITO_USE_V2", "").lower() not in ("0", "false", "no")
    # Always `master` now: the staged `v2` env was promoted onto it, so
    # both versions address the same database and there is no second env
    # to keep in sync. `AITO_ENV` overrides for a sandbox env.
    aito_env = os.environ.get("AITO_ENV", "") or "master"

    if not api_url or not api_key:
        raise ValueError(
            "No Aito credentials found. Set AITO_API_URL + AITO_API_KEY in "
            ".env (copy from .env.example to get started)."
        )

    return Config(
        aito_api_url=api_url,
        aito_api_key=api_key,
        public_demo=public_demo,
        use_v2=use_v2,
        aito_env=aito_env,
    )


DEFAULT_API_NAMESPACE = "v2@master"


def current_api_namespace() -> str:
    """The active `version@env` namespace, read straight from the
    environment.

    Cheap and dotenv-free, for callers that must scope something before
    `load_config()` has run or without paying for it on every call —
    `cache` and `precompute_store` both key their entries on this.
    Mirrors `Config.api_namespace`; tests pin the two together so they
    cannot drift.
    """
    use_v2 = os.environ.get("AITO_USE_V2", "").lower() not in ("0", "false", "no")
    env = os.environ.get("AITO_ENV", "") or "master"
    return f"{'v2' if use_v2 else 'v1'}@{env}"
