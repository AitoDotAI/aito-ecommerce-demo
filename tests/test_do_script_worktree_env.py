"""`./do` finds credentials from any git worktree.

A worktree is a fresh checkout, and the credentials file is gitignored, so
a worktree has none of its own. `./do` falls back to the main checkout's
files, says so, and lets a worktree's own file win. `./do target` prints
the Aito instance a command would use without touching it.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

DO_SCRIPT = Path(__file__).resolve().parent.parent / "do"
MAIN_URL = "http://main-checkout.test/instance"
OWN_URL = "http://worktree-own.test/instance"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd, check=True, capture_output=True,
    )


@pytest.fixture
def main_and_worktree(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    shutil.copy(DO_SCRIPT, main / "do")
    _git(main, "add", "do")
    _git(main, "commit", "-q", "-m", "init")
    worktree = tmp_path / "worktree"
    _git(main, "worktree", "add", "-q", str(worktree))
    return main, worktree


def _target(checkout: Path) -> str:
    # A developer's exported AITO_* variable would win over every file and
    # hide what is being tested.
    environment = {k: v for k, v in os.environ.items() if not k.startswith("AITO_")}
    result = subprocess.run(
        ["bash", "do", "target"], cwd=checkout, capture_output=True, text=True,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_worktree_without_credentials_uses_the_main_checkouts(main_and_worktree):
    main, worktree = main_and_worktree
    (main / ".env").write_text(f"AITO_API_URL={MAIN_URL}\n")

    output = _target(worktree)

    assert MAIN_URL in output
    assert str(main) in output, "the output must say where the credentials came from"


def test_worktree_with_its_own_credentials_ignores_the_main_checkouts(main_and_worktree):
    main, worktree = main_and_worktree
    (main / ".env").write_text(f"AITO_API_URL={MAIN_URL}\n")
    (worktree / ".env").write_text(f"AITO_API_URL={OWN_URL}\n")

    output = _target(worktree)

    assert OWN_URL in output
    assert MAIN_URL not in output


def test_worktree_env_local_overrides_the_main_checkouts_credentials(main_and_worktree):
    main, worktree = main_and_worktree
    (main / ".env").write_text(f"AITO_API_URL={MAIN_URL}\n")
    (worktree / ".env.local").write_text(f"AITO_API_URL={OWN_URL}\n")

    assert OWN_URL in _target(worktree)


def test_no_credentials_anywhere_reports_the_target_as_unset(main_and_worktree):
    _, worktree = main_and_worktree

    assert "<unset>" in _target(worktree)
