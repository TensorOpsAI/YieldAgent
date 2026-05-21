"""Translate platform-neutral domain objects into Meta Marketing API payloads.

Kept in one place so the MCP server stays a thin HTTP layer and so contributors
adding new platforms have a clear reference for what this mapping involves.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Any

from yieldagent.domain import Audience, Campaign, CreativeAsset, Flight, LineItem, Objective

OBJECTIVE_TO_META: dict[Objective, str] = {
    Objective.awareness: "OUTCOME_AWARENESS",
    Objective.traffic: "OUTCOME_TRAFFIC",
    Objective.engagement: "OUTCOME_ENGAGEMENT",
    Objective.leads: "OUTCOME_LEADS",
    Objective.app_promotion: "OUTCOME_APP_PROMOTION",
    Objective.sales: "OUTCOME_SALES",
}

GENDER_TO_META: dict[str, int] = {"male": 1, "female": 2}

# Most major currencies use 2 minor units. Currencies with 0 (JPY, KRW) or 3
# (BHD, KWD) minor units are listed here so we don't silently corrupt budgets.
ZERO_DECIMAL_CURRENCIES = {"JPY", "KRW", "VND", "CLP"}
THREE_DECIMAL_CURRENCIES = {"BHD", "KWD", "OMR", "JOD", "TND"}


def to_minor_units(amount: Decimal, currency: str) -> int:
    currency = currency.upper()
    if currency in ZERO_DECIMAL_CURRENCIES:
        return int(amount)
    if currency in THREE_DECIMAL_CURRENCIES:
        return int(amount * 1000)
    return int(amount * 100)


def campaign_objective(campaign: Campaign) -> str:
    return OBJECTIVE_TO_META[campaign.objective]


def flight_to_meta_times(flight: Flight) -> tuple[str, str]:
    """Meta expects ISO-8601 timestamps. Use UTC midnight bounds."""
    start = datetime.combine(flight.start_date, time.min, tzinfo=timezone.utc)
    # end_date is inclusive — flight ends at the end of that day
    end = datetime.combine(flight.end_date, time.max, tzinfo=timezone.utc)
    return start.isoformat(), end.isoformat()


def audience_to_targeting(audience: Audience) -> dict[str, Any]:
    targeting: dict[str, Any] = {}
    if audience.geos:
        targeting["geo_locations"] = {"countries": [g.upper() for g in audience.geos]}
    if audience.age_min is not None:
        targeting["age_min"] = audience.age_min
    if audience.age_max is not None:
        targeting["age_max"] = audience.age_max
    if audience.genders:
        genders = [GENDER_TO_META[g.lower()] for g in audience.genders if g.lower() in GENDER_TO_META]
        if genders:
            targeting["genders"] = genders
    # interests intentionally omitted — Meta requires adinterest IDs from a
    # search endpoint, which the agent should resolve in a follow-up pass.
    return targeting


def line_item_payload(line_item: LineItem, campaign_id: str) -> dict[str, Any]:
    start, end = flight_to_meta_times(line_item.flight)
    return {
        "campaign_id": campaign_id,
        "name": line_item.name,
        "lifetime_budget_minor": to_minor_units(
            line_item.budget.amount, line_item.budget.currency
        ),
        "start_time": start,
        "end_time": end,
        "targeting": audience_to_targeting(line_item.targeting.audience),
    }


def creative_payload(creative: CreativeAsset, page_id: str) -> dict[str, Any]:
    """Build a minimal link-ad creative.

    Image/video uploads are out of scope for the first slice — the agent will
    pass `image_url`/`video_url` references; production use will need to resolve
    these into Meta `image_hash` / `video_id` via separate uploads.
    """
    object_story_spec: dict[str, Any] = {"page_id": page_id}
    link_data: dict[str, Any] = {
        "link": creative.landing_url or "https://example.com",
        "message": creative.primary_text or "",
    }
    if creative.headline:
        link_data["name"] = creative.headline
    if creative.description:
        link_data["description"] = creative.description
    if creative.call_to_action and creative.landing_url:
        link_data["call_to_action"] = {
            "type": creative.call_to_action.upper().replace(" ", "_"),
            "value": {"link": creative.landing_url},
        }
    object_story_spec["link_data"] = link_data
    return {"name": creative.name, "object_story_spec": object_story_spec}
