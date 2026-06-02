"""CLI entry point for the campaign-setup agent.

    python -m yieldagent.agents.campaign_setup briefs/example_brief.md
    python -m yieldagent.agents.campaign_setup briefs/example_brief.md --auto-approve
    python -m yieldagent.agents.campaign_setup briefs/example_brief.md --dry-run

The default mode is interactive: the agent plans the draft, prints it, and asks
for approval on stdin before publishing. --dry-run swaps the Meta MCP server for
a stub so you can see the agent run end-to-end without Meta credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.types import Command

from yieldagent.env import load_dotenv

from .graph import build_graph
from .nodes import DEFAULT_MODEL


def _print_audit(state: dict) -> None:
    for entry in state.get("audit", []):
        print(f"  [{entry['node']}] {entry['summary']}", file=sys.stderr)


def _make_dry_run_tool_loader():
    """Stub MCP tool loader for --dry-run: synthesizes plausible IDs, no network calls."""

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


async def _run(brief_path: Path, *, auto_approve: bool, dry_run: bool, model_name: str) -> int:
    graph = build_graph(
        model_name=model_name,
        get_mcp_tool=_make_dry_run_tool_loader() if dry_run else None,
    )
    config = {"configurable": {"thread_id": str(uuid4())}}
    brief_text = brief_path.read_text()

    if dry_run:
        print("=== DRY RUN — Meta MCP server replaced with stub; no API calls ===", file=sys.stderr)

    state = await graph.ainvoke({"brief_text": brief_text}, config=config)

    if "__interrupt__" not in state and "campaign" not in state:
        print("Agent stopped before reaching the approval gate.", file=sys.stderr)
        _print_audit(state)
        return 1

    campaign = state["campaign"]
    print("\n=== Planned draft campaign ===\n", file=sys.stderr)
    print(json.dumps(campaign.model_dump(mode="json"), indent=2))

    if auto_approve:
        approved, reason = True, ""
    else:
        print("\nApprove and publish? [y/N] ", end="", file=sys.stderr, flush=True)
        choice = sys.stdin.readline().strip().lower()
        approved = choice in {"y", "yes"}
        reason = "" if approved else "rejected by operator"

    final = await graph.ainvoke(
        Command(resume={"approved": approved, "reason": reason}), config=config
    )
    _print_audit(final)

    if approved:
        print("\n=== Publish result ===\n", file=sys.stderr)
        print(json.dumps(final.get("publish_result", {}), indent=2))
        return 0
    print("\nDraft rejected — nothing published.", file=sys.stderr)
    return 0


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="yieldagent-campaign-setup")
    parser.add_argument("brief", type=Path, help="Path to a markdown campaign brief")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip the human gate (CI / smoke tests only — never use against live accounts)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Replace the Meta MCP server with a stub. No Meta credentials needed; "
        "nothing is sent to Meta. Use this to try the agent end-to-end before "
        "wiring up real ad accounts.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Claude model name")
    args = parser.parse_args()
    return asyncio.run(
        _run(
            args.brief,
            auto_approve=args.auto_approve,
            dry_run=args.dry_run,
            model_name=args.model,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
