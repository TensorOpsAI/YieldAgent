"""CLI entry point for the LinkedIn campaign-setup agent.

    python -m yieldagent.agents.linkedin_setup briefs/example_linkedin_brief.md
    python -m yieldagent.agents.linkedin_setup briefs/example_linkedin_brief.md --auto-approve
    python -m yieldagent.agents.linkedin_setup briefs/example_linkedin_brief.md --dry-run

Interactive by default: the agent plans the draft, prints it, and asks for
approval on stdin before publishing. --dry-run swaps the LinkedIn MCP server for
a stub so you can see the agent run end-to-end without LinkedIn credentials. The
shared flow lives in `yieldagent.agents._cli`; this module only supplies the
LinkedIn wiring.
"""

from __future__ import annotations

from typing import Any

from yieldagent.agents._cli import run_cli

from .graph import build_graph


def _make_dry_run_tool_loader():
    """Stub MCP tool loader for --dry-run: synthesizes plausible URNs, no network calls."""

    async def get_tool(name: str):
        class StubTool:
            async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
                if name != "publish_draft_campaign":
                    return {}
                campaign = payload.get("campaign", {})
                line_items = campaign.get("line_items", [])
                ads = campaign.get("ads", [])
                group_id = "100000000"
                return {
                    "campaign_id": group_id,
                    "campaign_group_urn": f"urn:li:sponsoredCampaignGroup:{group_id}",
                    "line_items": [
                        {
                            "name": li["name"],
                            "id": f"20000000{i}",
                            "urn": f"urn:li:sponsoredCampaign:20000000{i}",
                        }
                        for i, li in enumerate(line_items)
                    ],
                    "ads": [
                        {
                            "name": ad["name"],
                            "id": f"30000000{i}",
                            "campaign_urn": f"urn:li:sponsoredCampaign:20000000{0}",
                        }
                        for i, ad in enumerate(ads)
                    ],
                    "notes": {
                        "dry_run": "These URNs are synthesized; nothing was sent to LinkedIn.",
                    },
                }

        return StubTool()

    return get_tool


def main() -> int:
    return run_cli(
        prog="yieldagent-linkedin-setup",
        platform="LinkedIn",
        build_graph=build_graph,
        dry_run_tool_loader=_make_dry_run_tool_loader,
    )


if __name__ == "__main__":
    raise SystemExit(main())
