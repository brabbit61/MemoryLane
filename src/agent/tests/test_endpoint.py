"""Tests for POST /agent/search endpoint (Issue #23).

Mocking strategy: patch "app.routers.agent.build_graph" to return a MagicMock
whose .ainvoke is an AsyncMock → avoids real LLM or search service calls.
Uses the shared AsyncClient fixture from conftest.py.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import SearchResult

TENANT_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000001"))
USER_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000002"))
PHOTO_ID_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PHOTO_ID_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

_RESULT_A = SearchResult(
    photo_id=PHOTO_ID_A,
    filename="beach.jpg",
    taken_at=None,
    score=0.92,
    url="https://example.com/beach.jpg",
)
_RESULT_B = SearchResult(
    photo_id=PHOTO_ID_B,
    filename="sunset.jpg",
    taken_at=None,
    score=0.75,
    url="https://example.com/sunset.jpg",
)

_VALID_BODY: dict[str, Any] = {
    "query": "beach sunset",
    "tenant_id": TENANT_ID,
    "user_id": USER_ID,
    "limit": 20,
}


def _mock_graph(final_results: list[SearchResult], reasoning: list[str]) -> MagicMock:
    graph = MagicMock()
    graph.ainvoke = AsyncMock(return_value={"final_results": final_results, "reasoning": reasoning})
    return graph


# ---------------------------------------------------------------------------
# Group 1: happy path
# ---------------------------------------------------------------------------


async def test_agent_search_returns_200_with_results_and_reasoning(client: Any) -> None:
    reasoning = ["planner: requesting tools [semantic_search]", "reflector: 1 new unique results"]
    with patch(
        "app.routers.agent.build_graph",
        return_value=_mock_graph([_RESULT_A, _RESULT_B], reasoning),
    ):
        response = await client.post("/agent/search", json=_VALID_BODY)

    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 2
    assert body["results"][0]["photo_id"] == str(PHOTO_ID_A)
    assert len(body["reasoning"]) == 2


async def test_agent_search_empty_results_returns_200(client: Any) -> None:
    with patch(
        "app.routers.agent.build_graph",
        return_value=_mock_graph([], ["reflector: 0 new unique results (0 total, limit=20)"]),
    ):
        response = await client.post("/agent/search", json=_VALID_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []


async def test_agent_search_reasoning_forwarded_verbatim(client: Any) -> None:
    reasoning = ["step one", "step two", "step three"]
    with patch(
        "app.routers.agent.build_graph",
        return_value=_mock_graph([_RESULT_A], reasoning),
    ):
        response = await client.post("/agent/search", json=_VALID_BODY)

    assert response.json()["reasoning"] == reasoning


# ---------------------------------------------------------------------------
# Group 2: request validation
# ---------------------------------------------------------------------------


async def test_agent_search_missing_tenant_id_returns_422(client: Any) -> None:
    body = {k: v for k, v in _VALID_BODY.items() if k != "tenant_id"}
    response = await client.post("/agent/search", json=body)
    assert response.status_code == 422


async def test_agent_search_empty_query_returns_422(client: Any) -> None:
    body = {**_VALID_BODY, "query": ""}
    response = await client.post("/agent/search", json=body)
    assert response.status_code == 422
