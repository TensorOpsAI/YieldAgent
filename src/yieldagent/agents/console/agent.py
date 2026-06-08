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

from yieldagent.agents.console.llm import console_model_name
from yieldagent.agents.console.prompts import console_system_prompt
from yieldagent.agents.console.tools import CONSOLE_TOOLS
from yieldagent.agents.defaults import resolve_model_name

# One checkpointer shared across all model variants, so a conversation (and its
# pending approval interrupt) survives even if the operator switches model
# mid-thread. Agents are cached per model name.
_CHECKPOINTER = MemorySaver()
_AGENTS: dict[str, Any] = {}


def get_console_agent(model_name: str | None = None) -> Any:
    name = model_name or console_model_name()
    if name not in _AGENTS:
        model = init_chat_model(resolve_model_name(name))
        _AGENTS[name] = create_react_agent(
            model,
            CONSOLE_TOOLS,
            prompt=console_system_prompt(),
            checkpointer=_CHECKPOINTER,
        )
    return _AGENTS[name]
