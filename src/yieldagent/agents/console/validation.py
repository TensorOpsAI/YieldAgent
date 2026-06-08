"""Completeness check for a conversationally-built campaign.

The conversation replaces the markdown brief, so the agent must gather every
detail the platform needs. This reuses the SAME domain model the brief used as
the single source of truth — then adds the semantic checks the model can't
express (at least one line item and ad, ads point at real line items, every
creative has a usable source). `propose_campaign` calls this and refuses to
present an incomplete draft, so the agent is forced to ask for what's missing.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from yieldagent.domain import Campaign, CampaignPlan


def campaign_issues(data: dict[str, Any]) -> list[str]:
    """Return human-readable issues blocking creation; empty list means ready.

    No budget ceiling: the operator always reviews the budget in the proposal,
    and nothing spends until a manual activation in Campaign Manager — so a hard
    cap would only add friction.
    """
    try:
        campaign = Campaign.model_validate(data)
    except ValidationError as exc:
        return [
            f"{'.'.join(str(p) for p in err['loc']) or 'campaign'}: {err['msg']}"
            for err in exc.errors()
        ]

    issues: list[str] = []
    if not campaign.line_items:
        issues.append("Add at least one line item (budget, flight dates, targeting).")
    if not campaign.ads:
        issues.append("Add at least one ad / creative.")

    line_item_names = {li.name for li in campaign.line_items}
    for ad in campaign.ads:
        if ad.line_item_name not in line_item_names:
            issues.append(
                f"Ad {ad.name!r} references unknown line item {ad.line_item_name!r}."
            )
        creative = ad.creative
        has_copy = bool(creative.headline or creative.primary_text)
        if not creative.existing_post_urn and not has_copy:
            issues.append(
                f"Ad {ad.name!r} needs a creative: an existing post URN to sponsor, "
                "or ad copy (a headline or primary text) for a new post. A landing "
                "URL is optional."
            )
    return issues


def plan_issues(data: dict[str, Any]) -> list[str]:
    """Completeness issues for a `CampaignPlan` across all its platforms.

    Validates each platform's campaign with `campaign_issues`. With one platform
    the messages are unprefixed (identical to single-platform today); with several,
    each issue is prefixed with its platform so the agent knows where to look. An
    empty plan (no platforms) is itself an issue.
    """
    try:
        plan = CampaignPlan.model_validate(data)
    except ValidationError as exc:
        return [
            f"{'.'.join(str(p) for p in err['loc']) or 'plan'}: {err['msg']}"
            for err in exc.errors()
        ]

    if not plan.platforms:
        return ["Add at least one platform to the campaign plan."]

    single = len(plan.platforms) == 1
    issues: list[str] = []
    for pp in plan.platforms:
        for issue in campaign_issues(pp.campaign.model_dump(mode="json")):
            issues.append(issue if single else f"[{pp.platform}] {issue}")
    return issues
