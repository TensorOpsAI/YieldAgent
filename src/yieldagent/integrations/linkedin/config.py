"""Environment-driven configuration for the LinkedIn MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LinkedInConfig:
    access_token: str
    ad_account_id: str
    api_version: str
    allow_live: bool
    allowed_accounts: frozenset[str] = field(default_factory=frozenset)
    # Organization (Company Page) that authors the Direct Sponsored Content posts
    # backing each creative. Optional: if unset, the server resolves it from the
    # ad account's `reference` field at publish time.
    organization_urn: str | None = None

    @classmethod
    def from_env(cls) -> LinkedInConfig:
        token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
        account = os.environ.get("LINKEDIN_AD_ACCOUNT_ID")
        if not token:
            raise RuntimeError("LINKEDIN_ACCESS_TOKEN is required")
        if not account:
            raise RuntimeError("LINKEDIN_AD_ACCOUNT_ID is required")
        # Accept either bare numeric IDs or full URNs; normalize to bare numeric.
        if account.startswith("urn:li:sponsoredAccount:"):
            account = account.rsplit(":", 1)[-1]
        if not account.isdigit():
            raise RuntimeError(
                f"LINKEDIN_AD_ACCOUNT_ID must be a numeric account id (got {account!r})"
            )
        raw_allow = os.environ.get("LINKEDIN_ALLOWED_AD_ACCOUNTS", "")
        allowed = frozenset(a.strip() for a in raw_allow.split(",") if a.strip())
        # Accept a bare org id or a full URN.
        org = os.environ.get("LINKEDIN_ORGANIZATION_URN") or os.environ.get(
            "LINKEDIN_ORGANIZATION_ID"
        )
        if org and not org.startswith("urn:li:organization:"):
            org = f"urn:li:organization:{org.strip()}"
        return cls(
            access_token=token,
            ad_account_id=account,
            api_version=os.environ.get("LINKEDIN_API_VERSION", "202605"),
            allow_live=os.environ.get("YIELDAGENT_ALLOW_LIVE") == "1",
            allowed_accounts=allowed,
            organization_urn=org,
        )

    @property
    def account_urn(self) -> str:
        return f"urn:li:sponsoredAccount:{self.ad_account_id}"
