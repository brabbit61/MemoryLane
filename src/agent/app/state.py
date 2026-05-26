import uuid
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

    from app.models import SearchResult

# Exported so tests can assert the TypedDict's required keys haven't drifted.
REQUIRED_STATE_KEYS: frozenset[str] = frozenset(
    {
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
)


class AgentState(TypedDict):
    query: str
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    limit: int
    messages: list["BaseMessage"]
    tool_results: list[dict[str, Any]]
    iteration: int
    final_results: list["SearchResult"]
    reasoning: list[str]
