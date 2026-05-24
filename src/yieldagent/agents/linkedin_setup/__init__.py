"""Campaign-setup agent for LinkedIn Ads.

Reuses the platform-neutral `campaign_setup` graph (parse_brief → plan_campaign
→ human_gate → publish_draft) and wires it to the LinkedIn MCP server. Drafts
are created as `DRAFT` status on LinkedIn — nothing can spend without a manual
activation step in LinkedIn Campaign Manager.
"""

from .graph import build_graph

__all__ = ["build_graph"]
