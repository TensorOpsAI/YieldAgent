"""Tests for the LLM provider abstraction in the campaign-setup agent.

These tests pin the contract that the agent must be provider-agnostic:
node factories must dispatch through `init_chat_model`, accept any model name
LangChain recognises (claude-*, gemini-*, gpt-*), and bind structured output
to the right domain type. They do not exercise any real LLM.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from yieldagent.agents.campaign_setup import nodes
from yieldagent.domain import Brief, Campaign


def test_default_model_is_gemini_flash() -> None:
    assert nodes.DEFAULT_MODEL == "gemini-2.5-flash"


@patch("yieldagent.agents.campaign_setup.nodes.init_chat_model")
def test_parse_brief_uses_init_chat_model_with_default(mock_init: MagicMock) -> None:
    """The default node must dispatch via init_chat_model with DEFAULT_MODEL."""
    nodes.make_parse_brief_node()

    mock_init.assert_called_once_with(nodes.DEFAULT_MODEL)
    mock_init.return_value.with_structured_output.assert_called_once_with(Brief)


@patch("yieldagent.agents.campaign_setup.nodes.init_chat_model")
def test_parse_brief_respects_model_override(mock_init: MagicMock) -> None:
    """Passing a model name (e.g. claude-sonnet-4-6) must propagate to init_chat_model."""
    nodes.make_parse_brief_node("claude-sonnet-4-6")

    mock_init.assert_called_once_with("claude-sonnet-4-6")


@patch("yieldagent.agents.campaign_setup.nodes.init_chat_model")
def test_plan_campaign_uses_init_chat_model_with_default(mock_init: MagicMock) -> None:
    nodes.make_plan_campaign_node()

    mock_init.assert_called_once_with(nodes.DEFAULT_MODEL)
    mock_init.return_value.with_structured_output.assert_called_once_with(Campaign)


@patch("yieldagent.agents.campaign_setup.nodes.init_chat_model")
def test_plan_campaign_respects_model_override(mock_init: MagicMock) -> None:
    nodes.make_plan_campaign_node("gpt-4o")

    mock_init.assert_called_once_with("gpt-4o")


@patch("yieldagent.agents.campaign_setup.nodes.init_chat_model")
@pytest.mark.parametrize(
    "model_name",
    ["gemini-2.5-flash", "claude-sonnet-4-6", "gpt-4o", "google_genai:gemini-2.5-pro"],
)
def test_both_factories_accept_any_provider_string(
    mock_init: MagicMock, model_name: str
) -> None:
    """Provider dispatch is delegated entirely to init_chat_model — no allowlist here."""
    nodes.make_parse_brief_node(model_name)
    nodes.make_plan_campaign_node(model_name)

    assert mock_init.call_count == 2
    for call in mock_init.call_args_list:
        assert call.args == (model_name,)
