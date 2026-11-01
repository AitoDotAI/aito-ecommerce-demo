"""Write the stored customer profiles (ADR 0053) from the release's fixtures. Offline: no Aito call.

    uv run python scripts/generate_customer_profiles.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.customer_profiles import build, stored_rows

OUT = ROOT / "data" / "customer_profiles"


def main() -> None:
    summary, traits, facts = build()
    OUT.mkdir(exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    (OUT / "customers.json").write_text(json.dumps(traits, separators=(",", ":"), ensure_ascii=False) + "\n")
    (OUT / "facts.json").write_text(json.dumps(facts, separators=(",", ":"), ensure_ascii=False) + "\n")
    (OUT / "rows.json").write_text(json.dumps(stored_rows(set(facts)), separators=(",", ":"), ensure_ascii=False) + "\n")
    print(f"Wrote data/customer_profiles/: {summary['profiled']} of {summary['customers']} customers profiled, release {summary['release']}")


main()
