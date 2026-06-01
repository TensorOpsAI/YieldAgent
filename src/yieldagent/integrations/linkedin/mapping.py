"""Translate platform-neutral domain objects into LinkedIn Marketing API payloads.

Kept in one place so the MCP server stays a thin HTTP layer and so contributors
adding new platforms have a clear reference for what this mapping involves.

Hierarchy mapping:

| YieldAgent | LinkedIn       |
|------------|----------------|
| Campaign   | Campaign Group |
| LineItem   | Campaign       |
| Ad         | Creative       |

LinkedIn's three-level hierarchy lines up cleanly with our domain model — the
naming is the only thing that shifts.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any

from yieldagent.domain import Audience, Campaign, CreativeAsset, Flight, LineItem, Objective

# LinkedIn objectiveType values for Sponsored Content campaigns.
OBJECTIVE_TO_LINKEDIN: dict[Objective, str] = {
    Objective.awareness: "BRAND_AWARENESS",
    Objective.traffic: "WEBSITE_VISITS",
    Objective.engagement: "ENGAGEMENT",
    Objective.leads: "LEAD_GENERATION",
    Objective.app_promotion: "WEBSITE_VISITS",  # no dedicated app-install on LinkedIn
    Objective.sales: "WEBSITE_CONVERSIONS",
}

# LinkedIn requires geo URNs (urn:li:geo:{id}) — ISO codes are not accepted.
# Production use should resolve via the geo typeahead endpoint; the few entries
# below cover the common-case countries so simple briefs work out of the box.
ISO_TO_LINKEDIN_GEO_URN: dict[str, str] = {
    "US": "urn:li:geo:103644278",
    "GB": "urn:li:geo:101165590",
    "CA": "urn:li:geo:101174742",
    "DE": "urn:li:geo:101282230",
    "FR": "urn:li:geo:105015875",
    "AU": "urn:li:geo:101452733",
    "IN": "urn:li:geo:102713980",
    "IL": "urn:li:geo:101620260",
    "BR": "urn:li:geo:106057199",
    "JP": "urn:li:geo:101355337",
    "NL": "urn:li:geo:102890719",
    "ES": "urn:li:geo:105646813",
    "IT": "urn:li:geo:103350119",
    "SE": "urn:li:geo:105117694",
    "SG": "urn:li:geo:102454443",
}

# LinkedIn campaign type for standard image / single-share Sponsored Content.
DEFAULT_CAMPAIGN_TYPE = "SPONSORED_UPDATES"


def campaign_objective(campaign: Campaign) -> str:
    return OBJECTIVE_TO_LINKEDIN[campaign.objective]


def money_to_linkedin_amount(amount: Any, currency: str) -> dict[str, str]:
    """LinkedIn expects amounts as decimal strings, not minor units."""
    return {"amount": str(amount), "currencyCode": currency.upper()}


def flight_to_run_schedule(flight: Flight) -> dict[str, int]:
    """LinkedIn `runSchedule` uses epoch milliseconds. End-date is inclusive."""
    start = datetime.combine(flight.start_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(flight.end_date, time.max, tzinfo=timezone.utc)
    return {"start": int(start.timestamp() * 1000), "end": int(end.timestamp() * 1000)}


def campaign_run_schedule(flights: list[Flight]) -> dict[str, int]:
    """Build a Campaign Group runSchedule that spans all its child Campaigns.

    LinkedIn now requires `runSchedule` on `POST /adAccounts/{id}/adCampaignGroups`.
    The group must cover the earliest start and latest end across its line items.
    """
    if not flights:
        raise ValueError("Cannot compute runSchedule from empty list of flights")
    earliest = min(f.start_date for f in flights)
    latest = max(f.end_date for f in flights)
    return flight_to_run_schedule(Flight(start_date=earliest, end_date=latest))


def audience_to_targeting(audience: Audience) -> dict[str, Any]:
    """Build a LinkedIn `targetingCriteria` payload.

    Only geo targeting is wired in this slice. B2B facets (industries, job
    functions, seniorities, company sizes, skills) require URN resolution via
    the typeahead endpoint — a follow-up. They are present on the Audience for
    Brief round-trip fidelity, but are not pushed to the API here. If any B2B
    facets are set, a hint is included in the payload under `_unresolved_b2b`
    so the caller can log and surface them at approval time.
    """
    includes: list[str] = []
    for code in audience.geos:
        urn = ISO_TO_LINKEDIN_GEO_URN.get(code.upper())
        if urn:
            includes.append(urn)
    if not includes:
        # LinkedIn requires at least one location; default to US.
        includes.append(ISO_TO_LINKEDIN_GEO_URN["US"])

    criteria: dict[str, Any] = {
        "include": {
            "and": [
                {
                    "or": {
                        "urn:li:adTargetingFacet:locations": includes,
                    }
                }
            ]
        }
    }

    unresolved = {
        k: v
        for k, v in {
            "industries": audience.industries,
            "job_functions": audience.job_functions,
            "job_titles": audience.job_titles,
            "seniorities": audience.seniorities,
            "company_sizes": audience.company_sizes,
            "skills": audience.skills,
        }.items()
        if v
    }
    if unresolved:
        criteria["_unresolved_b2b"] = unresolved
    return criteria


def line_item_locale(audience: Audience) -> dict[str, str]:
    """LinkedIn campaigns require a `locale` (country + language).

    Derived from the first audience geo if available; defaults to en/US.
    """
    country = (audience.geos[0].upper() if audience.geos else "US")
    if country not in ISO_TO_LINKEDIN_GEO_URN:
        country = "US"
    return {"country": country, "language": "en"}


def line_item_payload(
    line_item: LineItem,
    *,
    campaign_group_urn: str,
    objective_type: str,
) -> dict[str, Any]:
    """Strict-typed snapshot of the create_campaign call for testing/inspection."""
    return {
        "campaignGroup": campaign_group_urn,
        "name": line_item.name,
        "objectiveType": objective_type,
        "type": DEFAULT_CAMPAIGN_TYPE,
        "totalBudget": money_to_linkedin_amount(
            line_item.budget.amount, line_item.budget.currency
        ),
        "runSchedule": flight_to_run_schedule(line_item.flight),
        "targetingCriteria": audience_to_targeting(line_item.targeting.audience),
        "locale": line_item_locale(line_item.targeting.audience),
    }


def creative_content(creative: CreativeAsset) -> dict[str, Any]:
    """Build a minimal Sponsored Content `content` block.

    Image/video uploads are out of scope for the first slice — the agent will
    pass `image_url`/`video_url` references; production use will need to upload
    these assets via the `/assets` endpoint and reference the returned URNs.
    """
    article: dict[str, Any] = {
        "source": creative.landing_url or "https://example.com",
    }
    if creative.headline:
        article["title"] = creative.headline
    if creative.description:
        article["description"] = creative.description
    if creative.image_url:
        article["thumbnail"] = creative.image_url

    content: dict[str, Any] = {"article": article}
    if creative.primary_text:
        content["commentary"] = creative.primary_text
    if creative.call_to_action:
        content["callToAction"] = {
            "label": creative.call_to_action.upper().replace(" ", "_")
        }
    return content


__all__ = [
    "DEFAULT_CAMPAIGN_TYPE",
    "ISO_TO_LINKEDIN_GEO_URN",
    "OBJECTIVE_TO_LINKEDIN",
    "audience_to_targeting",
    "campaign_objective",
    "campaign_run_schedule",
    "creative_content",
    "flight_to_run_schedule",
    "line_item_locale",
    "line_item_payload",
    "money_to_linkedin_amount",
]
