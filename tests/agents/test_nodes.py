"""Tests for the LLM provider abstraction in the campaign-setup agent.

These tests pin the contract that the agent must be provider-agnostic:
node factories dispatch through `init_chat_model`, accept any model name
LangChain recognises (claude-*, gemini-*, gpt-*), and bind structured output
to the right domain type. They do not exercise any real LLM.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from yieldagent.agents.campaign_setup import nodes
from yieldagent.domain import Brief, Campaign


# --- Provider resolution -----------------------------------------------------
# Bare `gemini-*` strings are ambiguous in LangChain: `init_chat_model` routes
# them to Vertex AI by default, which requires full GCP setup. We pin Google AI
# Studio (the Gemini API keyed by GOOGLE_API_KEY) by prefixing `google_genai:`.


@pytest.mark.parametrize(
    "input_name, expected",
    [
        ("gemini-2.5-flash", "google_genai:gemini-2.5-flash"),
        ("gemini-2.5-pro", "google_genai:gemini-2.5-pro"),
        ("gemini-3.5-flash", "google_genai:gemini-3.5-flash"),
        # Non-gemini models are passed through untouched.
        ("claude-sonnet-4-6", "claude-sonnet-4-6"),
        ("gpt-4o", "gpt-4o"),
        # Explicit provider prefixes are respected — caller knows what they want.
        ("google_genai:gemini-3.1-pro-preview", "google_genai:gemini-3.1-pro-preview"),
        ("google_vertexai:gemini-2.5-pro", "google_vertexai:gemini-2.5-pro"),
        ("anthropic:claude-sonnet-4-6", "anthropic:claude-sonnet-4-6"),
    ],
)
def test_resolve_model_name(input_name: str, expected: str) -> None:
    assert nodes._resolve_model_name(input_name) == expected


# --- Factory dispatch --------------------------------------------------------


@patch("yieldagent.agents.campaign_setup.nodes.init_chat_model")
def test_parse_brief_uses_init_chat_model_with_default(mock_init: MagicMock) -> None:
    nodes.make_parse_brief_node()

    mock_init.assert_called_once_with(nodes._resolve_model_name(nodes.DEFAULT_MODEL))
    mock_init.return_value.with_structured_output.assert_called_once_with(Brief)


@patch("yieldagent.agents.campaign_setup.nodes.init_chat_model")
def test_parse_brief_respects_anthropic_override(mock_init: MagicMock) -> None:
    nodes.make_parse_brief_node("claude-sonnet-4-6")

    mock_init.assert_called_once_with("claude-sonnet-4-6")


@patch("yieldagent.agents.campaign_setup.nodes.init_chat_model")
def test_plan_campaign_uses_init_chat_model_with_default(mock_init: MagicMock) -> None:
    nodes.make_plan_campaign_node()

    mock_init.assert_called_once_with(nodes._resolve_model_name(nodes.DEFAULT_MODEL))
    mock_init.return_value.with_structured_output.assert_called_once_with(Campaign)


@patch("yieldagent.agents.campaign_setup.nodes.init_chat_model")
def test_plan_campaign_respects_openai_override(mock_init: MagicMock) -> None:
    nodes.make_plan_campaign_node("gpt-4o")

    mock_init.assert_called_once_with("gpt-4o")
