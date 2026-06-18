"""Tests for app.graph — LangGraph StateGraph (Issue #22).

All tests are fully isolated: no real LLM calls, no HTTP calls.

Mocking strategy:
  - planner_node: patch "app.graph.get_llm" to return a MagicMock whose
    .ainvoke is an AsyncMock → avoids real API calls
  - tool_executor_node: patch "app.graph._TOOL_MAP" with a dict whose
    values have .ainvoke as AsyncMock → avoids real HTTP calls
  - reflector_node: pure data transformation — no patching needed
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END

from app.graph import (
    _MAX_ITERATIONS,
    build_graph,
    planner_node,
    reflector_node,
    should_continue,
    tool_executor_node,
)
from app.models import SearchResult
from app.state import AgentState

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
PHOTO_ID_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PHOTO_ID_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
PHOTO_ID_C = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

FAKE_RAW_A: dict[str, Any] = {
    "photo_id": str(PHOTO_ID_A),
    "filename": "beach.jpg",
    "taken_at": "2023-07-15T12:00:00",
    "score": 0.92,
    "url": "https://example.com/beach.jpg",
}
FAKE_RAW_B: dict[str, Any] = {
    "photo_id": str(PHOTO_ID_B),
    "filename": "sunset.jpg",
    "taken_at": "2023-08-01T18:30:00",
    "score": 0.75,
    "url": "https://example.com/sunset.jpg",
}
FAKE_RAW_C: dict[str, Any] = {
    "photo_id": str(PHOTO_ID_C),
    "filename": "mountain.jpg",
    "taken_at": None,
    "score": 0.50,
    "url": "https://example.com/mountain.jpg",
}


def _base_state(**overrides: Any) -> AgentState:
    base: AgentState = {
        "query": "beach sunset",
        "tenant_id": TENANT_ID,
        "user_id": USER_ID,
        "limit": 20,
        "messages": [],
        "tool_results": [],
        "iteration": 0,
        "final_results": [],
        "reasoning": [],
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def _make_ai_with_tool_call(
    tool_name: str = "search_photos",
    call_id: str = "tc1",
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": tool_name,
                "args": {
                    "query": "beach sunset",
                    "tenant_id": str(TENANT_ID),
                    "user_id": str(USER_ID),
                    "limit": 20,
                },
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def _make_search_result(
    photo_id: uuid.UUID = PHOTO_ID_A,
    score: float = 0.9,
) -> SearchResult:
    return SearchResult(
        photo_id=photo_id,
        filename="test.jpg",
        taken_at=None,
        score=score,
        url="https://example.com/test.jpg",
    )


def _mock_llm(ai_response: AIMessage) -> MagicMock:
    """Return a mock LLM object whose .ainvoke returns ai_response."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=ai_response)
    return llm


def _mock_tool(results: list[dict[str, Any]]) -> MagicMock:
    """Return a mock tool object whose .ainvoke returns results."""
    tool = MagicMock()
    tool.ainvoke = AsyncMock(return_value=results)
    return tool


# ---------------------------------------------------------------------------
# Group 1: should_continue routing (pure function — no mocking)
# ---------------------------------------------------------------------------


def test_should_continue_returns_end_when_iteration_at_cap() -> None:
    state = _base_state(iteration=_MAX_ITERATIONS, final_results=[])
    assert should_continue(state) == END


def test_should_continue_returns_end_when_final_results_present() -> None:
    state = _base_state(iteration=1, final_results=[_make_search_result()])
    assert should_continue(state) == END


def test_should_continue_returns_planner_when_no_results_and_low_iteration() -> None:
    state = _base_state(iteration=1, final_results=[])
    assert should_continue(state) == "planner"


def test_should_continue_iteration_boundary() -> None:
    # One below cap → loop back
    assert should_continue(_base_state(iteration=_MAX_ITERATIONS - 1)) == "planner"
    # At cap → stop
    assert should_continue(_base_state(iteration=_MAX_ITERATIONS)) == END


