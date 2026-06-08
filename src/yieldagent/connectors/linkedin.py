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

from .base import ConnectorManifest

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

    async def publish_draft(self, campaign: dict[str, Any]) -> dict[str, Any]:
        # Lazy import: pulls in the MCP server module only when actually creating.
        from yieldagent.integrations.linkedin.server import publish_draft_campaign

        return await publish_draft_campaign(campaign)


__all__ = ["LinkedInConnector"]
