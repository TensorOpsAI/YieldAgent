"""Adapt the console agent's streamed output into the SSE event contract.

`run()` starts a turn from a user message; `resume()` continues a paused turn
after the operator approves/rejects a proposal. Both yield `(event, payload)`
pairs the API turns into SSE: token / tool_call / tool_result / proposal /
created.
"""

from __future__ import annotations

import ast
import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from yieldagent.agents.console.agent import get_console_agent
from yieldagent.agents.console.llm import delta_text

Event = tuple[str, dict[str, Any]]


def _coerce(content: Any) -> Any:
    """Tool results arrive as strings; recover the original object if we can.

    Handles both JSON (double-quoted) and Python-repr (single-quoted) dicts, so a
    dict-returning tool's result is usable by the UI.
    """
    if isinstance(content, str):
        for parse in (json.loads, ast.literal_eval):
            try:
                return parse(content)
            except (ValueError, SyntaxError, TypeError):
                continue
        return content
    return content


def _summarize(content: Any) -> str:
    text = content if isinstance(content, str) else json.dumps(content, default=str)
    return text if len(text) <= 300 else text[:297] + "…"


async def _drive(inp: Any, thread_id: str, model: str | None) -> AsyncIterator[Event]:
    agent = get_console_agent(model)
    config = {"configurable": {"thread_id": thread_id}}
    async for mode, chunk in agent.astream(
        inp, config, stream_mode=["messages", "updates"]
    ):
        if mode == "messages":
            msg, _meta = chunk
            if getattr(msg, "type", "") == "AIMessageChunk":
                text = delta_text(getattr(msg, "content", ""))
                if text:
                    yield ("token", {"text": text})
            continue

        # mode == "updates"
        for node, update in chunk.items():
            if node == "__interrupt__":
                value = getattr(update[0], "value", {}) or {}
                yield (
                    "proposal",
                    {
                        "campaign": value.get("campaign", {}),
                        "unresolved": value.get("unresolved", {}),
                    },
                )
                continue
            if not isinstance(update, dict):
                continue
            for message in update.get("messages", []):
                for call in getattr(message, "tool_calls", None) or []:
                    yield ("tool_call", {"name": call["name"], "args": call.get("args", {})})
                if getattr(message, "type", "") == "tool":
                    name = getattr(message, "name", "")
                    content = getattr(message, "content", "")
                    if name == "create_linkedin_draft":
                        result = _coerce(content)
                        if isinstance(result, dict) and result.get("created"):
                            yield ("created", {"result": result})
                        else:
                            msg = (
                                result.get("error")
                                if isinstance(result, dict)
                                else str(result)
                            ) or "Creating the draft failed."
                            yield ("error", {"message": msg})
                    else:
                        yield ("tool_result", {"name": name, "summary": _summarize(content)})


def run(message: str, thread_id: str, model: str | None = None) -> AsyncIterator[Event]:
    return _drive({"messages": [HumanMessage(content=message)]}, thread_id, model)


def resume(
    thread_id: str, approved: bool, reason: str | None, model: str | None = None
) -> AsyncIterator[Event]:
    return _drive(
        Command(resume={"approved": approved, "reason": reason or ""}), thread_id, model
    )
