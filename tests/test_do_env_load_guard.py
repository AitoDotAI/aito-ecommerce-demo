"""`./do env-load` loads a data release into a named env, never into master.

It drops and reloads every table, so it refuses before any write when
AITO_ENV is unset or `master` (ADR 0035: a release reaches master only
through the promote). The loader refuses too, in case it is called directly.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# Not a reachable instance: a refusal must come before any connection.
UNREACHABLE = {"AITO_API_URL": "http://127.0.0.1:9/never", "AITO_API_KEY": "unused"}


def _run(command: list[str], aito_env: str | None) -> subprocess.CompletedProcess:
    environment = {k: v for k, v in os.environ.items() if not k.startswith("AITO_")} | UNREACHABLE
    if aito_env is not None:
        environment["AITO_ENV"] = aito_env
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, env=environment, timeout=60)


@pytest.mark.parametrize("aito_env", [None, "", "master"])
def test_env_load_refuses_master(aito_env):
    result = _run(["bash", "do", "env-load"], aito_env)
    assert result.returncode != 0
    assert "REFUSING 'env-load'" in result.stdout


def test_the_loader_refuses_master_when_asked_to():
    result = _run([sys.executable, "-m", "src.data_loader", "--reset", "--refuse-master"], "master")
    assert result.returncode != 0
    assert "Refusing" in result.stdout
