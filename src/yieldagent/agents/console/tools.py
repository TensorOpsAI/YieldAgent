"""Generic, platform-parameterized tools the console agent calls.

Every tool takes a `platform` key and dispatches through the connector registry —
no tool imports a platform module, so adding a platform (Meta, Google, a
Playwright-driven DSP) needs zero tool changes. The platform-specific behaviour
lives behind the `Connector` contract:
  * describe_platform — the connector's self-describing limits/fields (manifest);
  * list_targeting_options / search_targeting — discover the real taxonomy;
  * preview_targeting / estimate_reach — confirm + size the audience;
  * propose_campaign — completeness check + targeting/ad preview, then pause for
    human approval (LangGraph interrupt);
  * create_draft — the write step, normalized across platforms.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langchain_core.tools import tool
from langgraph.types import interrupt

from yieldagent.agents.console.ad_platforms import ad_platform_status
from yieldagent.agents.console.validation import plan_issues
from yieldagent.connectors import get_connector
from yieldagent.connectors.base import PublishError
from yieldagent.store import campaigns as store


def _plan(platform: str, campaign: dict[str, Any]) -> dict[str, Any]:
    """Wrap a (platform, campaign) into a one-platform CampaignPlan dict.

    The CampaignPlan is the model underneath every conversation (C2); with one
    platform it behaves exactly like the single-platform flow. Multi-platform
    plans (C4) reuse the same shape with more entries.
    """
    return {
        "name": campaign.get("name") or "Untitled",
        "platforms": [{"platform": platform, "campaign": campaign}],
    }


@tool
def list_ad_platforms() -> list[dict[str, Any]]:
    """List the ad platforms and whether you can create campaigns on each.

    Returns `[{platform, connected, can_create}]`. Plan and create only on a
    platform with `can_create` true. Call this first to answer the operator about
    platform availability instead of assuming, and to learn the platform key to
    pass to the other tools.
    """
    return ad_platform_status()


@tool
async def describe_platform(platform: str) -> dict[str, Any]:
    """Get a platform's hard rules before planning, so you propose a valid campaign
    up front instead of guessing.

    Call this right after the operator picks a platform. Returns its budget
    minimums, account currency, flight/date rules, audience floor, creative rules,
    and the required/optional field spec. Honour these while gathering — never ask
    the operator for something the platform sets automatically (e.g. locale).
    """
    return await get_connector(platform).describe_constraints()


@tool
async def list_targeting_options(platform: str, kind: str) -> list[str]:
    """List a platform's closed targeting taxonomy for a given `kind`.

    The valid kinds are the platform's audience facets (see describe_platform).
    Returns the real option names — use them exactly, never invent one. Any
    per-platform nuance (e.g. how a facet differs from a free-text one) is in
    describe_platform's audience notes.
    """
    return await get_connector(platform).list_taxonomy(kind)


@tool
async def search_targeting(platform: str, facet: str, query: str) -> list[str]:
    """Search a platform's open targeting taxonomy by keyword.

    Pass the platform key from list_ad_platforms. `facet` is e.g. "industries",
    "titles", or "skills". Returns relevance-ranked option names (e.g. facet
    "industries", query "software" -> ["Software Development", ...]). An empty list
    means no match — try another query, never invent a value.
    """
    return await get_connector(platform).search_targeting(facet, query)


@tool
async def preview_targeting(platform: str, audience: dict[str, Any]) -> dict[str, Any]:
    """Resolve an audience to platform targeting and report what matched.

    `audience` is a yieldagent Audience dict using the platform's audience facets
    (see describe_platform). Returns the resolved facets and any `unresolved` names
    that matched nothing — never guessed. Use this to confirm targeting with the
    operator before proposing.
    """
    return await get_connector(platform).preview_targeting(audience)


@tool
async def estimate_reach(platform: str, audience: dict[str, Any]) -> dict[str, int]:
    """Estimate how many members an audience reaches on a platform.

    `audience` is a yieldagent Audience dict. Returns {total, active}: `total` is a
    rounded member count, 0 when under the platform's privacy floor (the minimum a
    campaign can run). Use this to tell the operator how big their targeting is — and
    to catch a too-small audience — before proposing.
    """
    return await get_connector(platform).estimate_reach(audience)


@tool
async def propose_campaign(platform: str, campaign: dict[str, Any]) -> str:
    """Present the finished campaign draft to the operator and wait for approval.

    First validates the draft is complete (objective, line items with
    budget/flight/targeting, ads with a creative source); if anything is missing it
    is returned for you to ask the operator about — the draft is NOT shown until
    complete. Then resolves the targeting and builds ad previews via the platform so
    the operator sees exactly what will (and won't) be targeted. Do NOT call
    create_draft until this approves. `campaign` is a Campaign dict.
    """
    issues = plan_issues(_plan(platform, campaign))
    if issues:
        return (
            "The draft isn't ready to propose. Resolve these — ask the operator "
            "for anything missing, then call propose_campaign again:\n- "
            + "\n- ".join(issues)
        )
    connector = get_connector(platform)
    plan = await connector.preview_plan(campaign)
    previews = await connector.preview_ads(campaign)
    decision = interrupt(
        {
            "type": "proposal",
            "platform": platform,
            "campaign": campaign,
            "unresolved": plan.get("unresolved", {}),
            "previews": previews,
            "reach": plan.get("reach", {}),
        }
    )
    if decision.get("approved"):
        return "Operator approved. Call create_draft with the same platform and campaign."
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


@tool
async def create_draft(platform: str, campaign: dict[str, Any]) -> dict[str, Any]:
    """Create the approved campaign as a DRAFT on the platform and save it. Only call
    after propose_campaign returned an approval.

    Publishes the whole campaign as DRAFT — nothing spends until a manual activation
    on the platform — then persists it so it shows on the dashboard. On failure
    returns a structured result (never raises) so the UI shows a real error instead
    of a false "created" banner.
    """
    issues = plan_issues(_plan(platform, campaign))
    if issues:
        return {
            "created": False,
            "fixable": True,
            "error": "Campaign is incomplete; cannot create.",
            "issues": issues,
        }

    connector = get_connector(platform)
    try:
        result = await connector.publish_draft(campaign)
    except PublishError as exc:
        # Fixable platform problems (pre-flight or API-reported): tell the operator
        # what to change, then re-propose. Non-fixable: surface the error.
        out: dict[str, Any] = {"created": False, "fixable": exc.fixable}
        if exc.problems:
            out["problems"] = exc.problems
            out["rolled_back"] = exc.rolled_back
            out["next_step"] = (
                "Explain these to the operator, apply the fixes to the draft, and "
                "call propose_campaign again. Do not retry create until re-approved."
            )
        else:
            out["error"] = str(exc)
        return out

    manage_url = result.get("manage_url")
    # The draft now exists on the platform; persistence is best-effort and must not
    # turn a real success into a reported failure.
    try:
        store.save(
            {
                "id": uuid4().hex,
                "created_at": datetime.now(UTC).isoformat(),
                "platform": platform.strip().lower(),
                "name": campaign.get("name", "Untitled"),
                "objective": campaign.get("objective", ""),
                "status": "DRAFT",
                "group_urn": result.get("campaign_group_urn"),
                "lcm_url": manage_url,
                "targeting": _audience_summary(campaign),
                "unresolved": result.get("notes", {}).get("unresolved_b2b_targeting", {}),
                "payload": {"campaign": campaign, "result": result},
            }
        )
    except Exception:  # noqa: BLE001 — draft exists on the platform; dashboard sync is best-effort
        pass

    return {
        "created": True,
        "platform": platform.strip().lower(),
        "campaign_id": result.get("campaign_id"),
        "group_urn": result.get("campaign_group_urn"),
        "lcm_url": manage_url,
        "ad_ids": [a.get("id") for a in result.get("ads", [])],
    }


CONSOLE_TOOLS = [
    list_ad_platforms,
    describe_platform,
    list_targeting_options,
    search_targeting,
    preview_targeting,
    estimate_reach,
    propose_campaign,
    create_draft,
]
