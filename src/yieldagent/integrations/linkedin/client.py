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
from urllib.parse import quote

import httpx

from yieldagent.integrations._base import ApiError, BaseHttpClient

from .config import LinkedInConfig

_BASE_URL = "https://api.linkedin.com/rest"
_FORBIDDEN_STATUSES = {"ACTIVE", "COMPLETED"}


def _encode_targeting_criteria(criteria: dict[str, Any]) -> str:
    """Serialize a targetingCriteria dict into the Restli 2.0 query-string form
    the audienceCounts finder requires: `(include:(and:List((or:(<facet>:List(
    <urn>,…))),…)))` with every URN percent-encoded but the structure literal.
    """
    clauses: list[str] = []
    for clause in criteria.get("include", {}).get("and", []):
        for facet, urns in clause.get("or", {}).items():
            facet_enc = quote(str(facet), safe="")
            urns_enc = ",".join(quote(str(u), safe="") for u in urns)
            clauses.append(f"(or:({facet_enc}:List({urns_enc})))")
    return f"(include:(and:List({','.join(clauses)})))"
# LinkedIn's politicalIntent is a String enum, not a boolean. Sending a bool
# fails with "enum type is not backed by a String".
_POLITICAL_INTENT_VALUES = {"POLITICAL", "NOT_POLITICAL", "NOT_DECLARED"}


class LinkedInError(ApiError):
    """Raised for any non-2xx response from the LinkedIn Marketing API."""

    platform = "LinkedIn"


def client_from_env() -> LinkedInClient:
    """Build a client from the environment — the one place that wiring lives."""
    return LinkedInClient(LinkedInConfig.from_env())


