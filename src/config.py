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

from dotenv import load_dotenv


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    aito_api_url: str
    aito_api_key: str
    public_demo: bool
    # API v2 (Rep2) staging — ADR 0025. Off by default: the live demo
    # keeps serving v1 against `master`.
    use_v2: bool = False
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
        version = "v2" if self.use_v2 else "v1"
        return f"{self.aito_api_url}{env_path}/api/{version}"


def load_config(*, use_dotenv: bool = True) -> Config:
    """Load config from environment, with `.env` file fallback.

    Set `use_dotenv=False` in tests to prevent `.env` from interfering
    with monkeypatched environment variables.
    """
    if use_dotenv:
        load_dotenv(_PROJECT_ROOT / ".env", override=True)

    api_url = os.environ.get("AITO_API_URL", "").rstrip("/")
    api_key = os.environ.get("AITO_API_KEY", "")
    public_demo = os.environ.get("PUBLIC_DEMO", "").lower() in ("1", "true", "yes")
    use_v2 = os.environ.get("AITO_USE_V2", "").lower() in ("1", "true", "yes")
    # The env defaults to the version's home: v1 lives in `master`, v2 in
    # the `v2` env cloned from it. `AITO_ENV` overrides for a
    # feature-branch sandbox env.
    aito_env = os.environ.get("AITO_ENV", "") or ("v2" if use_v2 else "master")

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
