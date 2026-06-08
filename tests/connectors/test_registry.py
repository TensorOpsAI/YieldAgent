"""Tests for the connector contract, registry, and LinkedIn adapter (C0)."""

from __future__ import annotations

import pytest

from yieldagent.agents.console.ad_platforms import ad_platform_status
from yieldagent.connectors import Connector, get_connector, manifests, registry
from yieldagent.connectors.linkedin import LinkedInConnector


def test_registry_contains_linkedin() -> None:
    assert "linkedin" in registry()


def test_get_connector_is_case_insensitive() -> None:
    assert get_connector("LinkedIn") is get_connector("linkedin")


def test_get_connector_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_connector("myspace")


def test_linkedin_satisfies_the_protocol() -> None:
    # runtime_checkable Protocol — the adapter exposes the full surface.
    assert isinstance(LinkedInConnector(), Connector)


def test_manifest_shape() -> None:
    m = LinkedInConnector().manifest
    assert m.id == "linkedin"
    assert m.label == "LinkedIn"
    assert m.reliability == "api"
    assert set(m.as_status()) == {"platform", "connected", "can_create"}


def test_manifests_lists_registered_connectors() -> None:
    ids = {m.id for m in manifests()}
    assert "linkedin" in ids


def test_ad_platform_status_still_lists_all_three() -> None:
    platforms = {row["platform"] for row in ad_platform_status()}
    assert {"LinkedIn", "Meta", "Google"} <= platforms


async def test_list_taxonomy_company_sizes_is_local() -> None:
    # company_sizes is a static enum — no network needed.
    sizes = await LinkedInConnector().list_taxonomy("company_sizes")
    assert "11-50" in sizes


async def test_search_targeting_rejects_bad_facet_without_network() -> None:
    with pytest.raises(ValueError, match="facet must be one of"):
        await LinkedInConnector().search_targeting("bogus", "x")


async def test_list_taxonomy_rejects_bad_kind_without_network() -> None:
    with pytest.raises(ValueError, match="kind must be one of"):
        await LinkedInConnector().list_taxonomy("bogus")