class LinkedInClient(BaseHttpClient):
    def __init__(self, config: LinkedInConfig, http: httpx.AsyncClient | None = None):
        super().__init__(http)
        self.config = config

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
        optimization_target_type: str | None = None,
        status: str | None = None,
        offsite_delivery_enabled: bool = False,
        political_intent: str = "NOT_POLITICAL",
    ) -> dict[str, Any]:
        if (daily_budget is None) == (total_budget is None):
            raise ValueError("Provide exactly one of daily_budget or total_budget")
        if political_intent not in _POLITICAL_INTENT_VALUES:
            raise ValueError(
                f"political_intent must be one of {sorted(_POLITICAL_INTENT_VALUES)}, "
                f"got {political_intent!r}"
            )
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
        # With an optimizationTargetType set, LinkedIn bids automatically
        # (Maximum delivery) and no manual unitCost is required.
        if optimization_target_type is not None:
            payload["optimizationTargetType"] = optimization_target_type
        return await self._request(
            "POST",
            f"/adAccounts/{self.config.ad_account_id}/adCampaigns",
            json=payload,
        )

    async def create_post(
        self,
        *,
        author_urn: str,
        commentary: str,
        article: dict[str, Any] | None = None,
        dsc_ad_account_urn: str | None = None,
        feed_distribution: str = "NONE",
    ) -> dict[str, Any]:
        """Create a Post via the (non-account-scoped) Posts API.

        A LinkedIn Creative cannot carry inline copy — it must reference a real
        Post (share / ugcPost). For ads we create a *dark post* (Direct Sponsored
        Content): authored by the advertiser org, `feedDistribution=NONE` so it
        never shows on the page's organic feed, and an `adContext` tying it to the
        sponsored account. Returns the new post URN under `id` (from `x-restli-id`).

        `feedDistribution=NONE` makes LinkedIn treat the post as DSC, which *requires*
        `adContext.dscAdAccount`. `dscAdType` must NOT be sent — it is read-only and
        a 422 ("ReadOnly field present in a create request") results otherwise.
        """
        payload: dict[str, Any] = {
            "author": author_urn,
            "commentary": commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": feed_distribution,
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        if article is not None:
            payload["content"] = {"article": article}
        if dsc_ad_account_urn is not None:
            payload["adContext"] = {"dscAdAccount": dsc_ad_account_urn}
        return await self._request("POST", "/posts", json=payload)

    async def create_creative(
        self,
        *,
        campaign_urn: str,
        content: dict[str, Any],
        intended_status: str | None = None,
    ) -> dict[str, Any]:
        # The Creatives API rejects `account` (read-only) and uses `intendedStatus`
        # (an enum) rather than `status`. `content` must reference a Post URN, e.g.
        # {"reference": "urn:li:share:..."}.
        payload: dict[str, Any] = {
            "campaign": campaign_urn,
            "content": content,
            "intendedStatus": self._check_status(intended_status),
        }
        return await self._request(
            "POST",
            f"/adAccounts/{self.config.ad_account_id}/creatives",
            json=payload,
        )

    async def delete_campaign_group(self, campaign_group_id: str | int) -> None:
        """Delete a Campaign Group by numeric id. Used to roll back orphaned drafts."""
        await self._request(
            "DELETE",
            f"/adAccounts/{self.config.ad_account_id}/adCampaignGroups/{campaign_group_id}",
        )

    async def delete_campaign(self, campaign_id: str | int) -> None:
        """Delete a Campaign by numeric id. Used to roll back orphaned drafts."""
        await self._request(
            "DELETE",
            f"/adAccounts/{self.config.ad_account_id}/adCampaigns/{campaign_id}",
        )

    async def delete_creative(self, creative_urn: str) -> None:
        """Delete a Creative. The Creatives API keys on the URL-encoded URN."""
        key = quote(str(creative_urn), safe="")
        await self._request(
            "DELETE",
            f"/adAccounts/{self.config.ad_account_id}/creatives/{key}",
        )

    async def delete_post(self, post_urn: str) -> None:
        """Delete a Post (e.g. a minted dark post). The Posts API keys on the URL-encoded URN."""
        key = quote(str(post_urn), safe="")
        await self._request("DELETE", f"/posts/{key}")

    async def get_post(self, post_urn: str) -> dict[str, Any]:
        """Fetch a Post's content (commentary + article title/source/thumbnail).

        Used to preview the real creative behind an `existing_post_urn` before the
        operator approves — so they see the ad, not an opaque id.
        """
        key = quote(str(post_urn), safe="")
        return await self._request("GET", f"/posts/{key}")

    async def get_image(self, image_urn: str) -> dict[str, Any]:
        """Resolve an `urn:li:image:…` to a temporary `downloadUrl` for display."""
        key = quote(str(image_urn), safe="")
        return await self._request("GET", f"/images/{key}")

    async def audience_count(self, criteria: dict[str, Any]) -> dict[str, int]:
        """Estimate how many LinkedIn members match a targetingCriteria.

        Returns `{"total": int, "active": int}`. `total` is a rounded approximation
        and is 0 when the audience is under 300 (LinkedIn's privacy floor, which is
        also the minimum size a campaign can run). The targetingCriteria must go in
        the query string pre-encoded, so this bypasses the params-based `_request`.
        """
        query = f"q=targetingCriteriaV2&targetingCriteria={_encode_targeting_criteria(criteria)}"
        url = httpx.URL(f"{_BASE_URL}/audienceCounts").copy_with(query=query.encode())
        response = await self._http.request("GET", url, headers=self._headers)
        if response.status_code >= 400:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
            raise LinkedInError(response.status_code, payload)
        elements = response.json().get("elements", [])
        first = elements[0] if elements else {}
        return {"total": int(first.get("total", 0)), "active": int(first.get("active", 0))}

    async def typeahead_targeting_entities(self, *, facet: str, query: str) -> list[dict[str, Any]]:
        """Search a targeting facet's open taxonomy (industries, titles, skills).

        Returns the relevance-ranked entities `[{urn, name, facetUrn}, ...]`. Only
        facets whose `availableEntityFinders` include `TYPEAHEAD` accept this — the
        closed enums (seniorities, jobFunctions) 400 here and must use the
        standardized-data endpoints instead.
        """
        res = await self._request(
            "GET",
            "/adTargetingEntities",
            params={"q": "typeahead", "query": query, "facet": facet},
        )
        return res.get("elements", [])

    async def list_seniorities(self) -> list[dict[str, Any]]:
        """Standardized seniority taxonomy: `[{id, name:{localized:{en_US}}}, ...]` (10)."""
        res = await self._request("GET", "/seniorities", params={"count": 50})
        return res.get("elements", [])

    async def list_functions(self) -> list[dict[str, Any]]:
        """Standardized job-function taxonomy: `[{id, name:{localized:{en_US}}}, ...]` (26)."""
        res = await self._request("GET", "/functions", params={"count": 50})
        return res.get("elements", [])

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
