import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.db import get_db
from app.main import app


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
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
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
        response = await client.get(f"/search?q=beach&user_id={user_id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all("url" in item for item in data)
    assert data[0]["score"] >= data[1]["score"]
