"""Shared CLI runner for the platform-neutral campaign-setup agents.

Both the Meta (`campaign_setup`) and LinkedIn (`linkedin_setup`) entry points
run the same graph — parse brief → plan → human gate → publish — differing only
in which MCP server they target and the dry-run stub they substitute. This
module holds that shared flow so each agent's `cli.py` is just configuration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.types import Command

from yieldagent.env import load_dotenv

from .defaults import DEFAULT_MODEL

# build_graph(*, model_name, get_mcp_tool, checkpointer) for the target platform.
GraphBuilder = Callable[..., Any]
# Zero-arg factory returning a `get_mcp_tool` loader that stubs the MCP server.
ToolLoaderFactory = Callable[[], Any]


def _print_audit(state: dict) -> None:
    for entry in state.get("audit", []):
        print(f"  [{entry['node']}] {entry['summary']}", file=sys.stderr)


async def _run(
    brief_path: Path,
    *,
    auto_approve: bool,
    dry_run: bool,
    model_name: str,
    platform: str,
    build_graph: GraphBuilder,
    dry_run_tool_loader: ToolLoaderFactory,
) -> int:
    graph = build_graph(
        model_name=model_name,
        get_mcp_tool=dry_run_tool_loader() if dry_run else None,
    )
    config = {"configurable": {"thread_id": str(uuid4())}}
    brief_text = brief_path.read_text()

    if dry_run:
        print(
            f"=== DRY RUN — {platform} MCP server replaced with stub; no API calls ===",
            file=sys.stderr,
        )

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


def run_cli(
    *,
    prog: str,
    platform: str,
    build_graph: GraphBuilder,
    dry_run_tool_loader: ToolLoaderFactory,
) -> int:
    """Parse argv and run the agent. Each entry point supplies its platform wiring."""
    load_dotenv()
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("brief", type=Path, help="Path to a markdown campaign brief")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip the human gate (CI / smoke tests only — never use against live accounts)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=f"Replace the {platform} MCP server with a stub. No {platform} credentials "
        f"needed; nothing is sent to {platform}. Use this to try the agent end-to-end "
        "before wiring up real ad accounts.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM model name")
    args = parser.parse_args()
    return asyncio.run(
        _run(
            args.brief,
            auto_approve=args.auto_approve,
            dry_run=args.dry_run,
            model_name=args.model,
            platform=platform,
            build_graph=build_graph,
            dry_run_tool_loader=dry_run_tool_loader,
        )
    )
