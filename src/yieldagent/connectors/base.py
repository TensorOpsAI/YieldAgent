"""Platform-agnostic connector contract.

A `Connector` is how the agent talks to *any* ad platform without knowing which
one. Each platform (LinkedIn, Meta, …) implements this Protocol; the registry
hands the agent the right connector by key. The agent's tools are written once
against this interface (C1), and every platform-specific rule lives behind it —
in the connector's `manifest` (self-describing limits/fields) and its methods.

Keeping the surface small and uniform is what makes the multi-platform
conversation possible: the agent calls the same seven methods on a LinkedIn
connector or a Meta connector and never branches on platform.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ConnectorManifest:
    """Self-describing summary of a platform connector.

    `connected` reflects whether the platform's config is present; `can_create`
    whether the connector can publish drafts today. `reliability` is "api" for a
    real API connector or "browser" for a Playwright-driven one (C5), so the agent
    can set expectations. `notes` carries short human-facing caveats.
    """

    id: str
    label: str
    connected: bool
    can_create: bool
    reliability: str = "api"
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_status(self) -> dict[str, Any]:
        """Shape the agent's `list_ad_platforms` / Connections page already use."""
        return {
            "platform": self.label,
            "connected": self.connected,
            "can_create": self.can_create,
        }


@runtime_checkable
class Connector(Protocol):
    """The uniform interface every platform connector implements.

    Methods take and return platform-neutral dicts (serialized domain objects)
    so the agent's generic tools never import a platform module. A connector that
    cannot create campaigns yet still implements the read methods it supports and
    raises NotImplementedError for the rest; `manifest.can_create` tells callers.
    """

    @property
    def manifest(self) -> ConnectorManifest: ...

    async def describe_constraints(self) -> dict[str, Any]:
        """Self-describing limits, required/optional fields, and defaults."""
        ...

    async def search_targeting(self, facet: str, query: str) -> list[str]:
        """Search an open targeting taxonomy (e.g. industries/titles/skills)."""
        ...

    async def list_taxonomy(self, kind: str) -> list[str]:
        """List a closed enum taxonomy (e.g. seniorities/job_functions/sizes)."""
        ...

    async def preview_targeting(self, audience: dict[str, Any]) -> dict[str, Any]:
        """Resolve an audience and report what matched / was dropped."""
        ...

    async def estimate_reach(self, audience: dict[str, Any]) -> dict[str, int]:
        """Estimate how many members an audience reaches."""
        ...

    async def validate(self, campaign: dict[str, Any]) -> list[dict[str, Any]]:
        """Pre-flight a campaign, returning fixable problems (empty = ready)."""
        ...

    async def publish_draft(self, campaign: dict[str, Any]) -> dict[str, Any]:
        """Create the campaign as a DRAFT and return the created URNs/ids."""
        ...


__all__ = ["Connector", "ConnectorManifest"]
