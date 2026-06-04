"""The console agent: a tool-using conversational planner (M1).

A LangGraph ReAct agent (LLM + the console tools) with a checkpointer, so a
conversation — and its pending approval interrupt — persist across HTTP turns by
`thread_id`. Built once and reused so the in-memory checkpoint survives between
the initial request and the approval resume.
"""

from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from yieldagent.agents.console.chat import console_model_name
from yieldagent.agents.console.prompts import CONSOLE_SYSTEM_PROMPT
from yieldagent.agents.console.tools import CONSOLE_TOOLS
from yieldagent.agents.defaults import resolve_model_name

_AGENT: Any = None


def get_console_agent() -> Any:
    global _AGENT
    if _AGENT is None:
        model = init_chat_model(resolve_model_name(console_model_name()))
        _AGENT = create_react_agent(
            model,
            CONSOLE_TOOLS,
            prompt=CONSOLE_SYSTEM_PROMPT,
            checkpointer=MemorySaver(),
        )
    return _AGENT
