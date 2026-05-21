"""Thin async HTTP client for the Meta Marketing API.

Scoped to the surface the campaign-setup agent needs: account introspection plus
create-campaign / create-ad-set / create-ad. All writes default to PAUSED — the
client refuses to set ACTIVE status. Flipping a draft live is a human gate.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import MetaConfig


class MetaError(RuntimeError):
    """Raised for any non-2xx response from the Meta Marketing API."""

    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"Meta API error {status_code}: {payload}")


class MetaClient:
    def __init__(self, config: MetaConfig, http: httpx.AsyncClient | None = None):
        self.config = config
        self._http = http or httpx.AsyncClient(timeout=30.0)
        self._owns_http = http is None

    async def __aenter__(self) -> "MetaClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_http:
            await self._http.aclose()

    @property
    def base_url(self) -> str:
        return f"https://graph.facebook.com/{self.config.api_version}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged_params = {"access_token": self.config.access_token, **(params or {})}
        response = await self._http.request(
            method,
            f"{self.base_url}{path}",
            params=merged_params,
            data=data,
        )
        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
            raise MetaError(response.status_code, payload)
        return response.json()

    async def get_ad_account(self) -> dict[str, Any]:
        """Fetch account metadata; used to verify test-account status."""
        return await self._request(
            "GET",
            f"/{self.config.ad_account_id}",
            params={"fields": "id,name,account_status,currency,is_test_account"},
        )

    async def assert_test_account(self) -> dict[str, Any]:
        """Refuse to operate on a live account unless explicitly allowed."""
        account = await self.get_ad_account()
        if not account.get("is_test_account") and not self.config.allow_live:
            raise MetaError(
                403,
                {
                    "error": "refusing to operate on a non-test ad account",
                    "account_id": self.config.ad_account_id,
                    "hint": "create a test account in Meta Business Manager, or set YIELDAGENT_ALLOW_LIVE=1 to override",
                },
            )
        return account

    async def create_campaign(
        self,
        *,
        name: str,
        objective: str,
        special_ad_categories: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/{self.config.ad_account_id}/campaigns",
            data={
                "name": name,
                "objective": objective,
                "status": "PAUSED",
                "special_ad_categories": _csv(special_ad_categories or []),
            },
        )

    async def create_ad_set(
        self,
        *,
        campaign_id: str,
        name: str,
        daily_budget_minor: int | None = None,
        lifetime_budget_minor: int | None = None,
        start_time: str,
        end_time: str,
        targeting: dict[str, Any],
        billing_event: str = "IMPRESSIONS",
        optimization_goal: str = "LINK_CLICKS",
    ) -> dict[str, Any]:
        if (daily_budget_minor is None) == (lifetime_budget_minor is None):
            raise ValueError("Provide exactly one of daily_budget_minor or lifetime_budget_minor")
        data: dict[str, Any] = {
            "name": name,
            "campaign_id": campaign_id,
            "status": "PAUSED",
            "start_time": start_time,
            "end_time": end_time,
            "billing_event": billing_event,
            "optimization_goal": optimization_goal,
            "targeting": _json(targeting),
        }
        if daily_budget_minor is not None:
            data["daily_budget"] = str(daily_budget_minor)
        else:
            data["lifetime_budget"] = str(lifetime_budget_minor)
        return await self._request(
            "POST",
            f"/{self.config.ad_account_id}/adsets",
            data=data,
        )

    async def create_ad(
        self,
        *,
        ad_set_id: str,
        name: str,
        creative: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/{self.config.ad_account_id}/ads",
            data={
                "name": name,
                "adset_id": ad_set_id,
                "status": "PAUSED",
                "creative": _json(creative),
            },
        )


def _csv(items: list[str]) -> str:
    return ",".join(items)


def _json(value: Any) -> str:
    import json

    return json.dumps(value)
