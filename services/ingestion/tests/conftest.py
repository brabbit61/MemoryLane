import uuid
from collections.abc import AsyncGenerator, Generator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db import get_db
from app.main import app


@pytest.fixture()
def mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.getdel = AsyncMock(return_value="1")
    redis.get = AsyncMock(return_value=None)
    redis.aclose = AsyncMock()
    return redis


@pytest.fixture()
def dev_user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture()
def dev_tenant_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture()
def override_db() -> Generator[AsyncMock, None, None]:
    """Override the get_db FastAPI dependency with a mock AsyncSession.

    Yields the AsyncMock so tests can configure its behavior.
    """
    mock_db = AsyncMock()

    async def _override() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = _override
    try:
        yield mock_db
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture()
async def client(mock_redis: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    app.state.redis = mock_redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
