from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from app.graph import build_graph
from app.models import AgentSearchRequest, AgentSearchResponse
from app.state import AgentState

router = APIRouter()


@router.post("/agent/search", response_model=AgentSearchResponse)
async def agent_search(req: AgentSearchRequest) -> AgentSearchResponse:
    graph = build_graph()
    initial_state: AgentState = {
        "query": req.query,
        "tenant_id": req.tenant_id,
        "user_id": req.user_id,
        "limit": req.limit,
        "messages": [],
        "tool_results": [],
        "iteration": 0,
        "final_results": [],
        "reasoning": [],
    }
    config: dict[str, Any] = {"configurable": {"thread_id": str(uuid.uuid4())}}
    final = await graph.ainvoke(initial_state, config=config)
    return AgentSearchResponse(
        results=final["final_results"],
        reasoning=final["reasoning"],
    )
