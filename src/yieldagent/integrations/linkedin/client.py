"""Thin async HTTP client for the LinkedIn Marketing API.

Scoped to the surface the campaign-setup agent needs: account introspection plus
create-campaign-group / create-campaign / create-creative. All writes are forced
to `DRAFT` status — the client refuses to set `ACTIVE`. Activation is a manual
step in LinkedIn Campaign Manager.

LinkedIn has no test-account concept. The safety guard here is an explicit
allowlist: `LINKEDIN_ALLOWED_AD_ACCOUNTS` must contain the configured account
id, or `YIELDAGENT_ALLOW_LIVE=1` must be set.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import LinkedInConfig

_BASE_URL = "https://api.linkedin.com/rest"
_FORBIDDEN_STATUSES = {"ACTIVE", "COMPLETED"}


class LinkedInError(RuntimeError):
    """Raised for any non-2xx response from the LinkedIn Marketing API."""

    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"LinkedIn API error {status_code}: {payload}")


class LinkedInClient:
    def __init__(self, config: LinkedInConfig, http: httpx.AsyncClient | None = None):
        self.config = config
        self._http = http or httpx.AsyncClient(timeout=30.0)
        self._owns_http = http is None

    async def __aenter__(self) -> LinkedInClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._owns_http:
            await self._http.aclose()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.access_token}",
            "LinkedIn-Version": self.config.api_version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self._http.request(
            method,
            f"{_BASE_URL}{path}",
            params=params,
            json=json,
            headers=self._headers,
        )
        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
            raise LinkedInError(response.status_code, payload)
        # LinkedIn returns 201 with empty body for many creates; the new resource
        # id comes back in the `x-restli-id` (or `x-linkedin-id`) header.
        body: dict[str, Any] = {}
        if response.content:
            try:
                body = response.json()
            except ValueError:
                body = {"_raw": response.text}
        for header in ("x-restli-id", "x-linkedin-id"):
            if header in response.headers:
                body.setdefault("id", response.headers[header])
                break
        return body

    async def get_ad_account(self) -> dict[str, Any]:
        """Fetch account metadata; used to verify allowlist membership."""
        return await self._request("GET", f"/adAccounts/{self.config.ad_account_id}")

    def assert_account_allowed(self) -> None:
        """Refuse to operate on accounts not in the configured allowlist.

        LinkedIn has no sandbox / test-account flag, so the only meaningful guard
        is an explicit allowlist maintained by the operator.
        """
        if self.config.allow_live:
            return
        if self.config.ad_account_id in self.config.allowed_accounts:
            return
        raise LinkedInError(
            403,
            {
                "error": "ad account is not in LINKEDIN_ALLOWED_AD_ACCOUNTS",
                "account_id": self.config.ad_account_id,
                "hint": (
                    "add the id to LINKEDIN_ALLOWED_AD_ACCOUNTS (comma-separated), "
                    "or set YIELDAGENT_ALLOW_LIVE=1 to bypass — but note that bypass "
                    "disables the only safety net LinkedIn offers via this integration."
                ),
            },
        )

    def _check_status(self, status: str | None) -> str:
        if status is None:
            return "DRAFT"
        upper = status.upper()
        if upper in _FORBIDDEN_STATUSES:
            raise LinkedInError(
                400,
                {
                    "error": f"refusing to create resource with status={upper!r}",
                    "hint": "this client only creates DRAFT or PAUSED resources; "
                    "activation is a manual step in LinkedIn Campaign Manager",
                },
            )
        return upper

    async def create_campaign_group(
        self,
        *,
        name: str,
        total_budget: dict[str, str] | None = None,
        run_schedule: dict[str, int] | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "account": self.config.account_urn,
            "name": name,
            "status": self._check_status(status),
        }
        if total_budget is not None:
            payload["totalBudget"] = total_budget
        if run_schedule is not None:
            payload["runSchedule"] = run_schedule
        return await self._request(
            "POST",
            f"/adAccounts/{self.config.ad_account_id}/adCampaignGroups",
            json=payload,
        )

    async def create_campaign(
        self,
        *,
        campaign_group_urn: str,
        name: str,
        objective_type: str,
        campaign_type: str,
        daily_budget: dict[str, str] | None = None,
        total_budget: dict[str, str] | None = None,
        run_schedule: dict[str, int],
        targeting_criteria: dict[str, Any],
        locale: dict[str, str],
        unit_cost: dict[str, str] | None = None,
        cost_type: str = "CPC",
        status: str | None = None,
        offsite_delivery_enabled: bool = False,
        political_intent: bool = False,
    ) -> dict[str, Any]:
        if (daily_budget is None) == (total_budget is None):
            raise ValueError("Provide exactly one of daily_budget or total_budget")
        payload: dict[str, Any] = {
            "account": self.config.account_urn,
            "campaignGroup": campaign_group_urn,
            "name": name,
            "status": self._check_status(status),
            "type": campaign_type,
            "objectiveType": objective_type,
            "costType": cost_type,
            "runSchedule": run_schedule,
            "targetingCriteria": targeting_criteria,
            "locale": locale,
            # Both fields became required in current API versions. Safe defaults:
            # LinkedIn-only delivery (no Audience Network) and non-political.
            "offsiteDeliveryEnabled": offsite_delivery_enabled,
            "politicalIntent": political_intent,
        }
        if daily_budget is not None:
            payload["dailyBudget"] = daily_budget
        if total_budget is not None:
            payload["totalBudget"] = total_budget
        if unit_cost is not None:
            payload["unitCost"] = unit_cost
        return await self._request(
            "POST",
            f"/adAccounts/{self.config.ad_account_id}/adCampaigns",
            json=payload,
        )

    async def create_creative(
        self,
        *,
        campaign_urn: str,
        content: dict[str, Any],
        status: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "account": self.config.account_urn,
            "campaign": campaign_urn,
            "content": content,
            "status": self._check_status(status),
        }
        return await self._request(
            "POST",
            f"/adAccounts/{self.config.ad_account_id}/creatives",
            json=payload,
        )

    async def list_campaigns(self) -> dict[str, Any]:
        """List campaigns under the configured ad account.

        Read-only. Useful for smoke tests and for agents that need to know what
        already exists before planning a new campaign.
        """
        return await self._request(
            "GET",
            f"/adAccounts/{self.config.ad_account_id}/adCampaigns",
            params={"q": "search"},
        )
