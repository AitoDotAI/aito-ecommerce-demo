"""Write the stored agent runs (ADR 0052) from the committed retention snapshot. Offline: no Aito call.

    uv run python scripts/generate_agent_runs.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.shopkeeper_run import RETENTION_SNAPSHOT, RUNS_DIR, rows_by_situation, build_winback_run, release_env


def main() -> None:
    snapshot = json.loads(RETENTION_SNAPSHOT.read_text())["data"]
    run = build_winback_run(snapshot, rows_by_situation(), release_env())
    RUNS_DIR.mkdir(exist_ok=True)
    path = RUNS_DIR / f"{run['id']}.json"
    path.write_text(json.dumps(run, indent=1, ensure_ascii=False) + "\n")
    print(f"Wrote {path.relative_to(RUNS_DIR.parent.parent)}: {len(run['steps'])} steps, release {run['release']}")


main()