# ---------------------------------------------------------------------------
# Group 2: planner_node
# ---------------------------------------------------------------------------


async def test_planner_node_seeds_messages_on_first_iteration() -> None:
    ai_response = _make_ai_with_tool_call()
    with patch("app.graph.get_llm", return_value=_mock_llm(ai_response)):
        result = await planner_node(_base_state(iteration=0, messages=[]))

    msgs = result["messages"]
    assert isinstance(msgs[0], SystemMessage)
    assert isinstance(msgs[1], HumanMessage)
    assert isinstance(msgs[2], AIMessage)
    assert result["iteration"] == 1
    assert len(result["reasoning"]) == 1


async def test_planner_node_increments_iteration() -> None:
    ai_response = _make_ai_with_tool_call()
    with patch("app.graph.get_llm", return_value=_mock_llm(ai_response)):
        result = await planner_node(_base_state(iteration=1))

    assert result["iteration"] == 2


async def test_planner_node_appends_human_message_on_retry() -> None:
    ai_response = _make_ai_with_tool_call()
    prior_msgs: list[Any] = [
        SystemMessage(content="sys"),
        HumanMessage(content="initial"),
        _make_ai_with_tool_call(),
        ToolMessage(content="[]", tool_call_id="tc0"),
    ]
    with patch("app.graph.get_llm", return_value=_mock_llm(ai_response)):
        result = await planner_node(_base_state(iteration=1, messages=prior_msgs))

    msgs = result["messages"]
    # 4 existing + 1 new HumanMessage (retry) + 1 new AIMessage
    assert len(msgs) == 6
    assert isinstance(msgs[4], HumanMessage)
    assert isinstance(msgs[5], AIMessage)


async def test_planner_node_records_tool_names_in_reasoning() -> None:
    ai_response = _make_ai_with_tool_call("search_photos", "tc2")
    with patch("app.graph.get_llm", return_value=_mock_llm(ai_response)):
        result = await planner_node(_base_state(iteration=0))

    assert "search_photos" in result["reasoning"][0]


# ---------------------------------------------------------------------------
# Group 3: tool_executor_node
# ---------------------------------------------------------------------------


async def test_tool_executor_invokes_correct_tool_and_accumulates_results() -> None:
    ai_msg = _make_ai_with_tool_call("search_photos", "tc1")
    state = _base_state(
        messages=[SystemMessage(content="sys"), HumanMessage(content="q"), ai_msg],
    )

    with patch("app.graph._TOOL_MAP", {"search_photos": _mock_tool([FAKE_RAW_A])}):
        result = await tool_executor_node(state)

    assert result["tool_results"] == [FAKE_RAW_A]
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_call_id == "tc1"


async def test_tool_executor_handles_unknown_tool_name_gracefully() -> None:
    ai_msg = _make_ai_with_tool_call("nonexistent_tool", "tc_bad")
    state = _base_state(
        messages=[SystemMessage(content="sys"), HumanMessage(content="q"), ai_msg],
    )

    with patch("app.graph._TOOL_MAP", {}):
        result = await tool_executor_node(state)  # must not raise

    assert result["tool_results"] == []
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert "Unknown tool" in tool_msgs[0].content


async def test_tool_executor_handles_tool_exception_gracefully() -> None:
    failing_tool = MagicMock()
    failing_tool.ainvoke = AsyncMock(side_effect=RuntimeError("Search service timed out"))

    ai_msg = _make_ai_with_tool_call("search_photos", "tc_err")
    state = _base_state(
        messages=[SystemMessage(content="sys"), HumanMessage(content="q"), ai_msg],
    )

    with patch("app.graph._TOOL_MAP", {"search_photos": failing_tool}):
        result = await tool_executor_node(state)  # must not raise

    assert result["tool_results"] == []
    tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert "timed out" in tool_msgs[0].content


