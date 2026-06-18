"""Tests for agent HTTP tools."""

import httpx
import pytest
import respx
from httpx import Response

from app.tools import search_photos

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


@respx.mock
async def test_search_photos_basic_params() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    result = await search_photos.ainvoke(
        {"query": "beach sunset", "tenant_id": "t1", "user_id": "u1", "limit": 10}
    )

    assert result == FAKE_RESULTS
    params = dict(route.calls[0].request.url.params)
    assert params["q"] == "beach sunset"
    assert params["tenant_id"] == "t1"
    assert params["user_id"] == "u1"
    assert params["limit"] == "10"


@respx.mock
async def test_search_photos_omits_unused_filters() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    await search_photos.ainvoke({"query": "beach", "tenant_id": "t1", "user_id": "u1"})

    params = dict(route.calls[0].request.url.params)
    for key in (
        "start_date",
        "end_date",
        "camera_make",
        "min_latitude",
        "max_latitude",
        "min_longitude",
        "max_longitude",
    ):
        assert key not in params


@respx.mock
async def test_search_photos_date_filters() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    await search_photos.ainvoke(
        {
            "query": "beach sunset",
            "tenant_id": "t1",
            "user_id": "u1",
            "start_date": "2023-06-01",
            "end_date": "2023-08-31",
        }
    )

    params = dict(route.calls[0].request.url.params)
    assert params["start_date"] == "2023-06-01"
    assert params["end_date"] == "2023-08-31"
    assert "camera_make" not in params


@respx.mock
async def test_search_photos_camera_make() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    await search_photos.ainvoke(
        {"query": "beach", "tenant_id": "t1", "user_id": "u1", "camera_make": "Canon"}
    )

    params = dict(route.calls[0].request.url.params)
    assert params["camera_make"] == "Canon"
    assert "min_latitude" not in params


@respx.mock
async def test_search_photos_location_filters() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    await search_photos.ainvoke(
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


@respx.mock
async def test_search_photos_all_filters() -> None:
    route = respx.get(SEARCH_URL).mock(return_value=Response(200, json=FAKE_RESULTS))

    result = await search_photos.ainvoke(
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


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@respx.mock
async def test_timeout_raises_runtime_error() -> None:
    def _raise_timeout(request: httpx.Request) -> Response:
        raise httpx.ReadTimeout("timed out", request=request)

    respx.get(SEARCH_URL).mock(side_effect=_raise_timeout)

    with pytest.raises(RuntimeError, match="timed out"):
        await search_photos.ainvoke({"query": "beach", "tenant_id": "t1", "user_id": "u1"})


@respx.mock
async def test_5xx_raises_runtime_error() -> None:
    respx.get(SEARCH_URL).mock(return_value=Response(503, text="Service Unavailable"))

    with pytest.raises(RuntimeError, match="503"):
        await search_photos.ainvoke({"query": "beach", "tenant_id": "t1", "user_id": "u1"})


@respx.mock
async def test_4xx_raises_runtime_error() -> None:
    respx.get(SEARCH_URL).mock(return_value=Response(422, json={"detail": "bad params"}))

    with pytest.raises(RuntimeError, match="422"):
        await search_photos.ainvoke({"query": "beach", "tenant_id": "t1", "user_id": "u1"})
