import uuid
from typing import Any, TypedDict

from langchain_core.messages import BaseMessage

from app.models import SearchResult


class AgentState(TypedDict):
    query: str
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    limit: int
    messages: list[BaseMessage]
    tool_results: list[dict[str, Any]]
    iteration: int
    final_results: list[SearchResult]
    reasoning: list[str]
