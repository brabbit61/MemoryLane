"""Tests for the LLM module.

Verifies the module imports cleanly, the model is configured correctly,
and the search tool is bound — without making real API calls.
"""

from unittest.mock import patch

from langchain_core.runnables import Runnable

from app.llm import _TOOLS, SYSTEM_PROMPT, get_llm


def test_get_llm_returns_chat_model() -> None:
    with patch("app.llm.settings") as mock_settings:
        mock_settings.claude_model = "claude-sonnet-4-6"
        mock_settings.anthropic_api_key = "sk-test-key"
        llm = get_llm()

    assert isinstance(llm, Runnable)


def test_get_llm_has_bound_tools() -> None:
    with patch("app.llm.settings") as mock_settings:
        mock_settings.claude_model = "claude-sonnet-4-6"
        mock_settings.anthropic_api_key = "sk-test-key"
        llm = get_llm()

    # RunnableBinding wraps the model when tools are bound; it exposes kwargs
    assert hasattr(llm, "kwargs"), "Expected a RunnableBinding with .kwargs after bind_tools"
    bound_tool_names = {t["name"] for t in llm.kwargs.get("tools", [])}
    assert "search_photos" in bound_tool_names


def test_tools_list_contains_search_photos() -> None:
    tool_names = {t.name for t in _TOOLS}
    assert tool_names == {"search_photos"}


def test_system_prompt_mentions_search_photos() -> None:
    assert "search_photos" in SYSTEM_PROMPT
