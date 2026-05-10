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

    if not api_url or not api_key:
        raise ValueError(
            "No Aito credentials found. Set AITO_API_URL + AITO_API_KEY in "
            ".env (copy from .env.example to get started)."
        )

    return Config(
        aito_api_url=api_url,
        aito_api_key=api_key,
        public_demo=public_demo,
    )
