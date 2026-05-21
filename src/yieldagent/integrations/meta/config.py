"""Environment-driven configuration for the Meta MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MetaConfig:
    access_token: str
    ad_account_id: str
    page_id: str | None
    api_version: str
    allow_live: bool

    @classmethod
    def from_env(cls) -> "MetaConfig":
        token = os.environ.get("META_ACCESS_TOKEN")
        account = os.environ.get("META_AD_ACCOUNT_ID")
        if not token:
            raise RuntimeError("META_ACCESS_TOKEN is required")
        if not account:
            raise RuntimeError("META_AD_ACCOUNT_ID is required")
        if not account.startswith("act_"):
            account = f"act_{account}"
        return cls(
            access_token=token,
            ad_account_id=account,
            page_id=os.environ.get("META_PAGE_ID"),
            api_version=os.environ.get("META_API_VERSION", "v22.0"),
            allow_live=os.environ.get("YIELDAGENT_ALLOW_LIVE") == "1",
        )
