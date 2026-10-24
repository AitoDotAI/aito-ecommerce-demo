"""The sandbox database the levers write to (ADR 0043 and its amendments).

On shared.aito.ai a key authenticates only under its own `/db/<name>/`
path, so the sandbox is a database of its own, with its own read-write
key. Its master is the template, loaded once from the release fixtures;
each sandbox is a throwaway branch of it (`src/sandbox_envs.py`).

    AITO_SANDBOX_URL=https://shared.aito.ai/db/aito-ecommerce-sandbox
    AITO_SANDBOX_API_KEY=<the sandbox database's read-write key>
    ADMIN_TOKEN=<a long random string: who may press "New sandbox">

Sandbox mode exists only when both AITO_SANDBOX_* are set AND the URL's
database name contains "sandbox" and isn't PetNord's. Anything else leaves
it off: every sandbox route answers 404 and the app reads PetNord only.
Without ADMIN_TOKEN the browser can't create a sandbox (`./do sandbox-new`
still can, from the operator's shell).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from urllib.parse import urlparse

from src.config import Config

SANDBOX_MARKER = "sandbox"


def database_name(url: str) -> str | None:
    """`https://shared.aito.ai/db/aito-ecommerce-sandbox` → `aito-ecommerce-sandbox`;
    None for a URL without a `/db/<name>` path (a local engine)."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "db":
        return parts[1]
    return None


@dataclass(frozen=True)
class SandboxSetting:
    """What the settings say: the sandbox database's `Config`, or why there is none."""
    config: Config | None       # its master env: the template
    off_reason: str | None      # None when sandbox mode is on
    admin_token: str | None     # None: "New sandbox" is off in the browser

    @property
    def database(self) -> str | None:
        return database_name(self.config.aito_api_url) if self.config else None


def load_sandbox_setting(petnord: Config) -> SandboxSetting:
    """Sandbox mode is on only when both settings are set and the URL names a
    sandbox database other than PetNord's. Otherwise it is off, with the
    reason, which start-up prints."""
    url = os.environ.get("AITO_SANDBOX_URL", "").rstrip("/")
    key = os.environ.get("AITO_SANDBOX_API_KEY", "")
    token = os.environ.get("ADMIN_TOKEN", "") or None
    if not url or not key:
        return SandboxSetting(None, "AITO_SANDBOX_URL and AITO_SANDBOX_API_KEY are not both set", None)
    name = database_name(url)
    if name is None or SANDBOX_MARKER not in name:
        return SandboxSetting(None, f"AITO_SANDBOX_URL {url!r} doesn't name a sandbox database "
                                    f"(its /db/<name> must contain {SANDBOX_MARKER!r})", None)
    if url == petnord.aito_api_url:
        return SandboxSetting(None, f"AITO_SANDBOX_URL is PetNord's database URL ({url})", None)
    return SandboxSetting(replace(petnord, aito_api_url=url, aito_api_key=key, aito_env="master"), None, token)
