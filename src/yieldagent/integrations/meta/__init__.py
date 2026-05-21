"""Meta (Facebook + Instagram) Marketing API integration.

Exposed as an MCP server (`python -m yieldagent.integrations.meta.server`) so the
campaign-setup agent — and any other MCP client — can drive Meta through a
stable, audited tool surface.
"""

from .client import MetaClient, MetaError
from .config import MetaConfig

__all__ = ["MetaClient", "MetaConfig", "MetaError"]
