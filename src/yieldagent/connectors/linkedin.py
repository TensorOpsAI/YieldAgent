"""LinkedIn connector — wraps the existing LinkedIn integration in the contract.

This is the reference connector: it delegates to the tested LinkedIn modules
(client, targeting resolver, diagnostics, mapping, publish flow) and exposes them
through the uniform `Connector` surface. No new LinkedIn logic lives here — it is
an adapter, so the agent's generic tools (C1) can drive LinkedIn without importing
any `integrations.linkedin` module directly.
"""

from __future__ import annotations

import re
from typing import Any

from yieldagent.domain import Audience, BiddingStrategy, Campaign
from yieldagent.integrations.linkedin.client import client_from_env
from yieldagent.integrations.linkedin.config import LinkedInConfig
from yieldagent.integrations.linkedin.diagnostics import (
    describe_constraints,
    fallback_floor,
    preflight_problems,
    quote_budget_floor,
)
from yieldagent.integrations.linkedin.mapping import (
    DEFAULT_CAMPAIGN_TYPE,
    campaign_bidding,
    campaign_objective,
    flight_to_run_schedule,
    money_to_linkedin_amount,
)
from yieldagent.integrations.linkedin.targeting import (
    COMPANY_SIZE_TO_STAFF_RANGE,
    FACET_INDUSTRIES,
    FACET_SKILLS,
    FACET_TITLES,
    TargetingResolver,
    localized_name,
)

from .base import ConnectorManifest, PublishError

# Open taxonomies resolvable via the typeahead finder.
_SEARCHABLE_FACETS = {
    "industries": FACET_INDUSTRIES,
    "titles": FACET_TITLES,
    "skills": FACET_SKILLS,
}


def _configured() -> bool:
    try:
        LinkedInConfig.from_env()
        return True
    except Exception:  # noqa: BLE001 — missing/invalid config means "not connected"
        return False


