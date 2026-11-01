"""Ask the store (ADR 0042): a merchant's question, answered by Claude with the lever tools.

The model reads through the tools in `ask_tools.py` and proposes: nothing here writes. The loop is
the Messages API's tool-use loop, bounded in turns, and every tool call is returned beside the
answer so a person can see which Aito queries it rested on.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass

import anthropic

from src.ask_tools import AskTool

MODEL = "claude-opus-5-5"
MAX_TURNS = 8
MAX_TOKENS = 8000

BRIEF = """You are the merchandising assistant of PetNord, a Nordic online pet store, answering the owner in the app. \
The store's memory is an Aito predictive database, reached through your tools: each wraps one of the app's owner views \
(Product what-if, Supply, Retention) and returns that view's numbers.

Answer with the tools. You are read-only: propose, never act. Quote only numbers a tool returned and say what each rests \
on (how many showings, which view); do no arithmetic of your own. A band or estimate marked thin has too little evidence: \
say so and recommend not acting yet. The offer's lift is learned across the whole shop, not for this product alone: say so \
when you quote it. End with at most three proposed actions, each with the view that shows its numbers (a tool result's \
`view`). Keep the answer under 180 words, in plain merchant language. If no tool can answer the question, say so."""


class AskError(RuntimeError):
    """The model couldn't answer: it declined, ran out of turns or tokens."""


@dataclass(frozen=True)
class ToolCall:
    name: str
    input: dict
    ms: int
    error: str | None = None
    result: object = None     # what the model was given back; a stored conversation shows it


@dataclass(frozen=True)
class Answer:
    answer: str
    tool_calls: list[ToolCall]
    model: str
    input_tokens: int
    output_tokens: int

    def to_dict(self) -> dict:
        return asdict(self)


def ask(question: str, tools: list[AskTool], client: anthropic.Anthropic, model: str = MODEL) -> Answer:
    """Run the tool-use loop for `question`."""
    by_name = {t.name: t for t in tools}
    messages: list[dict] = [{"role": "user", "content": question}]
    calls: list[ToolCall] = []
    input_tokens = output_tokens = 0
    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model=model, max_tokens=MAX_TOKENS, system=BRIEF, tools=[t.definition() for t in tools],
            thinking={"type": "adaptive"}, output_config={"effort": "medium"}, messages=messages)
        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens
        if response.stop_reason == "refusal":
            raise AskError("The model declined this question.")
        if response.stop_reason == "max_tokens":
            raise AskError("The answer ran past its length limit.")
        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content if b.type == "text")
            return Answer(text, calls, response.model, input_tokens, output_tokens)
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                results.append(_run(by_name, block, calls))
        messages.append({"role": "user", "content": results})
    raise AskError(f"No answer after {MAX_TURNS} rounds of tool calls.")


def _run(by_name: dict[str, AskTool], block, calls: list[ToolCall]) -> dict:
    """One tool call; a failure goes back to the model as an error result, and onto the record."""
    started = time.perf_counter()
    try:
        result = by_name[block.name].run(block.input)
        error = None
        content = json.dumps(result, default=str)
    except Exception as exc:    # noqa: BLE001: the model may recover (a wrong SKU); the person sees the error
        result = None
        error = f"{type(exc).__name__}: {exc}"
        content = error
    calls.append(ToolCall(block.name, block.input, int((time.perf_counter() - started) * 1000), error, result))
    return {"type": "tool_result", "tool_use_id": block.id, "content": content, **({"is_error": True} if error else {})}
