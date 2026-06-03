"""Shared defaults for the campaign-setup agents.

Kept platform-neutral so both the Meta (`campaign_setup`) and LinkedIn
(`linkedin_setup`) entry points import from one place instead of reaching into
each other's modules.
"""

from __future__ import annotations

# Provider is inferred from the model name by init_chat_model:
#   gemini-*  -> google_genai (requires GOOGLE_API_KEY)
#   claude-*  -> anthropic    (requires ANTHROPIC_API_KEY)
#   gpt-*     -> openai       (requires OPENAI_API_KEY)
# Override at the CLI via --model, or pass an explicit "provider:model" string.
DEFAULT_MODEL = "gemini-3.1-pro-preview"
