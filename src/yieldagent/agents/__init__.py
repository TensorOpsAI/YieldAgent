"""YieldAgent agents.

Each agent is a LangGraph that consumes domain objects, calls platform MCP
servers via `langchain-mcp-adapters`, and pauses at human-approval gates before
taking any spend-affecting action.
"""
