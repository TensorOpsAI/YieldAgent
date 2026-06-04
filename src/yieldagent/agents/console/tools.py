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

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langchain_core.tools import tool
from langgraph.types import interrupt

from yieldagent.agents.console.ad_platforms import ad_platform_status
from yieldagent.agents.console.validation import campaign_issues
from yieldagent.domain import Audience
from yieldagent.integrations.linkedin.client import client_from_env
from yieldagent.integrations.linkedin.config import LinkedInConfig
from yieldagent.integrations.linkedin.targeting import (
    COMPANY_SIZE_TO_STAFF_RANGE,
    FACET_INDUSTRIES,
    FACET_SKILLS,
    FACET_TITLES,
    TargetingResolver,
    localized_name,
)
from yieldagent.store import campaigns as store

_SEARCHABLE_FACETS = {
    "industries": FACET_INDUSTRIES,
    "titles": FACET_TITLES,
    "skills": FACET_SKILLS,
}


@tool
def list_ad_platforms() -> list[dict[str, Any]]:
    """List the ad platforms and whether you can create campaigns on each.

    Returns `[{platform, connected, can_create}]`. Only plan and create on a
    platform with `can_create` true (currently LinkedIn). Call this to answer the
    operator about platform availability instead of assuming.
    """
    return ad_platform_status()


@tool
async def list_seniorities() -> list[str]:
    """List LinkedIn's standardized seniority levels (e.g. Manager, Director, VP, CXO).

    Use this before targeting seniority so you pick from real options.
    """
    async with client_from_env() as client:
        items = await client.list_seniorities()
    return [name for e in items if (name := localized_name(e))]


@tool
async def list_job_functions() -> list[str]:
    """List LinkedIn's standardized job functions (e.g. Engineering, Marketing, Sales)."""
    async with client_from_env() as client:
        items = await client.list_functions()
    return [name for e in items if (name := localized_name(e))]


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
    An empty list means no match — pick another query, never invent a value.
    """
    facet_urn = _SEARCHABLE_FACETS.get(facet.strip().lower())
    if facet_urn is None:
        # Raise (not an error string in the result list) so a bad facet can never
        # be mistaken for a real hit; the agent sees the message and retries.
        raise ValueError(f"facet must be one of {sorted(_SEARCHABLE_FACETS)}, got {facet!r}")
    async with client_from_env() as client:
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
    async with client_from_env() as client:
        resolved = await TargetingResolver(client).resolve(parsed)
    facets: dict[str, list[str]] = {}
    for clause in resolved.criteria["include"]["and"]:
        facets.update(clause["or"])
    return {"resolved_facets": facets, "unresolved": resolved.unresolved}


@tool
async def estimate_reach(audience: dict[str, Any]) -> dict[str, int]:
    """Estimate how many LinkedIn members match an audience — its total reach.

    `audience` is a yieldagent Audience dict. Returns {total, active}: `total` is
    a rounded member count, and is 0 when the audience is under 300 — LinkedIn's
    privacy floor, which is also the minimum size a campaign can run. Use this to
    tell the operator how big their targeting is (and to catch a too-small audience)
    before proposing.
    """
    parsed = Audience.model_validate(audience)
    async with client_from_env() as client:
        resolved = await TargetingResolver(client).resolve(parsed)
        return await client.audience_count(resolved.criteria)


async def _proposal_targeting(
    campaign: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, int]]:
    """Resolve every line item once against the live API, returning both the
    unresolved facets and the estimated audience reach per line item.

    Run at propose time so the proposal reflects exactly what publish will target
    (nothing guessed) and how big that audience is. Best-effort: API trouble
    yields empty maps and never blocks the proposal — publish re-resolves anyway.
    """
    unresolved: dict[str, list[str]] = {}
    reach: dict[str, int] = {}
    try:
        async with client_from_env() as client:
            resolver = TargetingResolver(client)
            for line_item in campaign.get("line_items", []):
                name = line_item.get("name", "")
                audience = Audience.model_validate(line_item["targeting"]["audience"])
                resolved = await resolver.resolve(audience)
                for facet, names in resolved.unresolved.items():
                    bucket = unresolved.setdefault(facet, [])
                    bucket.extend(n for n in names if n not in bucket)
                try:
                    reach[name] = (await client.audience_count(resolved.criteria))["total"]
                except Exception:  # noqa: BLE001 — reach is best-effort
                    pass
    except Exception:  # noqa: BLE001 — best-effort preview; publish re-resolves
        return unresolved, reach
    return unresolved, reach


async def _preview_existing_post(client: Any, post_urn: str) -> dict[str, Any]:
    """Build a creative preview from a hand-published post (best-effort)."""
    preview: dict[str, Any] = {
        "source": "existing_post",
        "post_urn": post_urn,
        "headline": None,
        "text": None,
        "url": None,
        "image_url": None,
    }
    try:
        post = await client.get_post(post_urn)
    except Exception:  # noqa: BLE001 — preview is best-effort, never blocks proposing
        return preview
    preview["text"] = post.get("commentary")
    article = (post.get("content") or {}).get("article") or {}
    preview["headline"] = article.get("title")
    preview["url"] = article.get("source")
    thumbnail = article.get("thumbnail")
    if thumbnail:
        try:
            image = await client.get_image(thumbnail)
            preview["image_url"] = image.get("downloadUrl")
        except Exception:  # noqa: BLE001 — image is optional
            pass
    return preview


async def _ad_previews(campaign: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build a display preview per ad so the operator sees the real creative.

    For an existing post, fetch its content from LinkedIn; for ad copy, use the
    fields the operator gave. Keyed by ad name. Best-effort: any API failure just
    yields a sparser preview — it never blocks the proposal.
    """
    ads = campaign.get("ads") or []
    if not ads:
        return {}
    previews: dict[str, dict[str, Any]] = {}
    try:
        async with client_from_env() as client:
            for ad in ads:
                name = ad.get("name") or ""
                creative = ad.get("creative") or {}
                if creative.get("existing_post_urn"):
                    previews[name] = await _preview_existing_post(
                        client, creative["existing_post_urn"]
                    )
                elif creative.get("landing_url"):
                    previews[name] = {
                        "source": "ad_copy",
                        "headline": creative.get("headline"),
                        "text": creative.get("primary_text"),
                        "url": creative.get("landing_url"),
                        "image_url": None,
                    }
    except Exception:  # noqa: BLE001 — preview is best-effort
        return previews
    return previews


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
    unresolved, reach = await _proposal_targeting(campaign)
    previews = await _ad_previews(campaign)
    decision = interrupt(
        {
            "type": "proposal",
            "campaign": campaign,
            "unresolved": unresolved,
            "previews": previews,
            "reach": reach,
        }
    )
    if decision.get("approved"):
        return "Operator approved. Call create_linkedin_draft with the same campaign."
    reason = (decision.get("reason") or "").strip()
    if reason:
        return (
            f'Operator did not approve. Their feedback: "{reason}". Apply it and '
            "call propose_campaign again with the revised draft — ask only if the "
            "request is unclear. Never create without a fresh approval."
        )
    return "Operator rejected the draft. Ask what they want to change, then propose again."


