"""Tests for ad-platform availability (the agent's single source of truth)."""

from __future__ import annotations

from yieldagent.agents.console.ad_platforms import ad_platform_status


def test_google_is_never_creatable() -> None:
    by_platform = {p["platform"]: p for p in ad_platform_status()}
    assert by_platform["Google"]["can_create"] is False
    assert by_platform["Google"]["connected"] is False


def test_linkedin_reflects_config_presence(monkeypatch) -> None:
    monkeypatch.delenv("LINKEDIN_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("LINKEDIN_AD_ACCOUNT_ID", raising=False)
    linkedin = {p["platform"]: p for p in ad_platform_status()}["LinkedIn"]
    assert linkedin["connected"] is False
    assert linkedin["can_create"] is False


def test_meta_is_connected_but_not_yet_creatable(monkeypatch) -> None:
    monkeypatch.setenv("META_ACCESS_TOKEN", "x")
    monkeypatch.setenv("META_AD_ACCOUNT_ID", "act_1")
    monkeypatch.setenv("META_PAGE_ID", "1")
    meta = {p["platform"]: p for p in ad_platform_status()}["Meta"]
    assert meta["connected"] is True
    assert meta["can_create"] is False
