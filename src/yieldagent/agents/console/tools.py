"""Tools the console agent calls to plan a LinkedIn campaign.

These wrap the existing, tested LinkedIn integration:
  * the "recipe book" reads — list_seniorities / list_job_functions /
    list_company_size_buckets / search_targeting — let the LLM discover the real
    taxonomy instead of guessing;
  * preview_targeting resolves an audience to URNs and surfaces anything that
    didn't match (the no-guess contract), so the operator sees what will be
    targeted before anything is created;
  * propose_campaign pauses for human approval (LangGraph interrupt);
  * create_linkedin_draft is the write step — STUBBED in M1, made real in M2.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from langgraph.types import interrupt

from yieldagent.agents.console.validation import campaign_issues
from yieldagent.domain import Audience
from yieldagent.integrations.linkedin.client import LinkedInClient
from yieldagent.integrations.linkedin.config import LinkedInConfig
from yieldagent.integrations.linkedin.targeting import (
    COMPANY_SIZE_TO_STAFF_RANGE,
    FACET_INDUSTRIES,
    FACET_SKILLS,
    FACET_TITLES,
    TargetingResolver,
)

_SEARCHABLE_FACETS = {
    "industries": FACET_INDUSTRIES,
    "titles": FACET_TITLES,
    "skills": FACET_SKILLS,
}


def _client() -> LinkedInClient:
    return LinkedInClient(LinkedInConfig.from_env())


def _localized(entity: dict[str, Any]) -> str | None:
    return entity.get("name", {}).get("localized", {}).get("en_US")


@tool
async def list_seniorities() -> list[str]:
    """List LinkedIn's standardized seniority levels (e.g. Manager, Director, VP, CXO).

    Use this before targeting seniority so you pick from real options.
    """
    async with _client() as client:
        items = await client.list_seniorities()
    return [name for e in items if (name := _localized(e))]


@tool
async def list_job_functions() -> list[str]:
    """List LinkedIn's standardized job functions (e.g. Engineering, Marketing, Sales)."""
    async with _client() as client:
        items = await client.list_functions()
    return [name for e in items if (name := _localized(e))]


@tool
def list_company_size_buckets() -> list[str]:
    """List the valid company-size buckets (employee-count ranges) for targeting."""
    return list(COMPANY_SIZE_TO_STAFF_RANGE.keys())


@tool
async def search_targeting(facet: str, query: str) -> list[str]:
    """Search an open targeting taxonomy by keyword.

    `facet` must be one of: "industries", "titles", "skills". Returns the
    relevance-ranked option names LinkedIn knows for `query` (e.g.
    search_targeting("industries", "software") -> ["Software Development", ...]).
    """
    facet_urn = _SEARCHABLE_FACETS.get(facet.strip().lower())
    if facet_urn is None:
        return [f"error: facet must be one of {sorted(_SEARCHABLE_FACETS)}"]
    async with _client() as client:
        hits = await client.typeahead_targeting_entities(facet=facet_urn, query=query)
    return [name for h in hits if (name := h.get("name"))]


@tool
async def preview_targeting(audience: dict[str, Any]) -> dict[str, Any]:
    """Resolve an audience to LinkedIn targeting and report what matched.

    `audience` is a yieldagent Audience dict (geos, seniorities, job_functions,
    industries, job_titles, skills, company_sizes). Returns the resolved facets
    and any `unresolved` names that matched no LinkedIn entity — never guessed.
    Use this to confirm targeting with the operator before proposing.
    """
    parsed = Audience.model_validate(audience)
    async with _client() as client:
        resolved = await TargetingResolver(client).resolve(parsed)
    facets: dict[str, list[str]] = {}
    for clause in resolved.criteria["include"]["and"]:
        facets.update(clause["or"])
    return {"resolved_facets": facets, "unresolved": resolved.unresolved}


async def _unresolved_targeting(campaign: dict[str, Any]) -> dict[str, list[str]]:
    """Resolve every line item's audience and collect what LinkedIn can't match.

    Run at propose time against the real API, so the proposal reflects exactly
    what the publish step will target — nothing is guessed. Best-effort: if the
    API is unavailable here, return empty (create re-resolves anyway).
    """
    merged: dict[str, list[str]] = {}
    try:
        async with _client() as client:
            resolver = TargetingResolver(client)
            for line_item in campaign.get("line_items", []):
                audience = Audience.model_validate(line_item["targeting"]["audience"])
                resolved = await resolver.resolve(audience)
                for facet, names in resolved.unresolved.items():
                    bucket = merged.setdefault(facet, [])
                    bucket.extend(n for n in names if n not in bucket)
    except Exception:  # noqa: BLE001 — best-effort preview; publish re-resolves
        return {}
    return merged


@tool
async def propose_campaign(campaign: dict[str, Any]) -> str:
    """Present the finished campaign draft to the operator and wait for approval.

    First validates the draft is complete (objective, line items with
    budget/flight/targeting, ads with a creative source); if anything is missing
    it is returned for you to ask the operator about — the draft is NOT shown
    until complete. Then resolves the targeting against LinkedIn so the operator
    sees exactly what will (and won't) be targeted. Do NOT call
    create_linkedin_draft until this approves. `campaign` is a Campaign dict.
    """
    issues = campaign_issues(campaign)
    if issues:
        return (
            "The draft isn't ready to propose. Resolve these — ask the operator "
            "for anything missing, then call propose_campaign again:\n- "
            + "\n- ".join(issues)
        )
    unresolved = await _unresolved_targeting(campaign)
    decision = interrupt(
        {"type": "proposal", "campaign": campaign, "unresolved": unresolved}
    )
    if decision.get("approved"):
        return "Operator approved. Call create_linkedin_draft with the same campaign."
    reason = decision.get("reason") or "no reason given"
    return f"Operator rejected the draft ({reason}). Ask what they want to change."


@tool
async def create_linkedin_draft(campaign: dict[str, Any]) -> dict[str, Any]:
    """Create the approved campaign as a DRAFT on LinkedIn. Only call after approval.

    M1: stubbed (returns synthesized ids, nothing is sent to LinkedIn). M2 wires
    this to the real publish flow and persists the result.
    """
    issues = campaign_issues(campaign)
    if issues:
        return {"error": "Campaign is incomplete; cannot create.", "issues": issues}
    return {
        "stub": True,
        "campaign_id": "dryrun_group_0",
        "name": campaign.get("name", "Untitled"),
        "note": "M1 stub — no LinkedIn write yet (M2 makes this real).",
    }


CONSOLE_TOOLS = [
    list_seniorities,
    list_job_functions,
    list_company_size_buckets,
    search_targeting,
    preview_targeting,
    propose_campaign,
    create_linkedin_draft,
]
