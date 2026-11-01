"""Store the Ask-the-store conversations a demo should have (ADR 0054), the ones that are missing.

    ./do record-conversations                 every predefined question without a stored conversation
    ./do record-conversations "A question?"   that one question, stored beside them

Each answer is a model run, so it costs money: the Anthropic key and the admin token come from the project's
dotenv file (the same ones the server uses), and nothing is called when every predefined question is stored.
The app runs in this process against the Aito database that file names; nothing is written to it.
"""

import datetime
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import ask_conversations
from src.config import _PROJECT_ROOT, _load_dotenv
from src.shopkeeper_run import release_env

ADMIN_HEADER = "X-Admin-Token"


def main() -> None:
    questions = sys.argv[1:] or ask_conversations.missing_questions()
    if not questions:
        print("Every predefined conversation is stored.")
        return
    _load_dotenv(_PROJECT_ROOT / ".env")
    missing = [name for name in ("ANTHROPIC_API_KEY", "ADMIN_TOKEN") if not os.environ.get(name)]
    if missing:
        sys.exit(f"Set {' and '.join(missing)} in the project's dotenv file: Ask is off without them.")
    os.environ.setdefault("AITO_SKIP_STARTUP_WARMUP", "1")

    from fastapi.testclient import TestClient
    from src.app import app

    with TestClient(app) as client:
        for question in questions:
            asked_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            response = client.post("/api/ask", json={"question": question}, headers={ADMIN_HEADER: os.environ["ADMIN_TOKEN"]})
            if response.status_code != 200:
                sys.exit(f"Ask answered {response.status_code} for {question!r}: {response.text[:300]}")
            answer = response.json()
            stored = ask_conversations.save(question, answer, asked_at, release_env())
            print(f"Stored {stored}: {len(answer['tool_calls'])} tool calls, {answer['input_tokens'] + answer['output_tokens']} tokens")


if __name__ == "__main__":
    main()
