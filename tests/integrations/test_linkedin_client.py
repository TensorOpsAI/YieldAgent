"""Tests for the LinkedIn Marketing API client.

These pin the endpoint paths the client uses for writes. LinkedIn deprecated
the global write endpoints (`/adCampaignGroups`, `/adCampaigns`, `/creatives`)
in favour of account-scoped ones (`/adAccounts/{id}/...`). The old endpoints
return 400 with an explicit migration message — see
`docs/claude_docs/linkedin_campaign_manager_api_debug_prompt.md`.

The tests intercept HTTP at the transport layer (no network), assert the
exact path each method posts to, and confirm the payload shape stays intact.
"""

from __future__ import annotations

import httpx
import pytest

from yieldagent.integrations.linkedin.client import LinkedInClient, LinkedInError
from yieldagent.integrations.linkedin.config import LinkedInConfig

_AD_ACCOUNT_ID = "537690018"


def _make_config() -> LinkedInConfig:
    return LinkedInConfig(
        access_token="test-token",
        ad_account_id=_AD_ACCOUNT_ID,
        api_version="202605",
        allow_live=False,
        allowed_accounts=frozenset({_AD_ACCOUNT_ID}),
    )


class _Recorder:
    """Collects every outbound httpx request so tests can assert on the URL."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        # LinkedIn returns 201 with the new id in this header for write endpoints.
        return httpx.Response(
            status_code=201,
            headers={"x-restli-id": "urn:li:sponsoredCampaignGroup:123"},
        )


@pytest.fixture
def recorded_client():
    recorder = _Recorder()
    transport = httpx.MockTransport(recorder.handler)
    http = httpx.AsyncClient(transport=transport, timeout=5.0)
    client = LinkedInClient(_make_config(), http=http)
    yield client, recorder


async def test_create_campaign_group_uses_account_scoped_path(recorded_client) -> None:
    client, recorder = recorded_client
    await client.create_campaign_group(
        name="smoke",
        total_budget={"amount": "10", "currencyCode": "EUR"},
    )
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.method == "POST"
    assert request.url.path == f"/rest/adAccounts/{_AD_ACCOUNT_ID}/adCampaignGroups"


async def test_create_campaign_uses_account_scoped_path(recorded_client) -> None:
    client, recorder = recorded_client
    await client.create_campaign(
        campaign_group_urn="urn:li:sponsoredCampaignGroup:1",
        name="smoke",
        objective_type="WEBSITE_VISITS",
        campaign_type="SPONSORED_UPDATES",
        total_budget={"amount": "10", "currencyCode": "EUR"},
        run_schedule={"start": 1, "end": 2},
        targeting_criteria={"include": {"and": []}},
        locale={"country": "US", "language": "en"},
    )
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.method == "POST"
    assert request.url.path == f"/rest/adAccounts/{_AD_ACCOUNT_ID}/adCampaigns"


async def test_create_creative_uses_account_scoped_path(recorded_client) -> None:
    client, recorder = recorded_client
    await client.create_creative(
        campaign_urn="urn:li:sponsoredCampaign:1",
        content={"reference": "urn:li:share:1"},
    )
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.method == "POST"
    assert request.url.path == f"/rest/adAccounts/{_AD_ACCOUNT_ID}/creatives"


async def test_create_creative_omits_account_and_uses_intended_status(recorded_client) -> None:
    """The Creatives API rejects a `account` field (read-only) and requires
    `intendedStatus` (not `status`). See the 422 errors:
    "/account :: ReadOnly field present", "/status :: unrecognized field",
    "/intendedStatus :: field is required".
    """
    import json

    client, recorder = recorded_client
    await client.create_creative(
        campaign_urn="urn:li:sponsoredCampaign:1",
        content={"reference": "urn:li:share:1"},
    )
    body = json.loads(recorder.requests[0].read())
    assert "account" not in body
    assert "status" not in body
    assert body["intendedStatus"] == "DRAFT"
    assert body["campaign"] == "urn:li:sponsoredCampaign:1"
    assert body["content"] == {"reference": "urn:li:share:1"}


async def test_create_creative_refuses_active_intended_status(recorded_client) -> None:
    client, _ = recorded_client
    with pytest.raises(LinkedInError):
        await client.create_creative(
            campaign_urn="urn:li:sponsoredCampaign:1",
            content={"reference": "urn:li:share:1"},
            intended_status="ACTIVE",
        )


async def test_create_post_uses_posts_endpoint_as_dark_post(recorded_client) -> None:
    """Creatives must reference a real Post. We create it as a dark (DSC) post:
    org author, feedDistribution NONE, lifecycleState PUBLISHED, and an adContext
    tying it to the sponsored account.
    """
    import json

    client, recorder = recorded_client
    await client.create_post(
        author_urn="urn:li:organization:80050982",
        commentary="How Northwind migrated to Lattice Cloud.",
        article={"source": "https://lattice.example/cloud", "title": "We replaced our warehouse"},
        dsc_ad_account_urn=f"urn:li:sponsoredAccount:{_AD_ACCOUNT_ID}",
    )
    request = recorder.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/rest/posts"
    body = json.loads(request.read())
    assert body["author"] == "urn:li:organization:80050982"
    assert body["commentary"].startswith("How Northwind")
    assert body["visibility"] == "PUBLIC"
    assert body["lifecycleState"] == "PUBLISHED"
    assert body["distribution"]["feedDistribution"] == "NONE"
    assert body["content"]["article"]["source"] == "https://lattice.example/cloud"
    assert body["adContext"]["dscAdAccount"] == f"urn:li:sponsoredAccount:{_AD_ACCOUNT_ID}"


async def test_get_ad_account_path_unchanged(recorded_client) -> None:
    """Reads were already account-scoped — make sure we don't accidentally regress."""
    client, recorder = recorded_client
    await client.get_ad_account()
    assert recorder.requests[0].url.path == f"/rest/adAccounts/{_AD_ACCOUNT_ID}"