class LinkedInConnector:
    """Adapter from the LinkedIn integration to the `Connector` contract."""

    id = "linkedin"
    label = "LinkedIn"

    @property
    def manifest(self) -> ConnectorManifest:
        connected = _configured()
        return ConnectorManifest(
            id=self.id,
            label=self.label,
            connected=connected,
            can_create=connected,
            reliability="api",
        )

    async def describe_constraints(self) -> dict[str, Any]:
        async with client_from_env() as client:
            return await describe_constraints(client)

    async def search_targeting(self, facet: str, query: str) -> list[str]:
        facet_urn = _SEARCHABLE_FACETS.get(facet.strip().lower())
        if facet_urn is None:
            raise ValueError(
                f"facet must be one of {sorted(_SEARCHABLE_FACETS)}, got {facet!r}"
            )
        async with client_from_env() as client:
            hits = await client.typeahead_targeting_entities(facet=facet_urn, query=query)
        return [name for h in hits if (name := h.get("name"))]

    async def list_taxonomy(self, kind: str) -> list[str]:
        key = kind.strip().lower()
        if key == "company_sizes":
            return list(COMPANY_SIZE_TO_STAFF_RANGE.keys())
        if key not in {"seniorities", "job_functions"}:
            raise ValueError(
                "kind must be one of 'seniorities', 'job_functions', 'company_sizes', "
                f"got {kind!r}"
            )
        async with client_from_env() as client:
            items = (
                await client.list_seniorities()
                if key == "seniorities"
                else await client.list_functions()
            )
        return [name for e in items if (name := localized_name(e))]

    async def preview_targeting(self, audience: dict[str, Any]) -> dict[str, Any]:
        parsed = Audience.model_validate(audience)
        async with client_from_env() as client:
            resolved = await TargetingResolver(client).resolve(parsed)
        facets: dict[str, list[str]] = {}
        for clause in resolved.criteria["include"]["and"]:
            facets.update(clause["or"])
        return {"resolved_facets": facets, "unresolved": resolved.unresolved}

    async def estimate_reach(self, audience: dict[str, Any]) -> dict[str, int]:
        parsed = Audience.model_validate(audience)
        async with client_from_env() as client:
            resolved = await TargetingResolver(client).resolve(parsed)
            return await client.audience_count(resolved.criteria)

    async def list_recent_posts(self, limit: int = 12) -> list[dict[str, Any]]:
        """Recent sponsorable org posts: `[{urn, text, media_type}]`, newest first.

        Lets the operator name a post by description ("our webinar post") instead
        of pasting a URN: the agent reads the texts and picks the match. Only
        original posts that carry text are returned, since reshares and bare
        references cannot be sponsored. Best-effort - returns `[]` on any trouble
        rather than blocking the conversation.
        """
        try:
            async with client_from_env() as client:
                org_urn = LinkedInConfig.from_env().organization_urn
                if not org_urn:
                    account = await client.get_ad_account()
                    org_urn = (account or {}).get("reference")
                if not org_urn or not str(org_urn).startswith("urn:li:organization:"):
                    return []
                raw = await client.list_organization_posts(
                    org_urn, count=max(limit * 2, 20)
                )
        except Exception:  # noqa: BLE001 — discovery is best-effort, never blocks
            return []

        posts: list[dict[str, Any]] = []
        for el in raw:
            if (el.get("lifecycleState") or "") != "PUBLISHED":
                continue
            text = _clean_commentary(el.get("commentary") or "")
            if not text:
                continue  # no text => a reshare/reference we can neither match nor sponsor
            posts.append(
                {
                    "urn": el.get("id"),
                    "text": text,
                    "media_type": _post_media_type(el.get("content") or {}),
                }
            )
            if len(posts) >= limit:
                break
        return posts

    async def quote_budget_floor(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Live per-plan floor via `adBudgetPricing`; falls back to the table.

        `plan` carries `objective`, `currency`, `audience`, `bidding_strategy`. The
        audience is the important one: `adBudgetPricing` 400s without resolved
        targeting, so a quote without it can only be the conservative fallback. We
        resolve the audience from `plan["audience"]` and, failing that, from a
        nested line item, so a live quote fires whenever the plan describes one.
        """
        plan = plan or {}
        objective = plan.get("objective")
        currency = plan.get("currency")
        audience = _audience_from_plan(plan)
        strategy_raw = plan.get("bidding_strategy")
        try:
            strategy = BiddingStrategy(strategy_raw) if strategy_raw else None
        except ValueError:
            strategy = None

        if not _configured():
            return fallback_floor(currency)

        criteria: dict[str, Any] | None = None
        try:
            async with client_from_env() as client:
                if audience:
                    try:
                        parsed_audience = Audience.model_validate(audience)
                        resolved = await TargetingResolver(client).resolve(parsed_audience)
                        criteria = resolved.criteria
                    except Exception:  # noqa: BLE001 — fall back if targeting won't resolve
                        criteria = None
                return await quote_budget_floor(
                    client,
                    objective=objective,
                    currency=currency,
                    targeting_criteria=criteria,
                    bidding_strategy=strategy,
                )
        except Exception:  # noqa: BLE001 — never raise; fallback is always usable
            return fallback_floor(currency)

    async def validate(self, campaign: dict[str, Any]) -> list[dict[str, Any]]:
        parsed = Campaign.model_validate(campaign)
        async with client_from_env() as client:
            return await preflight_problems(client, parsed)

    async def preview_plan(self, campaign: dict[str, Any]) -> dict[str, Any]:
        """Resolve each line item once: unresolved facets + reach. Best-effort."""
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
            return {"unresolved": unresolved, "reach": reach}
        return {"unresolved": unresolved, "reach": reach}

    async def preview_ads(self, campaign: dict[str, Any]) -> dict[str, Any]:
        """Build a display preview per ad (existing post → real content; copy → fields)."""
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
                            "media_type": None,
                        }
        except Exception:  # noqa: BLE001 — preview is best-effort
            return previews
        return previews

    async def forecast(self, campaign: dict[str, Any]) -> dict[str, Any]:
        """Forecast impressions/clicks/spend for the first line item. Best-effort.

        Mirrors how the draft is created (same targeting, budget, bidding, flight) so
        the numbers match what the platform predicts for the proposed campaign.
        Returns {} on any trouble (too-small audience, start date not in the future,
        API error) so it never blocks proposing.
        """
        try:
            parsed = Campaign.model_validate(campaign)
            if not parsed.line_items:
                return {}
            line_item = parsed.line_items[0]
            objective_type = campaign_objective(parsed)
            bidding = campaign_bidding(line_item, objective_type)
            schedule = flight_to_run_schedule(line_item.flight)
            daily_budget = (
                money_to_linkedin_amount(
                    line_item.daily_budget.amount, line_item.daily_budget.currency
                )
                if line_item.daily_budget
                else None
            )
            async with client_from_env() as client:
                resolved = await TargetingResolver(client).resolve(
                    line_item.targeting.audience
                )
                return await client.ad_supply_forecast(
                    campaign_type=DEFAULT_CAMPAIGN_TYPE,
                    time_range=(schedule["start"], schedule["end"]),
                    targeting_criteria=resolved.criteria,
                    total_budget=money_to_linkedin_amount(
                        line_item.budget.amount, line_item.budget.currency
                    ),
                    daily_budget=daily_budget,
                    objective_type=objective_type,
                    optimization_target=bidding["optimization_target_type"],
                    audience_expansion=bool(line_item.audience_expansion),
                    audience_network=bool(line_item.audience_network),
                )
        except Exception:  # noqa: BLE001 — forecast is best-effort, never blocks proposing
            return {}

    async def publish_draft(self, campaign: dict[str, Any]) -> dict[str, Any]:
        # Lazy import: pulls in the MCP server module only when actually creating.
        from yieldagent.integrations.linkedin.diagnostics import CampaignValidationError
        from yieldagent.integrations.linkedin.server import publish_draft_campaign

        try:
            result = await publish_draft_campaign(campaign)
        except CampaignValidationError as exc:
            raise PublishError(
                str(exc),
                problems=exc.problems,
                fixable=True,
                rolled_back=exc.rolled_back,
            ) from exc
        except Exception as exc:  # noqa: BLE001 — normalize to the neutral error
            raise PublishError(
                f"{self.label} did not create the draft: {exc}", fixable=False
            ) from exc
        result["manage_url"] = _lcm_url(LinkedInConfig.from_env().ad_account_id)
        return result


def _clean_commentary(text: str) -> str:
    """A post's commentary as plain, matchable text: strip `@[Name](urn:…)` mention
    markup down to the name, drop escapes, collapse whitespace, and truncate."""
    text = re.sub(r"@\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = text.replace("\\", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]


def _post_media_type(content: dict[str, Any]) -> str:
    """Classify a post's content so the agent can describe it: image/video/article/text."""
    if "article" in content:
        return "article"
    if "multiImage" in content:
        return "image"
    media_id = str((content.get("media") or {}).get("id") or "")
    if "video" in media_id:
        return "video"
    if "image" in media_id:
        return "image"
    return "text"


def _audience_from_plan(plan: dict[str, Any]) -> dict[str, Any] | None:
    """Find an audience in a quote plan, however the agent shaped it.

    Prefers a top-level `audience`, then the first line item's targeting under
    either a flat `line_items` list or a nested `campaign`. Returns None if none
    is present (the quote then falls back to the conservative table)."""
    if isinstance(plan.get("audience"), dict):
        return plan["audience"]
    campaign = plan.get("campaign") if isinstance(plan.get("campaign"), dict) else plan
    line_items = campaign.get("line_items") if isinstance(campaign, dict) else None
    if isinstance(line_items, list) and line_items:
        targeting = line_items[0].get("targeting") if isinstance(line_items[0], dict) else None
        audience = targeting.get("audience") if isinstance(targeting, dict) else None
        if isinstance(audience, dict):
            return audience
    return None


async def _preview_existing_post(client: Any, post_urn: str) -> dict[str, Any]:
    """Build a creative preview from a hand-published post (best-effort)."""
    preview: dict[str, Any] = {
        "source": "existing_post",
        "post_urn": post_urn,
        "headline": None,
        "text": None,
        "url": None,
        "image_url": None,
        "media_type": None,
    }
    try:
        post = await client.get_post(post_urn)
    except Exception:  # noqa: BLE001 — preview is best-effort, never blocks proposing
        return preview
    preview["text"] = post.get("commentary")
    content = post.get("content") or {}
    article = content.get("article") or {}
    preview["headline"] = article.get("title")
    preview["url"] = article.get("source")
    preview["image_url"], preview["media_type"] = await _media_image(client, content)
    return preview


async def _image_download_url(client: Any, image_urn: str) -> str | None:
    """Resolve an `urn:li:image:…` to its temporary download URL (best-effort)."""
    try:
        return (await client.get_image(image_urn)).get("downloadUrl")
    except Exception:  # noqa: BLE001 — image is optional
        return None


async def _media_image(client: Any, content: dict[str, Any]) -> tuple[str | None, str | None]:
    """Find a display image for a post's content: (image_url, media_type).

    Handles the three shapes a sponsorable post can carry — an article thumbnail, a
    single image/video (a video resolves to its poster frame), and a multi-image
    post (first image). `media_type` is "video" or "image" so the UI can badge it.
    """
    thumbnail = (content.get("article") or {}).get("thumbnail")
    if thumbnail and (url := await _image_download_url(client, thumbnail)):
        return url, "image"

    media_id = (content.get("media") or {}).get("id")
    if media_id and "video" in media_id:
        try:
            thumbnail = (await client.get_video(media_id)).get("thumbnail")
        except Exception:  # noqa: BLE001 — thumbnail is optional
            thumbnail = None
        if thumbnail:
            return thumbnail, "video"
    elif media_id and "image" in media_id and (url := await _image_download_url(client, media_id)):
        return url, "image"

    images = (content.get("multiImage") or {}).get("images") or []
    if images and (first := images[0].get("id") or images[0].get("image")):
        if url := await _image_download_url(client, first):
            return url, "image"

    return None, None


def _lcm_url(ad_account_id: str) -> str:
    return f"https://www.linkedin.com/campaignmanager/accounts/{ad_account_id}/campaigns"


__all__ = ["LinkedInConnector"]
