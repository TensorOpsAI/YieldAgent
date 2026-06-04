"""Completeness check for a conversationally-built campaign.

The conversation replaces the markdown brief, so the agent must gather every
detail the platform needs. This reuses the SAME domain model the brief used as
the single source of truth — then adds the semantic checks the model can't
express (at least one line item and ad, ads point at real line items, every
creative has a usable source). `propose_campaign` calls this and refuses to
present an incomplete draft, so the agent is forced to ask for what's missing.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import ValidationError

from yieldagent.domain import Campaign

# Safety ceiling on any single budget figure (currency-agnostic for now — a blunt
# guard against accidental large spend). Override with YIELDAGENT_MAX_BUDGET.
DEFAULT_MAX_BUDGET = 1000.0


def max_budget() -> float:
    raw = os.environ.get("YIELDAGENT_MAX_BUDGET")
    try:
        return float(raw) if raw else DEFAULT_MAX_BUDGET
    except ValueError:
        return DEFAULT_MAX_BUDGET


def campaign_issues(data: dict[str, Any]) -> list[str]:
    """Return human-readable issues blocking creation; empty list means ready."""
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

    cap = max_budget()
    if campaign.lifetime_budget and float(campaign.lifetime_budget.amount) > cap:
        issues.append(
            f"Lifetime budget {campaign.lifetime_budget.amount} exceeds the safety "
            f"cap of {cap:g}. Lower it, or ask an admin to raise YIELDAGENT_MAX_BUDGET."
        )
    for li in campaign.line_items:
        if float(li.budget.amount) > cap:
            issues.append(
                f"Line item {li.name!r} budget {li.budget.amount} exceeds the safety "
                f"cap of {cap:g}. Lower it, or ask an admin to raise the cap."
            )

    line_item_names = {li.name for li in campaign.line_items}
    for ad in campaign.ads:
        if ad.line_item_name not in line_item_names:
            issues.append(
                f"Ad {ad.name!r} references unknown line item {ad.line_item_name!r}."
            )
        creative = ad.creative
        if not creative.existing_post_urn and not creative.landing_url:
            issues.append(
                f"Ad {ad.name!r} needs a creative source: an existing post URN to "
                "sponsor, or ad copy + a landing URL to mint a new post."
            )
    return issues
