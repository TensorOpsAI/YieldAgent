"""LangGraph wiring for the campaign-setup agent.

Shape:

    START -> parse_brief -> plan_campaign -> human_gate -> publish_draft -> END
                                                       \\-> END (on reject)

The human_gate node calls `interrupt()`, so the graph pauses there until the
caller resumes with `Command(resume={"approved": bool, "reason": str})`.
"""

from __future__ import annotations

import sys
from typing import Awaitable, Callable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from yieldagent import domain

from .nodes import (
    DEFAULT_MODEL,
    human_gate,
    make_parse_brief_node,
    make_plan_campaign_node,
    make_publish_draft_node,
    route_after_gate,
)
from .state import AgentState

GetMcpTool = Callable[[str], Awaitable[object]]


def _default_checkpointer() -> MemorySaver:
    """In-memory checkpointer that knows how to (de)serialize our domain models.

    The graph state holds `Brief`/`Campaign` Pydantic models. Without an explicit
    allowlist langgraph warns on every checkpoint load that these types are
    "unregistered" (and will block them in a future version). Registering the
    domain types silences the warning and pins the set of types we trust to
    reconstruct from a checkpoint.
    """
    allowed = [getattr(domain, name) for name in domain.__all__]
    return MemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=allowed))


def _default_meta_mcp_tool_loader() -> GetMcpTool:
    """Load tools from the Meta MCP server spawned as a stdio subprocess."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {
            "meta": {
                "command": sys.executable,
                "args": ["-m", "yieldagent.integrations.meta.server"],
                "transport": "stdio",
            }
        }
    )

    async def get_tool(name: str):
        tools = await client.get_tools()
        for tool in tools:
            if tool.name == name:
                return tool
        raise RuntimeError(f"MCP tool {name!r} not found among {[t.name for t in tools]}")

    return get_tool


def build_graph(
    *,
    model_name: str = DEFAULT_MODEL,
    get_mcp_tool: GetMcpTool | None = None,
    checkpointer: MemorySaver | None = None,
):
    """Compile the campaign-setup graph.

    Pass `get_mcp_tool` to swap the Meta MCP server for a fake (used in tests).
    """
    builder = StateGraph(AgentState)
    builder.add_node("parse_brief", make_parse_brief_node(model_name))
    builder.add_node("plan_campaign", make_plan_campaign_node(model_name))
    builder.add_node("human_gate", human_gate)
    builder.add_node(
        "publish_draft",
        make_publish_draft_node(get_mcp_tool or _default_meta_mcp_tool_loader()),
    )

    builder.add_edge(START, "parse_brief")
    builder.add_edge("parse_brief", "plan_campaign")
    builder.add_edge("plan_campaign", "human_gate")
    builder.add_conditional_edges(
        "human_gate",
        route_after_gate,
        {"publish_draft": "publish_draft", "__end__": END},
    )
    builder.add_edge("publish_draft", END)

    return builder.compile(checkpointer=checkpointer or _default_checkpointer())
