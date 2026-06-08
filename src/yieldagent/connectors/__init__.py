"""Platform-agnostic ad-connector layer.

The agent talks to every ad platform through one `Connector` contract; the
`registry` resolves a platform key to its connector. This is the seam that makes
YieldAgent multi-platform without the agent ever branching on which platform.
"""

from .base import Connector, ConnectorManifest
from .registry import get_connector, manifests, registry

__all__ = [
    "Connector",
    "ConnectorManifest",
    "get_connector",
    "manifests",
    "registry",
]
