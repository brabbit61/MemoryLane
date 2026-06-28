import uuid

from app.state import AgentState


def test_agent_state_can_be_constructed_as_dict() -> None:
    state: AgentState = {
        "query": "sunset at the beach",
        "tenant_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "user_id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "limit": 20,
        "messages": [],
        "tool_results": [],
        "iteration": 0,
        "final_results": [],
        "reasoning": [],
    }
    assert state["query"] == "sunset at the beach"
    assert state["iteration"] == 0


def test_agent_state_iteration_is_mutable() -> None:
    state: AgentState = {
        "query": "dogs",
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "limit": 10,
        "messages": [],
        "tool_results": [],
        "iteration": 0,
        "final_results": [],
        "reasoning": [],
    }
    state["iteration"] += 1
    assert state["iteration"] == 1


def test_agent_state_reasoning_is_appendable() -> None:
    state: AgentState = {
        "query": "dogs",
        "tenant_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "limit": 10,
        "messages": [],
        "tool_results": [],
        "iteration": 0,
        "final_results": [],
        "reasoning": [],
    }
    state["reasoning"].append("called semantic_search")
    assert state["reasoning"] == ["called semantic_search"]


def test_agent_state_has_all_expected_annotations() -> None:
    expected = {
        "query",
        "tenant_id",
        "user_id",
        "limit",
        "messages",
        "tool_results",
        "iteration",
        "final_results",
        "reasoning",
    }
    assert expected.issubset(AgentState.__annotations__.keys())
