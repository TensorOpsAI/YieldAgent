"""Build the campaign-setup graph with the LinkedIn MCP server wired in.

The graph itself is the platform-neutral one from `campaign_setup`. The only
LinkedIn-specific concern at this layer is which MCP server hosts
`publish_draft_campaign`.
"""

from __future__ import annotations

import sys

from langgraph.checkpoint.memory import MemorySaver

from yieldagent.agents.campaign_setup.graph import GetMcpTool
from yieldagent.agents.campaign_setup.graph import build_graph as _build_neutral_graph
from yieldagent.agents.defaults import DEFAULT_MODEL


def _default_linkedin_mcp_tool_loader() -> GetMcpTool:
    """Load tools from the LinkedIn MCP server spawned as a stdio subprocess."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {
            "linkedin": {
                "command": sys.executable,
                "args": ["-m", "yieldagent.integrations.linkedin.server"],
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
    """Compile the campaign-setup graph wired to the LinkedIn MCP server.

    Pass `get_mcp_tool` to swap the LinkedIn MCP server for a fake (used by
    --dry-run and tests).
    """
    return _build_neutral_graph(
        model_name=model_name,
        get_mcp_tool=get_mcp_tool or _default_linkedin_mcp_tool_loader(),
        checkpointer=checkpointer,
    )
