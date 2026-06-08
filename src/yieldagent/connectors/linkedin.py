"""LinkedIn connector — wraps the existing LinkedIn integration in the contract.

This is the reference connector: it delegates to the tested LinkedIn modules
(client, targeting resolver, diagnostics, mapping, publish flow) and exposes them
through the uniform `Connector` surface. No new LinkedIn logic lives here — it is
an adapter, so the agent's generic tools (C1) can drive LinkedIn without importing
any `integrations.linkedin` module directly.
"""

from __future__ import annotations

from typing import Any

from yieldagent.domain import Audience, Campaign
from yieldagent.integrations.linkedin.client import client_from_env
from yieldagent.integrations.linkedin.config import LinkedInConfig
from yieldagent.integrations.linkedin.diagnostics import (
    describe_constraints,
    preflight_problems,
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
                        }
        except Exception:  # noqa: BLE001 — preview is best-effort
            return previews
        return previews

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


def _lcm_url(ad_account_id: str) -> str:
    return f"https://www.linkedin.com/campaignmanager/accounts/{ad_account_id}/campaigns"


__all__ = ["LinkedInConnector"]
