"""Connector registry — the agent's single lookup for platform connectors.

Built once per process from the available connectors. The agent's generic tools
(C1) resolve a platform key to a `Connector` here, so adding a platform is just
registering its connector — no change to the tools or the agent.
"""

from __future__ import annotations

from .base import Connector, ConnectorManifest
from .linkedin import LinkedInConnector

_REGISTRY: dict[str, Connector] | None = None


def _build() -> dict[str, Connector]:
    # As each platform's connector lands (Meta C3, Google C6) it is added here.
    connectors: tuple[Connector, ...] = (LinkedInConnector(),)
    return {c.manifest.id: c for c in connectors}


def registry() -> dict[str, Connector]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build()
    return _REGISTRY


def get_connector(platform: str) -> Connector:
    """Resolve a platform key (case-insensitive) to its connector, or raise."""
    conn = registry().get(platform.strip().lower())
    if conn is None:
        known = ", ".join(sorted(registry())) or "none"
        raise KeyError(f"No connector for platform {platform!r}; known: {known}")
    return conn


def manifests() -> list[ConnectorManifest]:
    """Every registered connector's manifest (for platform listing)."""
    return [c.manifest for c in registry().values()]


__all__ = ["get_connector", "manifests", "registry"]
