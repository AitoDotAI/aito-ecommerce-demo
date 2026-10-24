"""The committed result files behind the Evidence pages (ADR 0037 §2).

Each file says what produced its numbers: the command, the run's date, the
Aito env and engine version, and the commit of the code that ran. A page
reads the file; it never runs a benchmark live.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

from src.aito_client import AitoClient

EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "data" / "evidence"
ENTRIES = ("search-relevance", "model-checks", "personalised-search")


def run_info(client: AitoClient | None, command: str) -> dict:
    """Provenance for a run. `client` is None for a file derived offline."""
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                            cwd=EVIDENCE_DIR.parent.parent, check=True).stdout.strip()
    info = {"command": command, "date": date.today().isoformat(), "code_commit": commit}
    if client is not None:
        info.update({"aito_env": client._config.aito_env, "aito_api": client._config.api_namespace,
                     "aito_version": client.engine_version()})
    return info


def write(entry: str, result: dict) -> Path:
    if entry not in ENTRIES:
        raise ValueError(f"No Evidence entry {entry!r}; known: {', '.join(ENTRIES)}")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{entry}.json"
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read(entry: str) -> dict:
    if entry not in ENTRIES:
        raise KeyError(f"No Evidence entry {entry!r}; known: {', '.join(ENTRIES)}")
    path = EVIDENCE_DIR / f"{entry}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing: run `./do evidence {entry}`")
    return json.loads(path.read_text(encoding="utf-8"))
