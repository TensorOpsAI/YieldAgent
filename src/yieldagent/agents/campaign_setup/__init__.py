"""Campaign-setup agent — first vertical slice.

Reads a markdown brief, plans a platform-neutral draft Campaign, pauses for
human approval, then publishes the draft to Meta (paused) via the Meta MCP
server.
"""

from .graph import build_graph
from .state import AgentState

__all__ = ["AgentState", "build_graph"]
