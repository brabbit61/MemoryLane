import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.db import get_db
from app.main import app

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture()
def override_db() -> Generator[AsyncMock, None, None]:
    mock_db = AsyncMock()

    async def _override() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = _override
    try:
        yield mock_db
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_search_returns_results_in_descending_score_order(
    client: AsyncClient,
    override_db: AsyncMock,
) -> None:
    now = datetime(2024, 6, 1, tzinfo=UTC)

    rows = [
        {
            "id": uuid.uuid4(),
            "s3_key": "originals/t/u/1",
            "filename": "a.jpg",
            "taken_at": now,
            "score": 0.9,
        },
        {
            "id": uuid.uuid4(),
            "s3_key": "originals/t/u/2",
            "filename": "b.jpg",
            "taken_at": now,
            "score": 0.7,
        },
    ]
    mock_result = MagicMock()
    mock_result.mappings.return_value = rows
    override_db.execute = AsyncMock(return_value=mock_result)

    with (
        patch("app.routers.search.encode_text", return_value=[0.0] * 768),
        patch("app.routers.search.presign_photo_url", return_value="http://presigned/url"),
    ):
        response = await client.get(f"/search?q=beach&tenant_id={TENANT_ID}&user_id={USER_ID}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all("url" in item for item in data)
    assert data[0]["score"] >= data[1]["score"]


def _make_mock_db_with_rows(rows: list[dict]) -> AsyncMock:
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value = rows
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


def _search_query_params(mock_db: AsyncMock) -> dict:
    # execute is called twice: SET LOCAL then the main query. call_args is the last (main query).
    return mock_db.execute.call_args.args[1]


def _search_query_sql(mock_db: AsyncMock) -> str:
    return str(mock_db.execute.call_args.args[0])


def _base_url(extra: str = "") -> str:
    return f"/search?q=beach&tenant_id={TENANT_ID}&user_id={USER_ID}{extra}"


@pytest.mark.asyncio
async def test_search_includes_tenant_and_user_in_conditions(client: AsyncClient) -> None:
    mock_db = _make_mock_db_with_rows([])

    async def _override() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = _override
    try:
        with (
            patch("app.routers.search.encode_text", return_value=[0.0] * 768),
            patch("app.routers.search.presign_photo_url", return_value="http://x"),
        ):
            resp = await client.get(_base_url())
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    params = _search_query_params(mock_db)
    assert params["tid"] == str(TENANT_ID)
    assert params["uid"] == str(USER_ID)
    sql = _search_query_sql(mock_db)
    assert "pe.tenant_id = :tid" in sql
    assert "pe.user_id = :uid" in sql


@pytest.mark.asyncio
async def test_search_with_start_date_adds_filter(client: AsyncClient) -> None:
    mock_db = _make_mock_db_with_rows([])

    async def _override() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = _override
    try:
        with (
            patch("app.routers.search.encode_text", return_value=[0.0] * 768),
            patch("app.routers.search.presign_photo_url", return_value="http://x"),
        ):
            resp = await client.get(_base_url("&start_date=2024-06-01T00:00:00Z"))
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    params = _search_query_params(mock_db)
    assert "start_date" in params
    assert "p.taken_at >= :start_date" in _search_query_sql(mock_db)


@pytest.mark.asyncio
async def test_search_with_end_date_adds_filter(client: AsyncClient) -> None:
    mock_db = _make_mock_db_with_rows([])

    async def _override() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = _override
    try:
        with (
            patch("app.routers.search.encode_text", return_value=[0.0] * 768),
            patch("app.routers.search.presign_photo_url", return_value="http://x"),
        ):
            resp = await client.get(_base_url("&end_date=2024-08-31T00:00:00Z"))
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    params = _search_query_params(mock_db)
    assert "end_date" in params
    assert "p.taken_at <= :end_date" in _search_query_sql(mock_db)


@pytest.mark.asyncio
async def test_search_with_camera_make_adds_filter(client: AsyncClient) -> None:
    mock_db = _make_mock_db_with_rows([])

    async def _override() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = _override
    try:
        with (
            patch("app.routers.search.encode_text", return_value=[0.0] * 768),
            patch("app.routers.search.presign_photo_url", return_value="http://x"),
        ):
            resp = await client.get(_base_url("&camera_make=Canon"))
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    params = _search_query_params(mock_db)
    assert params["camera_make"] == "%Canon%"
    assert "ILIKE :camera_make" in _search_query_sql(mock_db)


@pytest.mark.asyncio
async def test_search_with_latitude_bounds_adds_filters(client: AsyncClient) -> None:
    mock_db = _make_mock_db_with_rows([])

    async def _override() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = _override
    try:
        with (
            patch("app.routers.search.encode_text", return_value=[0.0] * 768),
            patch("app.routers.search.presign_photo_url", return_value="http://x"),
        ):
            resp = await client.get(_base_url("&min_latitude=43.0&max_latitude=50.0"))
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    params = _search_query_params(mock_db)
    assert params["min_latitude"] == 43.0
    assert params["max_latitude"] == 50.0
    sql = _search_query_sql(mock_db)
    assert "p.latitude >= :min_latitude" in sql
    assert "p.latitude <= :max_latitude" in sql


@pytest.mark.asyncio
async def test_search_with_combined_date_and_camera_filters(client: AsyncClient) -> None:
    mock_db = _make_mock_db_with_rows([])

    async def _override() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = _override
    try:
        with (
            patch("app.routers.search.encode_text", return_value=[0.0] * 768),
            patch("app.routers.search.presign_photo_url", return_value="http://x"),
        ):
            resp = await client.get(
                _base_url(
                    "&start_date=2024-01-01T00:00:00Z"
                    "&end_date=2024-12-31T00:00:00Z"
                    "&camera_make=Sony"
                )
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    params = _search_query_params(mock_db)
    assert "start_date" in params
    assert "end_date" in params
    assert params["camera_make"] == "%Sony%"
    sql = _search_query_sql(mock_db)
    assert "p.taken_at >= :start_date" in sql
    assert "p.taken_at <= :end_date" in sql
    assert "ILIKE :camera_make" in sql


@pytest.mark.asyncio
async def test_search_no_filters_omits_extra_conditions(client: AsyncClient) -> None:
    mock_db = _make_mock_db_with_rows([])

    async def _override() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = _override
    try:
        with (
            patch("app.routers.search.encode_text", return_value=[0.0] * 768),
            patch("app.routers.search.presign_photo_url", return_value="http://x"),
        ):
            resp = await client.get(_base_url())
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    params = _search_query_params(mock_db)
    assert "start_date" not in params
    assert "end_date" not in params
    assert "camera_make" not in params
