"""Flow 3's agent reads one sandbox branch, read-only (ADR 0043).

`./do agent-demo <branch>` starts Claude Code with aito-mcp as its only
tools; Claude Code starts `scripts/agent-demo/aito-mcp-sandbox.sh` as the
MCP server. These tests run that launcher with a stand-in `uvx` that
records what it was started with, and check the fences:

- the agent's AITO_URL is the sandbox branch's env path, nothing else;
- the key comes from the read-only key file, is never printed, and no
  other Aito key or AITO_MCP_ALLOW_WRITES reaches aito-mcp;
- anything that isn't a sandbox branch, or a missing key, is refused.
"""

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
LAUNCHER = REPO / "scripts" / "agent-demo" / "aito-mcp-sandbox.sh"
BRANCH = "tmp-2026-10-26-11-30-00-3f9c2a1b7d4e6f80"
SANDBOX_DB = "https://shared.aito.ai/db/aito-ecommerce-sandbox"
READ_ONLY_KEY = "sandbox-read-only-key-for-the-test"


@pytest.fixture
def stand_in_uvx(tmp_path: Path) -> Path:
    """A `uvx` that writes its arguments and environment to a file, then exits."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "uvx-saw.txt"
    uvx = bin_dir / "uvx"
    uvx.write_text(f'#!/usr/bin/env bash\n{{ echo "ARGS $*"; env; }} > "{record}"\n')
    uvx.chmod(0o755)
    return record


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    path = tmp_path / "sandbox-readonly-key"
    path.write_text(READ_ONLY_KEY + "\n")
    path.chmod(0o600)
    return path


def launch(tmp_path: Path, **overrides: str) -> subprocess.CompletedProcess:
    environment = {
        "HOME": str(tmp_path), "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "SANDBOX_BRANCH": BRANCH, "SANDBOX_DB_URL": SANDBOX_DB,
        "SANDBOX_RO_KEY_FILE": str(tmp_path / "sandbox-readonly-key"),
        # What a developer's shell may hold: PetNord's key, the sandbox's
        # read-write key, and the switch that turns aito-mcp's writes on.
        "AITO_API_KEY": "petnord-key-must-not-reach-the-agent",
        "AITO_SANDBOX_API_KEY": "sandbox-read-write-key-must-not-reach-the-agent",
        "AITO_MCP_ALLOW_WRITES": "1",
    }
    environment.update(overrides)
    return subprocess.run(["bash", str(LAUNCHER)], env=environment, capture_output=True, text=True)


def test_the_agent_reads_the_sandbox_branch_with_the_read_only_key(tmp_path, stand_in_uvx, key_file):
    result = launch(tmp_path)

    assert result.returncode == 0, result.stderr
    saw = stand_in_uvx.read_text().splitlines()
    assert "ARGS aito-mcp@1.2.0" in saw
    assert f"AITO_URL={SANDBOX_DB}/env/{BRANCH}" in saw
    assert f"AITO_API_KEY={READ_ONLY_KEY}" in saw


def test_no_other_key_and_no_write_switch_reach_aito_mcp(tmp_path, stand_in_uvx, key_file):
    launch(tmp_path)

    saw = stand_in_uvx.read_text()
    assert "AITO_MCP_ALLOW_WRITES" not in saw, "aito-mcp's writes must stay off"
    assert "petnord-key" not in saw
    assert "AITO_SANDBOX_API_KEY" not in saw


def test_the_key_is_never_printed(tmp_path, stand_in_uvx, key_file):
    result = launch(tmp_path)

    assert READ_ONLY_KEY not in result.stdout + result.stderr


@pytest.mark.parametrize("branch", ["master", "env.master", "observable", "tmp-2026-10-26", BRANCH + "0"])
def test_anything_but_a_sandbox_branch_is_refused(tmp_path, stand_in_uvx, key_file, branch):
    result = launch(tmp_path, SANDBOX_BRANCH=branch)

    assert result.returncode != 0
    assert "not a sandbox branch" in result.stderr
    assert not stand_in_uvx.exists(), "aito-mcp must not start"


def test_petnords_database_is_refused(tmp_path, stand_in_uvx, key_file):
    result = launch(tmp_path, SANDBOX_DB_URL="https://shared.aito.ai/db/aito-ecommerce-demo")

    assert result.returncode != 0
    assert "doesn't name a sandbox database" in result.stderr
    assert not stand_in_uvx.exists()


def test_without_the_read_only_key_file_nothing_starts(tmp_path, stand_in_uvx):
    result = launch(tmp_path)

    assert result.returncode != 0
    assert "no read-only key" in result.stderr
    assert not stand_in_uvx.exists()


def test_do_agent_demo_refuses_without_the_key_file(tmp_path):
    # A copy of ./do outside any checkout, so no credentials file is read.
    do_copy = tmp_path / "do"
    do_copy.write_text((REPO / "do").read_text())
    environment = {k: v for k, v in os.environ.items() if not k.startswith(("AITO_", "SANDBOX_"))}
    environment["HOME"] = str(tmp_path)

    result = subprocess.run(["bash", str(do_copy), "agent-demo", BRANCH], cwd=tmp_path, env=environment,
                            capture_output=True, text=True)

    assert result.returncode != 0
    assert "REFUSING: no read-only key" in result.stderr
