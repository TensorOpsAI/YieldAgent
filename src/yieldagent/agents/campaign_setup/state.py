"""Graph state for the campaign-setup agent."""

from __future__ import annotations

from typing import Any, TypedDict

from yieldagent.domain import Brief, Campaign


class AuditEntry(TypedDict):
    """One line in the agent's immutable action log.

    Pillar 6 of the YieldAgent foundation: every spend-affecting decision is
    recorded with its rationale so a human can reconstruct what happened.
    """

    node: str
    summary: str
    detail: dict[str, Any]


class AgentState(TypedDict, total=False):
    brief_text: str
    brief: Brief
    campaign: Campaign
    approved: bool
    publish_result: dict[str, Any]
    audit: list[AuditEntry]
