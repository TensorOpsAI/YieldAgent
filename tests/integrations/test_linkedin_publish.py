"""Tests for the publish_draft_campaign orchestration.

The focus here is the creative-backing-post branch: an ad may reference a
hand-published post via `existing_post_urn` (no posting permission needed), or
let the server mint a Direct Sponsored Content "dark" post. These pin which
path each ad takes without standing up a real MCP server or hitting LinkedIn.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from yieldagent.domain import (
    Audience,
    Campaign,
    CreativeAsset,
    Flight,
    LineItem,
    Money,
    Objective,
    Targeting,
)
from yieldagent.domain.campaign import Ad
from yieldagent.integrations.linkedin import server as srv
from yieldagent.integrations.linkedin.config import LinkedInConfig

_AD_ACCOUNT_ID = "537690018"
_ORG_URN = "urn:li:organization:80050982"


def _config() -> LinkedInConfig:
    return LinkedInConfig(
        access_token="t",
        ad_account_id=_AD_ACCOUNT_ID,
        api_version="202605",
        allow_live=True,
        organization_urn=_ORG_URN,
    )


class _FakeClient:
    """Records create_post / create_creative calls; returns plausible ids.

    Set `fail_creative_on` to a 1-based call index to make that create_creative
    raise, exercising the rollback path. Deletes are recorded, not executed.
    """

    def __init__(self, config: LinkedInConfig):
        self.config = config
        self.create_post_calls: list[dict] = []
        self.create_campaign_calls: list[dict] = []
        self.create_creative_calls: list[dict] = []
        self.fail_creative_on: int | None = None
        self.deleted_creatives: list[str] = []
        self.deleted_campaigns: list[str] = []
        self.deleted_groups: list[str] = []
        self.deleted_posts: list[str] = []
        self._creative_seq = 0

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        pass

    def assert_account_allowed(self) -> None:
        pass

    async def typeahead_targeting_entities(self, *, facet: str, query: str) -> list[dict]:
        # The audience here is geo-only; resolve the locations typeahead and
        # leave every other facet empty.
        if facet.endswith("locations"):
            return [{"urn": "urn:li:geo:103644278", "name": "United States"}]
        return []

    async def get_ad_account(self) -> dict:
        return {"reference": _ORG_URN}

    async def create_campaign_group(self, **_kw) -> dict:
        return {"id": "111"}

    async def create_campaign(self, **kw) -> dict:
        self.create_campaign_calls.append(kw)
        return {"id": "222"}

    async def create_post(self, **kw) -> dict:
        self.create_post_calls.append(kw)
        return {"id": "urn:li:share:MINTED"}

    async def create_creative(self, **kw) -> dict:
        self._creative_seq += 1
        self.create_creative_calls.append(kw)
        if self.fail_creative_on == self._creative_seq:
            raise RuntimeError("UGC_RESHARE_CANNOT_BE_SPONSORED")
        return {"id": f"urn:li:sponsoredCreative:33{self._creative_seq}"}

    async def delete_creative(self, creative_urn: str) -> None:
        self.deleted_creatives.append(creative_urn)

    async def delete_campaign(self, campaign_id) -> None:
        self.deleted_campaigns.append(campaign_id)

    async def delete_campaign_group(self, campaign_group_id) -> None:
        self.deleted_groups.append(campaign_group_id)

    async def delete_post(self, post_urn: str) -> None:
        self.deleted_posts.append(post_urn)


@pytest.fixture
def patched(monkeypatch):
    captured: dict[str, Any] = {}

    def _factory(config: LinkedInConfig) -> _FakeClient:
        client = _FakeClient(config)
        client.fail_creative_on = captured.get("fail_creative_on")
        captured["client"] = client
        return client

    monkeypatch.setattr(srv, "LinkedInClient", _factory)
    monkeypatch.setattr(srv.LinkedInConfig, "from_env", classmethod(lambda cls: _config()))
    return captured


def _campaign(*creatives: CreativeAsset) -> dict:
    line_item = LineItem(
        name="LI-1",
        budget=Money(amount=100, currency="EUR"),
        flight=Flight(start_date=date(2026, 7, 1), end_date=date(2026, 7, 31)),
        targeting=Targeting(audience=Audience(description="engineers", geos=["US"])),
    )
    ads = [
        Ad(name=c.name, line_item_name="LI-1", creative=c) for c in creatives
    ]
    return Campaign(
        name="C",
        objective=Objective.traffic,
        line_items=[line_item],
        ads=ads,
    ).model_dump(mode="json")


async def test_existing_post_urn_skips_create_post(patched) -> None:
    campaign = _campaign(
        CreativeAsset(name="reuse", existing_post_urn="urn:li:share:HANDMADE")
    )
    result = await srv.publish_draft_campaign(campaign)
    client = patched["client"]
    assert client.create_post_calls == []
    assert len(client.create_creative_calls) == 1
    assert client.create_creative_calls[0]["content"] == {"reference": "urn:li:share:HANDMADE"}
    assert result["ads"][0]["post_urn"] == "urn:li:share:HANDMADE"


async def test_missing_post_urn_mints_dark_post(patched) -> None:
    campaign = _campaign(
        CreativeAsset(name="fresh", landing_url="https://example.com")
    )
    await srv.publish_draft_campaign(campaign)
    client = patched["client"]
    assert len(client.create_post_calls) == 1
    assert client.create_creative_calls[0]["content"] == {"reference": "urn:li:share:MINTED"}


async def test_mixed_ads_only_mint_for_missing_urn(patched) -> None:
    campaign = _campaign(
        CreativeAsset(name="reuse", existing_post_urn="urn:li:share:HANDMADE"),
        CreativeAsset(name="fresh", landing_url="https://example.com"),
    )
    await srv.publish_draft_campaign(campaign)
    client = patched["client"]
    assert len(client.create_post_calls) == 1
    refs = {c["content"]["reference"] for c in client.create_creative_calls}
    assert refs == {"urn:li:share:HANDMADE", "urn:li:share:MINTED"}


async def test_creative_failure_rolls_back_orphans(patched) -> None:
    # Two existing-post ads; the second creative fails. The group, campaign, and
    # the first (already-created) creative must all be torn down — no orphans.
    patched["fail_creative_on"] = 2
    campaign = _campaign(
        CreativeAsset(name="ok", existing_post_urn="urn:li:share:A"),
        CreativeAsset(name="boom", existing_post_urn="urn:li:share:B"),
    )
    with pytest.raises(RuntimeError, match="UGC_RESHARE_CANNOT_BE_SPONSORED"):
        await srv.publish_draft_campaign(campaign)

    client = patched["client"]
    assert client.deleted_creatives == ["urn:li:sponsoredCreative:331"]
    assert client.deleted_campaigns == ["222"]
    assert client.deleted_groups == ["111"]
    # Existing-post ads never mint posts, so nothing to delete there.
    assert client.deleted_posts == []


async def test_minted_post_is_rolled_back_on_creative_failure(patched) -> None:
    # A dark-post ad: the post is minted, then the creative fails. The minted
    # post must be cleaned up alongside the campaign and group.
    patched["fail_creative_on"] = 1
    campaign = _campaign(CreativeAsset(name="fresh", landing_url="https://example.com"))
    with pytest.raises(RuntimeError, match="UGC_RESHARE_CANNOT_BE_SPONSORED"):
        await srv.publish_draft_campaign(campaign)

    client = patched["client"]
    assert client.deleted_posts == ["urn:li:share:MINTED"]
    assert client.deleted_campaigns == ["222"]
    assert client.deleted_groups == ["111"]
    assert client.deleted_creatives == []


async def test_auto_bidding_uses_cpm_and_objective_target(patched) -> None:
    # A LEAD_GENERATION campaign must be created with auto-bidding so no manual
    # bid is needed: costType CPM + optimizationTargetType MAX_LEAD.
    line_item = LineItem(
        name="LI-1",
        budget=Money(amount=100, currency="EUR"),
        flight=Flight(start_date=date(2026, 7, 1), end_date=date(2026, 7, 31)),
        targeting=Targeting(audience=Audience(description="x", geos=["US"])),
    )
    campaign = Campaign(
        name="C",
        objective=Objective.leads,
        line_items=[line_item],
        ads=[Ad(name="a", line_item_name="LI-1",
                creative=CreativeAsset(name="a", existing_post_urn="urn:li:share:X"))],
    ).model_dump(mode="json")

    await srv.publish_draft_campaign(campaign)
    call = patched["client"].create_campaign_calls[0]
    assert call["cost_type"] == "CPM"
    assert call["optimization_target_type"] == "MAX_LEAD"


async def test_traffic_objective_uses_max_click(patched) -> None:
    # The default fixture is a traffic (WEBSITE_VISITS) campaign → MAX_CLICK.
    await srv.publish_draft_campaign(
        _campaign(CreativeAsset(name="a", existing_post_urn="urn:li:share:X"))
    )
    call = patched["client"].create_campaign_calls[0]
    assert call["cost_type"] == "CPM"
    assert call["optimization_target_type"] == "MAX_CLICK"
