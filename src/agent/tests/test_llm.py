"""Tests for the LLM module.

Verifies the module imports cleanly, the model is configured correctly,
and all four tools are bound — without making real API calls.
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
    assert "semantic_search" in bound_tool_names
    assert "date_filter_search" in bound_tool_names
    assert "metadata_filter_search" in bound_tool_names
    assert "combined_filter_search" in bound_tool_names


def test_tools_list_contains_all_four() -> None:
    tool_names = {t.name for t in _TOOLS}
    assert tool_names == {
        "semantic_search",
        "date_filter_search",
        "metadata_filter_search",
        "combined_filter_search",
    }


def test_system_prompt_mentions_all_tools() -> None:
    for name in (
        "semantic_search",
        "date_filter_search",
        "metadata_filter_search",
        "combined_filter_search",
    ):
        assert name in SYSTEM_PROMPT, f"SYSTEM_PROMPT missing routing hint for {name}"
