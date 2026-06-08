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


def test_meta_is_planned_not_yet_available() -> None:
    # Meta has no connector yet, so it always shows as coming soon regardless of env.
    meta = {p["platform"]: p for p in ad_platform_status()}["Meta"]
    assert meta["connected"] is False
    assert meta["can_create"] is False