async def test_list_campaigns_uses_account_scoped_path_with_search(recorded_client) -> None:
    """New helper for the read path used in smoke testing."""
    client, recorder = recorded_client
    await client.list_campaigns()
    request = recorder.requests[0]
    assert request.method == "GET"
    assert request.url.path == f"/rest/adAccounts/{_AD_ACCOUNT_ID}/adCampaigns"
    assert request.url.params.get("q") == "search"


async def test_create_campaign_includes_offsite_and_political_defaults(recorded_client) -> None:
    """LinkedIn now requires offsiteDeliveryEnabled + politicalIntent on Campaign create.

    Defaults must be safe: LinkedIn-only delivery (no Audience Network) and
    non-political. Callers can override via kwargs.
    """
    client, recorder = recorded_client
    await client.create_campaign(
        campaign_group_urn="urn:li:sponsoredCampaignGroup:1",
        name="smoke",
        objective_type="WEBSITE_VISITS",
        campaign_type="SPONSORED_UPDATES",
        total_budget={"amount": "10", "currencyCode": "EUR"},
        run_schedule={"start": 1, "end": 2},
        targeting_criteria={"include": {"and": []}},
        locale={"country": "US", "language": "en"},
    )
    payload = recorder.requests[0].read()
    import json
    body = json.loads(payload)
    assert body["offsiteDeliveryEnabled"] is False
    # politicalIntent is a STRING enum (POLITICAL | NOT_POLITICAL | NOT_DECLARED),
    # NOT a boolean. LinkedIn rejects a bool with
    # "enum type is not backed by a String".
    assert body["politicalIntent"] == "NOT_POLITICAL"


async def test_create_campaign_offsite_and_political_overrideable(recorded_client) -> None:
    client, recorder = recorded_client
    await client.create_campaign(
        campaign_group_urn="urn:li:sponsoredCampaignGroup:1",
        name="smoke",
        objective_type="WEBSITE_VISITS",
        campaign_type="SPONSORED_UPDATES",
        total_budget={"amount": "10", "currencyCode": "EUR"},
        run_schedule={"start": 1, "end": 2},
        targeting_criteria={"include": {"and": []}},
        locale={"country": "US", "language": "en"},
        offsite_delivery_enabled=True,
        political_intent="POLITICAL",
    )
    payload = recorder.requests[0].read()
    import json
    body = json.loads(payload)
    assert body["offsiteDeliveryEnabled"] is True
    assert body["politicalIntent"] == "POLITICAL"


async def test_create_campaign_rejects_invalid_political_intent(recorded_client) -> None:
    """Guard against passing a value LinkedIn's enum doesn't accept."""
    client, _ = recorded_client
    with pytest.raises(ValueError, match="political_intent"):
        await client.create_campaign(
            campaign_group_urn="urn:li:sponsoredCampaignGroup:1",
            name="smoke",
            objective_type="WEBSITE_VISITS",
            campaign_type="SPONSORED_UPDATES",
            total_budget={"amount": "10", "currencyCode": "EUR"},
            run_schedule={"start": 1, "end": 2},
            targeting_criteria={"include": {"and": []}},
            locale={"country": "US", "language": "en"},
            political_intent="MAYBE",
        )


async def test_required_headers_present(recorded_client) -> None:
    """All writes must include the LinkedIn-Version + restli protocol headers."""
    client, recorder = recorded_client
    await client.create_campaign_group(name="smoke")
    request = recorder.requests[0]
    # Headers are case-insensitive in httpx.
    assert request.headers["authorization"] == "Bearer test-token"
    assert request.headers["linkedin-version"] == "202605"
    assert request.headers["x-restli-protocol-version"] == "2.0.0"
