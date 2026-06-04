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


class _FakeLinkedIn:
    """Async-context stand-in for the LinkedIn client used by _ad_previews."""

    def __init__(self, post: dict | None = None, image: dict | None = None) -> None:
        self._post = post or {}
        self._image = image or {}

    async def __aenter__(self) -> _FakeLinkedIn:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        pass

    async def get_post(self, _urn: str) -> dict:
        return self._post

    async def get_image(self, _urn: str) -> dict:
        return self._image


async def test_ad_preview_from_existing_post(monkeypatch) -> None:
    post = {
        "commentary": "Static floors cost money.",
        "content": {
            "article": {
                "title": "Setting floors without killing win rate",
                "source": "https://tensorops.ai/blog/floors",
                "thumbnail": "urn:li:image:1",
            }
        },
    }
    monkeypatch.setattr(
        tools, "client_from_env",
        lambda: _FakeLinkedIn(post=post, image={"downloadUrl": "https://media/x.jpg"}),
    )
    campaign = {"ads": [{"name": "Ad1", "creative": {"existing_post_urn": "urn:li:share:9"}}]}
    previews = await tools._ad_previews(campaign)
    p = previews["Ad1"]
    assert p["source"] == "existing_post"
    assert p["headline"] == "Setting floors without killing win rate"
    assert p["text"] == "Static floors cost money."
    assert p["url"] == "https://tensorops.ai/blog/floors"
    assert p["image_url"] == "https://media/x.jpg"


async def test_ad_preview_from_ad_copy(monkeypatch) -> None:
    monkeypatch.setattr(tools, "client_from_env", lambda: _FakeLinkedIn())
    campaign = {
        "ads": [
            {
                "name": "Ad2",
                "creative": {
                    "headline": "Scale your startup",
                    "primary_text": "TensorOps helps you ship AI",
                    "landing_url": "https://tensorops.ai",
                },
            }
        ]
    }
    previews = await tools._ad_previews(campaign)
    assert previews["Ad2"] == {
        "source": "ad_copy",
        "headline": "Scale your startup",
        "text": "TensorOps helps you ship AI",
        "url": "https://tensorops.ai",
        "image_url": None,
    }


async def test_ad_preview_best_effort_on_post_failure(monkeypatch) -> None:
    class _Boom(_FakeLinkedIn):
        async def get_post(self, _urn: str) -> dict:
            raise RuntimeError("post fetch failed")

    monkeypatch.setattr(tools, "client_from_env", lambda: _Boom())
    campaign = {"ads": [{"name": "Ad3", "creative": {"existing_post_urn": "urn:li:share:9"}}]}
    previews = await tools._ad_previews(campaign)
    # a failed fetch still yields a sparse preview, never raises
    assert previews["Ad3"]["source"] == "existing_post"
    assert previews["Ad3"]["headline"] is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
