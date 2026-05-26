"""
Contract tests for Pydantic models.

These tests define the expected shape before any implementation exists.
They also act as a cross-service contract: SearchResult must stay
shape-compatible with services/search/app/models.py:SearchResult.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import AgentSearchRequest, AgentSearchResponse, SearchResult

# ---------------------------------------------------------------------------
# SearchResult — contract test (must match search-svc shape exactly)
# ---------------------------------------------------------------------------

SEARCH_RESULT_FIELDS = {"photo_id", "filename", "taken_at", "score", "url"}


def test_search_result_has_expected_fields() -> None:
    assert set(SearchResult.model_fields.keys()) == SEARCH_RESULT_FIELDS


def test_search_result_happy_path() -> None:
    r = SearchResult(
        photo_id=uuid.uuid4(),
        filename="beach.jpg",
        taken_at=datetime(2024, 6, 1, tzinfo=UTC),
        score=0.91,
        url="https://s3.example.com/presigned",
    )
    assert r.filename == "beach.jpg"
    assert r.score == 0.91


def test_search_result_optional_fields_accept_none() -> None:
    r = SearchResult(
        photo_id=uuid.uuid4(),
        filename=None,
        taken_at=None,
        score=0.5,
        url="https://s3.example.com/presigned",
    )
    assert r.filename is None
    assert r.taken_at is None


def test_search_result_score_coerces_int_to_float() -> None:
    r = SearchResult(
        photo_id=uuid.uuid4(),
        filename=None,
        taken_at=None,
        score=1,
        url="https://s3.example.com/presigned",
    )
    assert isinstance(r.score, float)


def test_search_result_rejects_invalid_photo_id() -> None:
    with pytest.raises(ValidationError):
        SearchResult(
            photo_id="not-a-uuid",
            filename=None,
            taken_at=None,
            score=0.5,
            url="https://s3.example.com/presigned",
        )


def test_search_result_url_is_required() -> None:
    with pytest.raises(ValidationError):
        SearchResult(
            photo_id=uuid.uuid4(),
            filename=None,
            taken_at=None,
            score=0.5,
        )


# ---------------------------------------------------------------------------
# AgentSearchRequest
# ---------------------------------------------------------------------------


def test_agent_search_request_happy_path() -> None:
    req = AgentSearchRequest(
        query="sunset at the beach",
        tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    )
    assert req.query == "sunset at the beach"
    assert req.limit == 20


def test_agent_search_request_limit_defaults_to_20() -> None:
    req = AgentSearchRequest(
        query="dogs",
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )
    assert req.limit == 20


def test_agent_search_request_limit_can_be_overridden() -> None:
    req = AgentSearchRequest(
        query="dogs",
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        limit=5,
    )
    assert req.limit == 5


def test_agent_search_request_requires_query() -> None:
    with pytest.raises(ValidationError):
        AgentSearchRequest(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )


def test_agent_search_request_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        AgentSearchRequest(
            query="",
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )


def test_agent_search_request_rejects_invalid_user_id() -> None:
    with pytest.raises(ValidationError):
        AgentSearchRequest(
            query="dogs",
            tenant_id=uuid.uuid4(),
            user_id="not-a-uuid",
        )


def test_agent_search_request_rejects_invalid_tenant_id() -> None:
    with pytest.raises(ValidationError):
        AgentSearchRequest(
            query="dogs",
            tenant_id="not-a-uuid",
            user_id=uuid.uuid4(),
        )


def test_agent_search_request_requires_tenant_id() -> None:
    with pytest.raises(ValidationError):
        AgentSearchRequest(
            query="dogs",
            user_id=uuid.uuid4(),
        )


# ---------------------------------------------------------------------------
# AgentSearchResponse
# ---------------------------------------------------------------------------


def test_agent_search_response_happy_path() -> None:
    result = SearchResult(
        photo_id=uuid.uuid4(),
        filename="a.jpg",
        taken_at=None,
        score=0.8,
        url="https://example.com/a.jpg",
    )
    resp = AgentSearchResponse(
        results=[result],
        reasoning=["called semantic_search with query='sunset'", "results sufficient, stopping"],
    )
    assert len(resp.results) == 1
    assert len(resp.reasoning) == 2


def test_agent_search_response_allows_empty_results() -> None:
    resp = AgentSearchResponse(results=[], reasoning=["no matching photos found"])
    assert resp.results == []


def test_agent_search_response_allows_empty_reasoning() -> None:
    resp = AgentSearchResponse(results=[], reasoning=[])
    assert resp.reasoning == []


def test_agent_search_response_requires_results_field() -> None:
    with pytest.raises(ValidationError):
        AgentSearchResponse(reasoning=[])


def test_agent_search_response_requires_reasoning_field() -> None:
    with pytest.raises(ValidationError):
        AgentSearchResponse(results=[])