def _audience_summary(campaign: dict[str, Any]) -> dict[str, Any]:
    """A compact targeting snapshot (first line item's audience) for the dashboard."""
    line_items = campaign.get("line_items") or []
    if not line_items:
        return {}
    return line_items[0].get("targeting", {}).get("audience", {})


def _lcm_url(ad_account_id: str) -> str:
    return f"https://www.linkedin.com/campaignmanager/accounts/{ad_account_id}/campaigns"


@tool
async def create_linkedin_draft(campaign: dict[str, Any]) -> dict[str, Any]:
    """Create the approved campaign as a DRAFT on LinkedIn and save it. Only call
    after propose_campaign returned an approval.

    Publishes the whole campaign (group → campaigns → creatives) as DRAFT — the
    client refuses ACTIVE, so nothing spends until a manual activation in Campaign
    Manager — then persists it so it shows on the dashboard.
    """
    issues = campaign_issues(campaign)
    if issues:
        return {
            "created": False,
            "error": "Campaign is incomplete; cannot create.",
            "issues": issues,
        }

    # Imported lazily: pulls in the MCP server module only when actually creating.
    from yieldagent.integrations.linkedin import server as li_server

    # LinkedIn has no transaction; publish_draft_campaign already rolls back any
    # partial work on failure. Surface a failure as a structured result (never
    # raise) so the UI shows a real error instead of a false "created" banner.
    try:
        result = await li_server.publish_draft_campaign(campaign)
    except Exception as exc:  # noqa: BLE001 — report publish failures, don't crash the turn
        return {"created": False, "error": f"LinkedIn did not create the draft: {exc}"}

    config = LinkedInConfig.from_env()
    group_id = result.get("campaign_id")
    lcm_url = _lcm_url(config.ad_account_id)

    # The draft now exists on LinkedIn; persistence is best-effort and must not
    # turn a real success into a reported failure.
    try:
        store.save(
            {
                "id": uuid4().hex,
                "created_at": datetime.now(UTC).isoformat(),
                "platform": "linkedin",
                "name": campaign.get("name", "Untitled"),
                "objective": campaign.get("objective", ""),
                "status": "DRAFT",
                "group_urn": result.get("campaign_group_urn"),
                "lcm_url": lcm_url,
                "targeting": _audience_summary(campaign),
                "unresolved": result.get("notes", {}).get("unresolved_b2b_targeting", {}),
                "payload": {"campaign": campaign, "result": result},
            }
        )
    except Exception:  # noqa: BLE001 — draft exists on LinkedIn; dashboard sync is best-effort
        pass

    return {
        "created": True,
        "campaign_id": group_id,
        "group_urn": result.get("campaign_group_urn"),
        "lcm_url": lcm_url,
        "ad_ids": [a.get("id") for a in result.get("ads", [])],
    }


CONSOLE_TOOLS = [
    list_ad_platforms,
    list_seniorities,
    list_job_functions,
    list_company_size_buckets,
    search_targeting,
    preview_targeting,
    estimate_reach,
    propose_campaign,
    create_linkedin_draft,
]
