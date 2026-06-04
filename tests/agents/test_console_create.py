"""Tests for the create-draft tool's result shape and the runtime's routing.

Covers the failure paths that must NOT look like success in the UI: an
incomplete campaign, a LinkedIn publish error, and the runtime turning each into
an `error` event rather than a `created` (false-success) one.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from yieldagent.agents.console import runtime, tools


def _complete() -> dict[str, Any]:
    return {
        "name": "Q3 Demand Gen",
        "objective": "leads",
        "line_items": [
            {
                "name": "Main",
                "budget": {"amount": 300, "currency": "EUR"},
                "flight": {"start_date": "2026-06-16", "end_date": "2026-06-30"},
                "targeting": {"audience": {"description": "x", "geos": ["US"]}},
            }
        ],
        "ads": [
            {
                "name": "Ad 1",
                "line_item_name": "Main",
                "creative": {"name": "c1", "existing_post_urn": "urn:li:share:1"},
            }
        ],
    }


async def test_create_draft_incomplete_returns_structured_failure() -> None:
    result = await tools.create_linkedin_draft.ainvoke({"campaign": {"name": "x"}})
    assert result["created"] is False
    assert "incomplete" in result["error"].lower()
    assert result["issues"]


async def test_create_draft_publish_error_is_caught_not_raised(monkeypatch) -> None:
    """A LinkedIn failure must come back as created=False, never an exception."""
    from yieldagent.integrations.linkedin import server as li_server

    async def boom(_campaign: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("publish failed: 403 not allowed")

    monkeypatch.setattr(li_server, "publish_draft_campaign", boom)
    result = await tools.create_linkedin_draft.ainvoke({"campaign": _complete()})
    assert result["created"] is False
    assert "403 not allowed" in result["error"]


class _FakeAgent:
    """Minimal stand-in for the console agent: replays one tool ToolMessage."""

    def __init__(self, tool_message: Any) -> None:
        self._msg = tool_message

    async def astream(self, _inp, _config, stream_mode=None):  # noqa: ANN001
        yield ("updates", {"tools": {"messages": [self._msg]}})


def _tool_message(content: str) -> SimpleNamespace:
    return SimpleNamespace(type="tool", name="create_linkedin_draft", content=content)


async def _events(monkeypatch, content: str) -> list[tuple[str, dict]]:
    monkeypatch.setattr(
        runtime, "get_console_agent", lambda _model: _FakeAgent(_tool_message(content))
    )
    return [ev async for ev in runtime.run("go", "t", None)]


async def test_runtime_emits_created_on_success(monkeypatch) -> None:
    result = {"created": True, "campaign_id": "123", "lcm_url": "http://lcm"}
    events = await _events(monkeypatch, json.dumps(result))
    assert ("created", {"result": result}) in events
    assert not any(name == "error" for name, _ in events)


async def test_runtime_emits_error_on_structured_failure(monkeypatch) -> None:
    content = json.dumps({"created": False, "error": "LinkedIn did not create the draft: 403"})
    events = await _events(monkeypatch, content)
    assert ("error", {"message": "LinkedIn did not create the draft: 403"}) in events
    assert not any(name == "created" for name, _ in events)


async def test_runtime_emits_error_on_raw_exception_string(monkeypatch) -> None:
    """If the ToolNode swallows an exception into a plain string, route it to error,
    never a false 'created' banner."""
    events = await _events(monkeypatch, "Traceback: KeyError 'campaign'")
    assert any(name == "error" for name, _ in events)
    assert not any(name == "created" for name, _ in events)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
