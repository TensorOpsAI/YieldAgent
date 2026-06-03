"""CLI entry point for the Meta campaign-setup agent.

    python -m yieldagent.agents.campaign_setup briefs/example_brief.md
    python -m yieldagent.agents.campaign_setup briefs/example_brief.md --auto-approve
    python -m yieldagent.agents.campaign_setup briefs/example_brief.md --dry-run

Interactive by default: the agent plans the draft, prints it, and asks for
approval on stdin before publishing. --dry-run swaps the Meta MCP server for a
stub so you can see the agent run end-to-end without Meta credentials. The
shared flow lives in `yieldagent.agents._cli`; this module only supplies the
Meta wiring.
"""

from __future__ import annotations

from typing import Any

from yieldagent.agents._cli import run_cli

from .graph import build_graph


def _make_dry_run_tool_loader():
    """Stub MCP tool loader for --dry-run: synthesizes plausible Meta IDs, no network calls."""

    async def get_tool(name: str):
        class StubTool:
            async def ainvoke(self, payload: dict[str, Any]) -> dict[str, Any]:
                if name != "publish_draft_campaign":
                    return {}
                campaign = payload.get("campaign", {})
                return {
                    "campaign_id": "dryrun_campaign_000",
                    "line_items": [
                        {"name": li["name"], "id": f"dryrun_adset_{i:03d}"}
                        for i, li in enumerate(campaign.get("line_items", []))
                    ],
                    "ads": [
                        {"name": ad["name"], "id": f"dryrun_ad_{i:03d}"}
                        for i, ad in enumerate(campaign.get("ads", []))
                    ],
                }

        return StubTool()

    return get_tool


def main() -> int:
    return run_cli(
        prog="yieldagent-campaign-setup",
        platform="Meta",
        build_graph=build_graph,
        dry_run_tool_loader=_make_dry_run_tool_loader,
    )


if __name__ == "__main__":
    raise SystemExit(main())
