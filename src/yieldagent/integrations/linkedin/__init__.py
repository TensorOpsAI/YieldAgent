"""LinkedIn Marketing API integration.

Exposed as an MCP server (`python -m yieldagent.integrations.linkedin.server`)
so the campaign-setup agent — and any other MCP client — can drive LinkedIn
through a stable, audited tool surface.

Safety model differs from Meta: LinkedIn has no test-account concept, so the
integration requires an explicit `LINKEDIN_ALLOWED_AD_ACCOUNTS` allowlist and
creates everything as `DRAFT` status by default. Drafts must be activated
manually in LinkedIn Campaign Manager — there is no API path from agent action
to live spend.
"""

from .client import LinkedInClient, LinkedInError, client_from_env
from .config import LinkedInConfig

__all__ = ["LinkedInClient", "LinkedInConfig", "LinkedInError", "client_from_env"]
