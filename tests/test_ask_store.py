"""Ask the store's loop (src/ask_store.py), against a scripted stand-in for the Messages API.

There is no live model here: each test scripts the model's turns and checks what the loop does
with them. A real call is the live check, run once a key is configured.
"""

from types import SimpleNamespace as NS

import pytest

from src.ask_store import MAX_TURNS, AskError, ask
from src.ask_tools import AskTool


def _tool_use(name, args, id="tu_1"):
    return NS(type="tool_use", name=name, input=args, id=id)


def _turn(content, stop_reason, model="claude-opus-5-5"):
    return NS(content=content, stop_reason=stop_reason, model=model, usage=NS(input_tokens=100, output_tokens=20))


class Scripted:
    """A client whose `messages.create` plays the scripted turns and records the requests."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.requests = []
        self.messages = self

    def create(self, **request):
        self.requests.append({**request, "messages": list(request["messages"])})
        return self.turns.pop(0)


def _tools(run):
    return [AskTool("offer_what_if", "d", {"type": "object", "properties": {}}, run)]


def test_a_tool_call_runs_and_its_result_goes_back_to_the_model():
    client = Scripted(_turn([_tool_use("offer_what_if", {"sku": "S"})], "tool_use"),
                      _turn([NS(type="text", text="Put S on offer.")], "end_turn"))

    answer = ask("What next?", _tools(lambda args: {"sku": args["sku"], "thin": False}), client)

    assert answer.answer == "Put S on offer."
    assert [(c.name, c.input, c.error) for c in answer.tool_calls] == [("offer_what_if", {"sku": "S"}, None)]
    sent_back = client.requests[1]["messages"][-1]["content"][0]
    assert sent_back["tool_use_id"] == "tu_1" and '"thin": false' in sent_back["content"]
    assert (answer.input_tokens, answer.output_tokens) == (200, 40)


def test_the_request_carries_the_brief_the_tools_and_adaptive_thinking():
    client = Scripted(_turn([NS(type="text", text="ok")], "end_turn"))

    ask("Q?", _tools(lambda args: {}), client)

    request = client.requests[0]
    assert "read-only" in request["system"] and "do no arithmetic" in request["system"]
    assert [t["name"] for t in request["tools"]] == ["offer_what_if"]
    assert request["thinking"] == {"type": "adaptive"} and request["model"] == "claude-opus-5-5"


def test_a_failing_tool_goes_back_as_an_error_result_and_is_recorded():
    def broken(args):
        raise ValueError("No product S")
    client = Scripted(_turn([_tool_use("offer_what_if", {"sku": "S"})], "tool_use"),
                      _turn([NS(type="text", text="That SKU isn't in the catalogue.")], "end_turn"))

    answer = ask("Q?", _tools(broken), client)

    assert answer.tool_calls[0].error == "ValueError: No product S"
    assert client.requests[1]["messages"][-1]["content"][0]["is_error"] is True


def test_a_refusal_is_an_error_not_an_empty_answer():
    with pytest.raises(AskError, match="declined"):
        ask("Q?", _tools(lambda args: {}), Scripted(_turn([], "refusal")))


def test_a_cut_off_answer_is_an_error():
    with pytest.raises(AskError, match="length limit"):
        ask("Q?", _tools(lambda args: {}), Scripted(_turn([NS(type="text", text="Half an")], "max_tokens")))


def test_a_model_that_never_stops_calling_tools_is_stopped():
    client = Scripted(*[_turn([_tool_use("offer_what_if", {})], "tool_use") for _ in range(MAX_TURNS)])

    with pytest.raises(AskError, match=f"{MAX_TURNS} rounds"):
        ask("Q?", _tools(lambda args: {}), client)
