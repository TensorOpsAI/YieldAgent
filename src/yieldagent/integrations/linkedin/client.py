"""Thin async HTTP client for the LinkedIn Marketing API.

Covers the surface YieldAgent's agents need: account introspection,
campaign-group / campaign / creative creation (DRAFT only), ad analytics
(read), partial campaign edits (status / budget / schedule) gated by an
explicit confirm flag, lead-gen-forms read + webhook subscription, and DMP
matched-audiences list uploads.

LinkedIn has no test-account concept. The safety guard here is an explicit
allowlist: `LINKEDIN_ALLOWED_AD_ACCOUNTS` must contain the configured account
id, or `YIELDAGENT_ALLOW_LIVE=1` must be set.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

import httpx

from .config import LinkedInConfig

_BASE_URL = "https://api.linkedin.com/rest"
_FORBIDDEN_STATUSES = {"ACTIVE", "COMPLETED"}

# Statuses the partial-update path will allow with confirm=True.
_CONFIRMABLE_STATUSES = {"ACTIVE", "PAUSED", "ARCHIVED", "DRAFT"}

CampaignStatus = Literal["ACTIVE", "PAUSED", "ARCHIVED", "DRAFT"]
AnalyticsPivot = Literal[
    "CAMPAIGN",
    "CREATIVE",
    "ACCOUNT",
    "CAMPAIGN_GROUP",
    "COMPANY",
    "MEMBER_COMPANY_SIZE",
    "MEMBER_COUNTRY_V2",
    "MEMBER_INDUSTRY",
    "MEMBER_JOB_FUNCTION",
    "MEMBER_JOB_TITLE",
    "MEMBER_SENIORITY",
]
TimeGranularity = Literal["ALL", "DAILY", "MONTHLY", "YEARLY"]


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

    async def __aenter__(self) -> "LinkedInClient":
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
        params: list[tuple[str, str]] | dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> dict[str, Any]:
        merged_headers = self._headers
        if headers:
            merged_headers = {**merged_headers, **headers}
        if content is not None and json is not None:
            raise ValueError("Pass either json or content, not both")

        response = await self._http.request(
            method,
            f"{_BASE_URL}{path}",
            params=params,
            json=json,
            content=content,
            headers=merged_headers,
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
        if "location" in response.headers:
            body.setdefault("_location", response.headers["location"])
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
        return await self._request("POST", "/adCampaignGroups", json=payload)

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
        }
        if daily_budget is not None:
            payload["dailyBudget"] = daily_budget
        if total_budget is not None:
            payload["totalBudget"] = total_budget
        if unit_cost is not None:
            payload["unitCost"] = unit_cost
        return await self._request("POST", "/adCampaigns", json=payload)

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
        return await self._request("POST", "/creatives", json=payload)

    # -- Campaign reads --------------------------------------------------

    async def list_campaigns(
        self,
        *,
        status_values: list[str] | None = None,
        type_values: list[str] | None = None,
        campaign_group_urns: list[str] | None = None,
        page_size: int = 100,
        page_token: str | None = None,
        sort_order: Literal["ASCENDING", "DESCENDING"] = "DESCENDING",
    ) -> dict[str, Any]:
        """List campaigns under the configured ad account with optional filters."""
        search_parts: list[str] = []
        if status_values:
            search_parts.append(
                f"status:(values:List({','.join(status_values)}))"
            )
        if type_values:
            search_parts.append(
                f"type:(values:List({','.join(type_values)}))"
            )
        if campaign_group_urns:
            search_parts.append(
                f"campaignGroup:(values:{_format_urn_list(campaign_group_urns)})"
            )

        params: list[tuple[str, str]] = [
            ("q", "search"),
            ("sortOrder", sort_order),
            ("pageSize", str(page_size)),
        ]
        if search_parts:
            params.append(("search", f"({','.join(search_parts)})"))
        if page_token:
            params.append(("pageToken", page_token))

        return await self._request(
            "GET",
            f"/adAccounts/{self.config.ad_account_id}/adCampaigns",
            params=params,
        )

    async def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Fetch a single campaign by id (digits, not URN)."""
        return await self._request(
            "GET",
            f"/adAccounts/{self.config.ad_account_id}/adCampaigns/{campaign_id}",
        )

    # -- Campaign partial updates ---------------------------------------

    async def patch_campaign(
        self,
        campaign_id: str,
        *,
        set_fields: dict[str, Any] | None = None,
        delete_fields: list[str] | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Submit a Rest.li PARTIAL_UPDATE against an existing campaign.

        Setting `confirm=False` returns a dry-run preview of the patch body
        instead of issuing the POST. Callers expose this as a built-in
        approval gate: the agent stages an edit, the operator inspects the
        patch, and only an explicit re-call with `confirm=True` mutates
        spend. Status changes are restricted to PAUSED / ACTIVE / ARCHIVED /
        DRAFT — COMPLETED is refused.
        """
        if not set_fields and not delete_fields:
            raise ValueError("patch_campaign needs at least one of set_fields / delete_fields")
        if set_fields and "status" in set_fields:
            status = str(set_fields["status"]).upper()
            if status not in _CONFIRMABLE_STATUSES:
                raise LinkedInError(
                    400,
                    {
                        "error": f"status={status!r} is not allowed via patch_campaign",
                        "allowed": sorted(_CONFIRMABLE_STATUSES),
                    },
                )
            set_fields = {**set_fields, "status": status}

        patch_body: dict[str, Any] = {"patch": {}}
        if set_fields:
            patch_body["patch"]["$set"] = set_fields
        if delete_fields:
            patch_body["patch"]["$delete"] = delete_fields

        endpoint = (
            f"/adAccounts/{self.config.ad_account_id}/adCampaigns/{campaign_id}"
        )
        if not confirm:
            return {
                "dry_run": True,
                "method": "POST",
                "endpoint": endpoint,
                "headers": {"X-RestLi-Method": "PARTIAL_UPDATE"},
                "body": patch_body,
                "hint": "Re-call with confirm=True to apply this change.",
            }

        self.assert_account_allowed()
        result = await self._request(
            "POST",
            endpoint,
            json=patch_body,
            headers={"X-RestLi-Method": "PARTIAL_UPDATE"},
        )
        return {"applied": True, "patch": patch_body, "response": result}

    async def set_campaign_status(
        self, campaign_id: str, status: str, *, confirm: bool = False
    ) -> dict[str, Any]:
        return await self.patch_campaign(
            campaign_id,
            set_fields={"status": status.upper()},
            confirm=confirm,
        )

    async def update_campaign_budget(
        self,
        campaign_id: str,
        *,
        daily_budget: dict[str, str] | None = None,
        total_budget: dict[str, str] | None = None,
        clear_total_budget: bool = False,
        confirm: bool = False,
    ) -> dict[str, Any]:
        if daily_budget is None and total_budget is None and not clear_total_budget:
            raise ValueError(
                "update_campaign_budget needs daily_budget, total_budget, or "
                "clear_total_budget=True"
            )
        set_fields: dict[str, Any] = {}
        if daily_budget is not None:
            set_fields["dailyBudget"] = daily_budget
        if total_budget is not None:
            set_fields["totalBudget"] = total_budget
        delete_fields = ["totalBudget"] if clear_total_budget else None
        return await self.patch_campaign(
            campaign_id,
            set_fields=set_fields or None,
            delete_fields=delete_fields,
            confirm=confirm,
        )

    async def update_campaign_schedule(
        self,
        campaign_id: str,
        *,
        start_epoch_ms: int | None = None,
        end_epoch_ms: int | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        if start_epoch_ms is None and end_epoch_ms is None:
            raise ValueError(
                "update_campaign_schedule needs start_epoch_ms or end_epoch_ms"
            )
        run_schedule: dict[str, int] = {}
        if start_epoch_ms is not None:
            run_schedule["start"] = start_epoch_ms
        if end_epoch_ms is not None:
            run_schedule["end"] = end_epoch_ms
        return await self.patch_campaign(
            campaign_id,
            set_fields={"runSchedule": run_schedule},
            confirm=confirm,
        )

    # -- Lead Sync (read + webhook subscribe) ---------------------------
    #
    # Requires the `r_marketing_leadgen_automation` OAuth scope, which lives
    # in a separate program approval. Webhook validation against the app
    # client secret is performed by the web receiver, not this client.

    async def list_lead_forms(
        self,
        *,
        owner_organization_urn: str | None = None,
        owner_sponsored_account_urn: str | None = None,
        count: int = 10,
        start: int = 0,
    ) -> dict[str, Any]:
        """List Lead Gen Forms owned by an organization or sponsored account."""
        if not (owner_organization_urn or owner_sponsored_account_urn):
            raise ValueError(
                "list_lead_forms needs owner_organization_urn or owner_sponsored_account_urn"
            )
        if owner_organization_urn:
            owner = f"(organization:{owner_organization_urn})"
        else:
            owner = f"(sponsoredAccount:{owner_sponsored_account_urn})"
        params: list[tuple[str, str]] = [
            ("owner", owner),
            ("q", "owner"),
            ("count", str(count)),
            ("start", str(start)),
        ]
        return await self._request("GET", "/leadForms", params=params)

    async def get_lead_form(self, form_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/leadForms/{form_id}")

    async def list_lead_responses(
        self,
        *,
        sponsored_account_urn: str | None = None,
        versioned_form_urn: str | None = None,
        lead_type: Literal["SPONSORED", "ORGANIC"] = "SPONSORED",
        limited_to_test_leads: bool = False,
    ) -> dict[str, Any]:
        """Pull leads from Lead Gen Forms (pull model).

        Either `sponsored_account_urn` (account-owner scope) or
        `versioned_form_urn` (single-form scope) must be supplied — usually
        you pass both for narrowest matching. `versioned_form_urn` looks
        like `urn:li:versionedLeadGenForm:(urn:li:leadGenForm:3162,1)`.
        """
        if not (sponsored_account_urn or versioned_form_urn):
            raise ValueError(
                "list_lead_responses needs sponsored_account_urn or versioned_form_urn"
            )
        params: list[tuple[str, str]] = [("q", "owner")]
        if sponsored_account_urn:
            params.append(("owner", f"(sponsoredAccount:{sponsored_account_urn})"))
        params.append(("leadType", f"(leadType:{lead_type})"))
        params.append(("limitedToTestLeads", str(limited_to_test_leads).lower()))
        if versioned_form_urn:
            params.append(("versionedLeadGenFormUrn", versioned_form_urn))
        return await self._request("GET", "/leadFormResponses", params=params)

    async def get_lead_response(self, response_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/leadFormResponses/{response_id}")

    async def subscribe_lead_notifications(
        self,
        *,
        webhook_url: str,
        owner_sponsored_account_urn: str | None = None,
        owner_organization_urn: str | None = None,
        versioned_form_urn: str | None = None,
        lead_type: Literal["SPONSORED", "ORGANIC"] = "SPONSORED",
    ) -> dict[str, Any]:
        """Register a webhook for lead-notification push events."""
        if not (owner_sponsored_account_urn or owner_organization_urn):
            raise ValueError(
                "subscribe_lead_notifications needs an owner_sponsored_account_urn "
                "or owner_organization_urn"
            )
        owner: dict[str, str] = {}
        if owner_sponsored_account_urn:
            owner["sponsoredAccount"] = owner_sponsored_account_urn
        if owner_organization_urn:
            owner["organization"] = owner_organization_urn
        payload: dict[str, Any] = {
            "webhook": webhook_url,
            "owner": owner,
            "leadType": lead_type,
        }
        if versioned_form_urn:
            payload["versionedForm"] = versioned_form_urn
        return await self._request("POST", "/leadNotifications", json=payload)

    # -- Matched Audiences (DMP segments) -------------------------------
    #
    # Requires the `rw_dmp_segments` OAuth scope, which is a separate program
    # approval from the base Marketing API. Reads on dmpSegments/listUploads
    # also accept `rw_ads`.

    async def create_dmp_segment(
        self,
        *,
        name: str,
        segment_type: Literal[
            "COMPANY_LIST_UPLOAD", "USER_LIST_UPLOAD", "COMPANY", "USER"
        ] = "COMPANY_LIST_UPLOAD",
        source_platform: Literal["LIST_UPLOAD", "API"] = "LIST_UPLOAD",
    ) -> dict[str, Any]:
        """Create a DMP Segment under the configured ad account.

        For CSV uploads use the default `LIST_UPLOAD` source platform with a
        `*_LIST_UPLOAD` type. For streaming dynamic add/remove via the
        `dmpSegments/{id}/users` endpoint, pass `source_platform="API"` and
        `segment_type="USER"` / `"COMPANY"`.
        """
        payload: dict[str, Any] = {
            "account": self.config.account_urn,
            "destinations": [{"destination": "LINKEDIN"}],
            "name": name,
            "sourcePlatform": source_platform,
            "type": segment_type,
        }
        return await self._request("POST", "/dmpSegments", json=payload)

    async def get_dmp_segment(self, segment_id: str) -> dict[str, Any]:
        """Fetch a DMP segment's current state, including `destinationSegmentId` once READY."""
        return await self._request("GET", f"/dmpSegments/{segment_id}")

    async def generate_dmp_upload_url(self) -> dict[str, Any]:
        """Request a one-shot upload URL for a DMP list-upload CSV.

        LinkedIn returns `{value: <ambry_url>}`. Pass the URL to
        `upload_dmp_csv` to stream the CSV body, then use the returned media
        URN with `attach_dmp_list`.
        """
        payload = {"owner": self.config.account_urn}
        return await self._request(
            "POST",
            "/dmpSegments?action=generateUploadUrl",
            json=payload,
        )

    async def upload_dmp_csv(self, upload_url: str, csv_bytes: bytes) -> str:
        """POST CSV bytes to the upload URL; return the media URN.

        Note that `upload_url` is on `www.linkedin.com/ambry/`, not the API
        host, so this call bypasses the regular `/rest` prefix. We still
        send the bearer token; LinkedIn-Version is not required for ambry.
        The media URN comes back in the `location` response header.
        """
        response = await self._http.post(
            upload_url,
            content=csv_bytes,
            headers={
                "Authorization": f"Bearer {self.config.access_token}",
                "Content-Type": "text/csv",
            },
        )
        if response.status_code >= 400:
            try:
                payload: Any = response.json()
            except ValueError:
                payload = response.text
            raise LinkedInError(response.status_code, payload)
        location = response.headers.get("location")
        if not location:
            raise LinkedInError(
                502, {"error": "DMP upload response did not include a location header"}
            )
        # LinkedIn returns either `/AAYA...csv` or a full `urn:li:media:...` value.
        if location.startswith("urn:"):
            return location
        return f"urn:li:media:{location}"

    async def attach_dmp_list(self, segment_id: str, media_urn: str) -> dict[str, Any]:
        """Attach an uploaded CSV (referenced by media URN) to a DMP segment."""
        return await self._request(
            "POST",
            f"/dmpSegments/{segment_id}/listUploads",
            json={"inputFile": media_urn},
        )

    async def add_dmp_users(
        self,
        segment_id: str,
        *,
        hashed_emails: list[str] | None = None,
        google_aids: list[str] | None = None,
        action: Literal["ADD", "REMOVE"] = "ADD",
    ) -> dict[str, Any]:
        """Streaming dynamic add/remove for `sourcePlatform=API`, `type=USER` segments.

        Pass SHA256-lowercase-hex hashed emails and/or Google Android IDs.
        Use a `LIST_UPLOAD` segment instead if you need a one-shot CSV load.
        """
        ids: list[dict[str, str]] = []
        for email in hashed_emails or []:
            ids.append({"idType": "SHA256_EMAIL", "idValue": email})
        for gaid in google_aids or []:
            ids.append({"idType": "GOOGLE_AID", "idValue": gaid})
        if not ids:
            raise ValueError("add_dmp_users requires hashed_emails or google_aids")
        return await self._request(
            "POST",
            f"/dmpSegments/{segment_id}/users",
            json={"elements": [{"action": action, "userIds": ids}]},
        )

    # -- Ad Analytics ----------------------------------------------------

    async def get_ad_analytics(
        self,
        *,
        pivot: AnalyticsPivot,
        date_start: date,
        date_end: date | None = None,
        time_granularity: TimeGranularity = "ALL",
        campaign_urns: list[str] | None = None,
        creative_urns: list[str] | None = None,
        account_urns: list[str] | None = None,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run the Analytics Finder (`q=analytics`) for one pivot.

        Returns the raw `{elements: [...], paging: {...}}` payload. The caller
        is responsible for any aggregation. Provide at least one of
        campaign_urns / creative_urns / account_urns (LinkedIn requires a
        scoping facet).
        """
        if not (campaign_urns or creative_urns or account_urns):
            raise ValueError(
                "get_ad_analytics requires at least one of campaign_urns, "
                "creative_urns, or account_urns"
            )

        params: list[tuple[str, str]] = [
            ("q", "analytics"),
            ("pivot", pivot),
            ("timeGranularity", time_granularity),
            ("dateRange", _format_date_range(date_start, date_end)),
        ]
        if campaign_urns:
            params.append(("campaigns", _format_urn_list(campaign_urns)))
        if creative_urns:
            params.append(("creatives", _format_urn_list(creative_urns)))
        if account_urns:
            params.append(("accounts", _format_urn_list(account_urns)))
        if fields:
            params.append(("fields", ",".join(fields)))

        return await self._request("GET", "/adAnalytics", params=params)

    async def get_ad_statistics(
        self,
        *,
        pivots: list[AnalyticsPivot],
        date_start: date,
        date_end: date | None = None,
        time_granularity: TimeGranularity = "ALL",
        campaign_urns: list[str] | None = None,
        creative_urns: list[str] | None = None,
        account_urns: list[str] | None = None,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run the Statistics Finder (`q=statistics`) for up to three pivots."""
        if not pivots:
            raise ValueError("pivots must be a non-empty list")
        if len(pivots) > 3:
            raise ValueError("LinkedIn supports at most 3 pivots in q=statistics")
        if not (campaign_urns or creative_urns or account_urns):
            raise ValueError(
                "get_ad_statistics requires at least one of campaign_urns, "
                "creative_urns, or account_urns"
            )

        params: list[tuple[str, str]] = [
            ("q", "statistics"),
            ("pivots", _format_urn_list(pivots)),
            ("timeGranularity", time_granularity),
            ("dateRange", _format_date_range(date_start, date_end)),
        ]
        if campaign_urns:
            params.append(("campaigns", _format_urn_list(campaign_urns)))
        if creative_urns:
            params.append(("creatives", _format_urn_list(creative_urns)))
        if account_urns:
            params.append(("accounts", _format_urn_list(account_urns)))
        if fields:
            params.append(("fields", ",".join(fields)))

        return await self._request("GET", "/adAnalytics", params=params)


# -- Rest.li v2 query value helpers -------------------------------------

def _format_date_range(start: date, end: date | None) -> str:
    """Build the Rest.li `dateRange=(start:(year:Y,month:M,day:D),end:...)` value."""
    parts = [f"start:(year:{start.year},month:{start.month},day:{start.day})"]
    if end is not None:
        parts.append(f"end:(year:{end.year},month:{end.month},day:{end.day})")
    return f"({','.join(parts)})"


def _format_urn_list(values: list[str]) -> str:
    """Build the Rest.li `List(a,b,c)` value used for list-typed query parameters."""
    return f"List({','.join(values)})"
