"""Structured browser-fallback responses for gated platform APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FALLBACK_TOOL = "browser.run_playwright_flow"
GATED_ERROR_MARKERS = (
    "access_denied",
    "app review",
    "application is restricted",
    "authorization",
    "authorized",
    "developer token",
    "insufficient privileges",
    "insufficient_scope",
    "not approved",
    "oauth",
    "permission",
    "permissions",
    "program approval",
    "scope",
    "scopes",
    "unauthorized",
    "user_not_authorized",
    "vetted",
)


@dataclass(frozen=True)
class BrowserFallback:
    """A routing hint agents can act on without silently driving a user session."""

    reason: str
    operation: str
    platform: str

    def asdict(self) -> dict[str, Any]:
        return {
            "needs_browser_fallback": True,
            "reason": self.reason,
            "platform": self.platform,
            "operation": self.operation,
            "fallback_tool": FALLBACK_TOOL,
            "risk": "credential_sensitive",
            "approval_required": True,
            "dry_run_required": True,
            "next_step": (
                "Show a dry-run Playwright plan for the platform web UI, then ask for "
                "explicit operator approval before running it in an authenticated browser session."
            ),
        }


def _flatten_payload(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key} {_flatten_payload(item)}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(_flatten_payload(item) for item in value)
    return str(value)


def is_gated_platform_error(status_code: int, payload: Any) -> bool:
    """Return true for OAuth scope, app-review, program-approval, or access gates."""
    if status_code not in {400, 401, 403}:
        return False
    compact = _flatten_payload(payload).lower()
    return any(marker in compact for marker in GATED_ERROR_MARKERS)


def browser_fallback_response(
    *,
    platform: str,
    operation: str,
    status_code: int,
    payload: Any,
) -> dict[str, Any]:
    reason = f"{platform} API returned {status_code}: {_flatten_payload(payload)[:280]}"
    return BrowserFallback(reason=reason, operation=operation, platform=platform).asdict()
