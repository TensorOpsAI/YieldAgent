"""CLI entry point for the campaign-setup agent.

    python -m yieldagent.agents.campaign_setup briefs/example_brief.md
    python -m yieldagent.agents.campaign_setup briefs/example_brief.md --auto-approve

The default mode is interactive: the agent plans the draft, prints it, and asks
for approval on stdin before publishing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from langgraph.types import Command

from .graph import build_graph
from .nodes import DEFAULT_MODEL


def _print_audit(state: dict) -> None:
    for entry in state.get("audit", []):
        print(f"  [{entry['node']}] {entry['summary']}", file=sys.stderr)


async def _run(brief_path: Path, *, auto_approve: bool, model_name: str) -> int:
    graph = build_graph(model_name=model_name)
    config = {"configurable": {"thread_id": str(uuid4())}}
    brief_text = brief_path.read_text()

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
    parser = argparse.ArgumentParser(prog="yieldagent-campaign-setup")
    parser.add_argument("brief", type=Path, help="Path to a markdown campaign brief")
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip the human gate (CI / smoke tests only — never use against live accounts)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Claude model name")
    args = parser.parse_args()
    return asyncio.run(_run(args.brief, auto_approve=args.auto_approve, model_name=args.model))


if __name__ == "__main__":
    raise SystemExit(main())