async def test_tool_executor_preserves_prior_tool_results() -> None:
    ai_msg = _make_ai_with_tool_call("search_photos", "tc2")
    state = _base_state(
        messages=[SystemMessage(content="sys"), HumanMessage(content="q"), ai_msg],
        tool_results=[FAKE_RAW_A],  # already something from a prior call
    )

    with patch("app.graph._TOOL_MAP", {"search_photos": _mock_tool([FAKE_RAW_B])}):
        result = await tool_executor_node(state)

    assert FAKE_RAW_A in result["tool_results"]
    assert FAKE_RAW_B in result["tool_results"]
    assert len(result["tool_results"]) == 2


# ---------------------------------------------------------------------------
# Group 4: reflector_node
# ---------------------------------------------------------------------------


async def test_reflector_converts_raw_dicts_to_search_results() -> None:
    state = _base_state(tool_results=[FAKE_RAW_A], final_results=[])
    result = await reflector_node(state)

    assert len(result["final_results"]) == 1
    assert isinstance(result["final_results"][0], SearchResult)
    assert result["final_results"][0].photo_id == PHOTO_ID_A


async def test_reflector_deduplicates_by_photo_id() -> None:
    # Same photo twice + one unique
    duplicate = dict(FAKE_RAW_A)
    state = _base_state(tool_results=[FAKE_RAW_A, duplicate, FAKE_RAW_B], final_results=[])
    result = await reflector_node(state)

    ids = [r.photo_id for r in result["final_results"]]
    assert len(ids) == 2
    assert ids.count(PHOTO_ID_A) == 1


async def test_reflector_clears_tool_results_after_processing() -> None:
    state = _base_state(tool_results=[FAKE_RAW_A])
    result = await reflector_node(state)
    assert result["tool_results"] == []


async def test_reflector_respects_limit() -> None:
    raw_results = [
        {**FAKE_RAW_A, "score": 0.9},
        {**FAKE_RAW_B, "score": 0.7},
        {**FAKE_RAW_C, "score": 0.5},
    ]
    state = _base_state(tool_results=raw_results, final_results=[], limit=1)
    result = await reflector_node(state)

    assert len(result["final_results"]) == 1
    assert result["final_results"][0].score == 0.9  # highest score kept


async def test_reflector_skips_existing_final_results_duplicates() -> None:
    existing = _make_search_result(PHOTO_ID_A, 0.9)
    state = _base_state(tool_results=[FAKE_RAW_A], final_results=[existing])
    result = await reflector_node(state)

    ids = [r.photo_id for r in result["final_results"]]
    assert ids.count(PHOTO_ID_A) == 1  # not doubled


async def test_reflector_appends_reasoning_entry() -> None:
    state = _base_state(tool_results=[FAKE_RAW_A], reasoning=["prior step"])
    result = await reflector_node(state)

    assert len(result["reasoning"]) == 2
    assert "reflector" in result["reasoning"][1]


# ---------------------------------------------------------------------------
# Group 5: build_graph + integration
# ---------------------------------------------------------------------------


def test_build_graph_compiles_without_error() -> None:
    graph = build_graph()
    assert graph is not None
    assert hasattr(graph, "ainvoke")


async def test_graph_terminates_at_iteration_cap() -> None:
    """Integration test: graph must stop at _MAX_ITERATIONS even with no results."""
    ai_response = _make_ai_with_tool_call("search_photos", "tc_iter")

    # LLM always asks for a tool call; tool always returns empty list → no final_results
    with (
        patch("app.graph.get_llm", return_value=_mock_llm(ai_response)),
        patch("app.graph._TOOL_MAP", {"search_photos": _mock_tool([])}),
    ):
        graph = build_graph()
        config = {"configurable": {"thread_id": "test-iter-cap"}}
        initial_state: AgentState = {
            "query": "beach sunset",
            "tenant_id": TENANT_ID,
            "user_id": USER_ID,
            "limit": 20,
            "messages": [],
            "tool_results": [],
            "iteration": 0,
            "final_results": [],
            "reasoning": [],
        }
        final_state = await graph.ainvoke(initial_state, config)

    assert final_state["iteration"] == _MAX_ITERATIONS
    assert final_state["final_results"] == []
