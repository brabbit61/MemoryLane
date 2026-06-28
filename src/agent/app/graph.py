"""LangGraph StateGraph for MemoryLane search agent (Issue #22).

Topology:
    START → planner → tools → reflector ─→ END
                                  │
                                  └→ planner  (loop, max _MAX_ITERATIONS)
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.llm import SYSTEM_PROMPT, get_llm
from app.models import SearchResult
from app.state import AgentState
from app.tools import TOOLS

# O(1) tool dispatch — built once at import time
_TOOL_MAP: dict[str, Any] = {t.name: t for t in TOOLS}

_MAX_ITERATIONS: int = 3


# ---------------------------------------------------------------------------
# Private helpers (pure, no I/O)
# ---------------------------------------------------------------------------


def _build_initial_prompt(state: AgentState) -> str:
    return (
        f"Search query: {state['query']}\n"
        f"tenant_id: {state['tenant_id']}\n"
        f"user_id: {state['user_id']}\n"
        f"Return up to {state['limit']} results."
    )


def _build_retry_prompt(state: AgentState) -> str:
    found = len(state["tool_results"])
    return (
        f"The previous search returned {found} results. "
        f"Please refine the search to find more relevant photos for: {state['query']}"
    )


def _describe_tool_calls(ai_message: AIMessage) -> str:
    if not ai_message.tool_calls:
        return "planner: no tool calls generated"
    names = ", ".join(tc["name"] for tc in ai_message.tool_calls)
    return f"planner: requesting tools [{names}]"


def _get_last_ai_message(messages: list[Any]) -> AIMessage:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return msg
    raise ValueError("No AIMessage found in message history")


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


async def planner_node(state: AgentState) -> dict[str, Any]:
    """Invoke the LLM to decide which tool(s) to call next."""
    llm = get_llm()
    messages: list[Any] = list(state["messages"])

    if not messages:
        # First iteration — seed the conversation
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=_build_initial_prompt(state)),
        ]
    else:
        # Subsequent iterations — add context about what was found so far
        messages.append(HumanMessage(content=_build_retry_prompt(state)))

    ai_message: AIMessage = await llm.ainvoke(messages)
    messages.append(ai_message)

    return {
        "messages": messages,
        "reasoning": state["reasoning"] + [_describe_tool_calls(ai_message)],
        "iteration": state["iteration"] + 1,
    }


async def tool_executor_node(state: AgentState) -> dict[str, Any]:
    """Execute every tool call from the last AIMessage; accumulate raw results."""
    messages: list[Any] = list(state["messages"])
    last_ai = _get_last_ai_message(messages)

    new_tool_results: list[dict[str, Any]] = []
    new_messages: list[Any] = []

    for tool_call in last_ai.tool_calls:
        name: str = tool_call["name"]
        args: dict[str, Any] = dict(tool_call["args"])
        tool_call_id: str = tool_call.get("id") or ""

        tool = _TOOL_MAP.get(name)
        if tool is None:
            content = json.dumps({"error": f"Unknown tool: {name}"})
            status: str = "error"
        else:
            try:
                raw: list[dict[str, Any]] = await tool.ainvoke(args)
                new_tool_results.extend(raw)
                content = json.dumps(raw)
                status = "success"
            except Exception as exc:
                content = json.dumps({"error": str(exc)})
                status = "error"

        new_messages.append(ToolMessage(content=content, tool_call_id=tool_call_id, status=status))

    return {
        "messages": messages + new_messages,
        "tool_results": state["tool_results"] + new_tool_results,
    }


async def reflector_node(state: AgentState) -> dict[str, Any]:
    """Convert raw tool_results → SearchResult, deduplicate, sort, trim to limit."""
    seen: set[uuid.UUID] = {r.photo_id for r in state["final_results"]}
    new_results: list[SearchResult] = []

    for raw in state["tool_results"]:
        try:
            result = SearchResult.model_validate(raw)
        except Exception:  # noqa: S112 — malformed raw dicts are silently skipped
            continue
        if result.photo_id not in seen:
            seen.add(result.photo_id)
            new_results.append(result)

    all_results: list[SearchResult] = list(state["final_results"]) + new_results
    all_results.sort(key=lambda r: r.score, reverse=True)
    all_results = all_results[: state["limit"]]

    reasoning_entry = (
        f"reflector: {len(new_results)} new unique results "
        f"({len(all_results)} total, limit={state['limit']})"
    )

    return {
        "final_results": all_results,
        "tool_results": [],  # cleared so the next iteration starts fresh
        "reasoning": state["reasoning"] + [reasoning_entry],
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def should_continue(state: AgentState) -> str:
    """Terminate when the iteration cap is hit or results have been found."""
    if state["iteration"] >= _MAX_ITERATIONS or bool(state["final_results"]):
        return END
    return "planner"


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    """Compile and return the MemoryLane search StateGraph with MemorySaver.

    Returns Any because CompiledStateGraph has four generic type params that
    vary across langgraph versions, making a precise annotation fragile.
    """
    g: StateGraph = StateGraph(AgentState)  # type: ignore[type-arg]
    g.add_node("planner", planner_node)
    g.add_node("tools", tool_executor_node)
    g.add_node("reflector", reflector_node)
    g.set_entry_point("planner")
    g.add_edge("planner", "tools")
    g.add_edge("tools", "reflector")
    g.add_conditional_edges(
        "reflector",
        should_continue,
        {END: END, "planner": "planner"},
    )
    return g.compile(checkpointer=MemorySaver())
