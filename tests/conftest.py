"""Shared pytest fixtures for the YieldAgent test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip LLM + ad-provider credentials and the live-run flag so tests never
    accidentally hit real APIs or live ad accounts."""
    for var in (
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "LINKEDIN_ACCESS_TOKEN",
        "META_ACCESS_TOKEN",
        "YIELDAGENT_ALLOW_LIVE",
    ):
        monkeypatch.delenv(var, raising=False)
