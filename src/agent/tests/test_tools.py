"""Tests for agent HTTP tools.

Each tool is tested for:
- Correct URL and query params sent to the search service
- None params are omitted from the request
- Response is parsed and returned as-is
- Timeouts raise RuntimeError
- 5xx responses raise RuntimeError
"""

import httpx
import pytest
import respx
from httpx import Response

from app.tools import (
    combined_filter_search,
    date_filter_search,
    metadata_filter_search,
    semantic_search,
)

SEARCH_URL = "http://search-svc:8002/search"

FAKE_RESULTS = [
    {
        "photo_id": "00000000-0000-0000-0000-000000000001",
        "filename": "beach.jpg",
        "taken_at": "2023-07-15T12:00:00",
        "score": 0.92,
        "url": "https://example.com/beach.jpg",
    }
]


# ---------------------------------------------------------------------------
# semantic_search
# ---------------------------------------------------------------------------


@respx.mock
async def test_semantic_search_sends_correct_params() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    result = await semantic_search.ainvoke(
        {"query": "beach sunset", "tenant_id": "t1", "user_id": "u1", "limit": 10}
    )

    assert result == FAKE_RESULTS
    assert route.called
    params = dict(route.calls[0].request.url.params)
    assert params["q"] == "beach sunset"
    assert params["tenant_id"] == "t1"
    assert params["user_id"] == "u1"
    assert params["limit"] == "10"


@respx.mock
async def test_semantic_search_no_extra_params() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    await semantic_search.ainvoke({"query": "beach", "tenant_id": "t1", "user_id": "u1"})

    params = dict(route.calls[0].request.url.params)
    assert "start_date" not in params
    assert "end_date" not in params
    assert "camera_make" not in params


# ---------------------------------------------------------------------------
# date_filter_search
# ---------------------------------------------------------------------------


@respx.mock
async def test_date_filter_search_sends_dates() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    result = await date_filter_search.ainvoke(
        {
            "query": "beach sunset",
            "tenant_id": "t1",
            "user_id": "u1",
            "start_date": "2023-06-01",
            "end_date": "2023-08-31",
        }
    )

    assert result == FAKE_RESULTS
    params = dict(route.calls[0].request.url.params)
    assert params["start_date"] == "2023-06-01"
    assert params["end_date"] == "2023-08-31"
    assert "camera_make" not in params


# ---------------------------------------------------------------------------
# metadata_filter_search
# ---------------------------------------------------------------------------


@respx.mock
async def test_metadata_filter_search_sends_camera_make() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    await metadata_filter_search.ainvoke(
        {"query": "beach", "tenant_id": "t1", "user_id": "u1", "camera_make": "Canon"}
    )

    params = dict(route.calls[0].request.url.params)
    assert params["camera_make"] == "Canon"


@respx.mock
async def test_metadata_filter_search_omits_none_params() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    await metadata_filter_search.ainvoke(
        {
            "query": "beach",
            "tenant_id": "t1",
            "user_id": "u1",
            "camera_make": "Canon",
            # lat/lon intentionally omitted → should not appear in request
        }
    )

    params = dict(route.calls[0].request.url.params)
    assert "min_latitude" not in params
    assert "max_latitude" not in params
    assert "min_longitude" not in params
    assert "max_longitude" not in params


@respx.mock
async def test_metadata_filter_search_sends_location() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    await metadata_filter_search.ainvoke(
        {
            "query": "Paris",
            "tenant_id": "t1",
            "user_id": "u1",
            "min_latitude": 48.8,
            "max_latitude": 48.9,
            "min_longitude": 2.3,
            "max_longitude": 2.4,
        }
    )

    params = dict(route.calls[0].request.url.params)
    assert params["min_latitude"] == "48.8"
    assert params["max_latitude"] == "48.9"
    assert params["min_longitude"] == "2.3"
    assert params["max_longitude"] == "2.4"
    assert "camera_make" not in params


# ---------------------------------------------------------------------------
# combined_filter_search
# ---------------------------------------------------------------------------


@respx.mock
async def test_combined_filter_search_sends_all_params() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    result = await combined_filter_search.ainvoke(
        {
            "query": "Paris trip",
            "tenant_id": "t1",
            "user_id": "u1",
            "start_date": "2023-06-01",
            "end_date": "2023-08-31",
            "camera_make": "Canon",
            "min_latitude": 48.8,
            "max_latitude": 48.9,
            "min_longitude": 2.3,
            "max_longitude": 2.4,
        }
    )

    assert result == FAKE_RESULTS
    params = dict(route.calls[0].request.url.params)
    assert params["start_date"] == "2023-06-01"
    assert params["end_date"] == "2023-08-31"
    assert params["camera_make"] == "Canon"
    assert params["min_latitude"] == "48.8"
    assert params["max_latitude"] == "48.9"
    assert params["min_longitude"] == "2.3"
    assert params["max_longitude"] == "2.4"


@respx.mock
async def test_combined_filter_search_omits_none_params() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    await combined_filter_search.ainvoke(
        {
            "query": "Paris trip",
            "tenant_id": "t1",
            "user_id": "u1",
            "start_date": "2023-06-01",
            "end_date": "2023-08-31",
            # no camera or location params
        }
    )

    params = dict(route.calls[0].request.url.params)
    assert params["start_date"] == "2023-06-01"
    assert "camera_make" not in params
    assert "min_latitude" not in params
    assert "max_latitude" not in params
    assert "min_longitude" not in params
    assert "max_longitude" not in params


# ---------------------------------------------------------------------------
# Error handling (shared _call_search path — tested via semantic_search)
# ---------------------------------------------------------------------------


@respx.mock
async def test_timeout_raises_runtime_error() -> None:
    def _raise_timeout(request: httpx.Request) -> Response:
        raise httpx.ReadTimeout("timed out", request=request)

    respx.get(SEARCH_URL).mock(side_effect=_raise_timeout)

    with pytest.raises(RuntimeError, match="timed out"):
        await semantic_search.ainvoke({"query": "beach", "tenant_id": "t1", "user_id": "u1"})


@respx.mock
async def test_5xx_raises_runtime_error() -> None:
    respx.get(SEARCH_URL).mock(return_value=Response(503, text="Service Unavailable"))

    with pytest.raises(RuntimeError, match="503"):
        await semantic_search.ainvoke({"query": "beach", "tenant_id": "t1", "user_id": "u1"})


@respx.mock
async def test_4xx_raises_runtime_error() -> None:
    respx.get(SEARCH_URL).mock(return_value=Response(422, json={"detail": "bad params"}))

    with pytest.raises(RuntimeError, match="422"):
        await semantic_search.ainvoke({"query": "beach", "tenant_id": "t1", "user_id": "u1"})
