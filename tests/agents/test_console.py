"""Tests for console LLM helpers and provider-status shaping."""

from __future__ import annotations

from typing import Any

from yieldagent.agents.console import providers
from yieldagent.agents.console.llm import delta_text


def test_delta_text_handles_plain_string() -> None:
    assert delta_text("hello") == "hello"


def test_delta_text_joins_gemini_text_blocks() -> None:
    content = [{"type": "text", "text": "ab"}, {"type": "text", "text": "cd"}]
    assert delta_text(content) == "abcd"


def test_delta_text_ignores_non_text_blocks_and_other_types() -> None:
    assert delta_text([{"type": "thinking", "text": "x"}]) == ""
    assert delta_text(None) == ""


async def test_status_lists_models_only_when_connected(monkeypatch) -> None:
    async def fake_probe(provider: dict[str, Any]) -> dict[str, Any]:
        connected = provider["id"] == "google"
        return {"connected": connected, "reason": None if connected else "no key"}

    monkeypatch.setattr(providers, "_probe", fake_probe)
    out = await providers.status(force=True)

    google = next(p for p in out if p["id"] == "google")
    openai = next(p for p in out if p["id"] == "openai")
    assert google["connected"] and google["models"]
    assert not openai["connected"] and openai["models"] == []
    assert openai["reason"] == "no key"
