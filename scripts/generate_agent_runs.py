"""Write the stored agent runs (ADRs 0052 and 0057) from the committed retention and supply snapshots. Offline: no Aito call.

    uv run python scripts/generate_agent_runs.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.shopkeeper_run import RETENTION_SNAPSHOT, RUNS_DIR, rows_by_situation, build_winback_run, release_env
from src.shopkeeper_stock import SUPPLY_SNAPSHOT, build_stock_run


def main() -> None:
    snapshot = json.loads(RETENTION_SNAPSHOT.read_text())["data"]
    runs = [build_winback_run(snapshot, rows_by_situation(), release_env()),
            build_stock_run(json.loads(SUPPLY_SNAPSHOT.read_text())["data"], release_env())]
    RUNS_DIR.mkdir(exist_ok=True)
    for run in runs:
        path = RUNS_DIR / f"{run['id']}.json"
        path.write_text(json.dumps(run, indent=1, ensure_ascii=False) + "\n")
        print(f"Wrote {path.relative_to(RUNS_DIR.parent.parent)}: {len(run['steps'])} steps, release {run['release']}")


main()
