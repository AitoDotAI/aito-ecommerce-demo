"""Store one Ask-the-store conversation (ADR 0054) from a running server where Ask is on.

    ADMIN_TOKEN=... uv run python scripts/record_conversation.py "What should I reorder this week?" [--base http://localhost:8641]

The call costs a model run, so it is the presenter's: the token is read from the environment, never from a file.
"""

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import ask_conversations
from src.shopkeeper_run import release_env


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--base", default="http://localhost:8641")
    args = parser.parse_args()
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        sys.exit("Set ADMIN_TOKEN to the server's admin token.")
    request = urllib.request.Request(f"{args.base}/api/ask", data=json.dumps({"question": args.question}).encode(),
                                     headers={"Content-Type": "application/json", "X-Admin-Token": token})
    asked_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            answer = json.load(response)
    except urllib.error.HTTPError as exc:
        sys.exit(f"{args.base}/api/ask answered {exc.code}: {exc.read().decode()[:300]}")
    conversation_id = ask_conversations.save(args.question, answer, asked_at, release_env())
    print(f"Stored {conversation_id}: {len(answer['tool_calls'])} tool calls, {answer['input_tokens'] + answer['output_tokens']} tokens")


if __name__ == "__main__":
    main()
