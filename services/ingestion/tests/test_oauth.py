import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio()
async def test_oauth_init_returns_auth_url(
    client: AsyncClient,
    mock_redis: AsyncMock,
    dev_user_id: uuid.UUID,
) -> None:
    mock_user = AsyncMock()
    mock_user.scalar_one_or_none.return_value = object()

    with (
        patch("app.routers.oauth.get_db") as mock_get_db,
        patch("app.services.redis_state.create_state_token", return_value="test-token"),
    ):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_user)
        mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

        response = await client.get(f"/oauth/google/init?user_id={dev_user_id}")

    assert response.status_code == 200
    data = response.json()
    assert "auth_url" in data
    assert "accounts.google.com" in data["auth_url"]
    mock_redis.set.assert_called()


@pytest.mark.asyncio()
async def test_callback_invalid_state(
    client: AsyncClient,
    mock_redis: AsyncMock,
) -> None:
    mock_redis.getdel = AsyncMock(return_value=None)

    user_id = uuid.uuid4()
    with patch("app.services.redis_state.consume_state_token", return_value=False):
        response = await client.get(
            f"/oauth/google/callback?code=fake-code&state=bad-token:{user_id}"
        )

    assert response.status_code == 400


@pytest.mark.asyncio()
async def test_callback_success(
    client: AsyncClient,
    mock_redis: AsyncMock,
    dev_user_id: uuid.UUID,
    dev_tenant_id: uuid.UUID,
) -> None:
    from app.models import User

    mock_user_obj = User(
        id=dev_user_id,
        tenant_id=dev_tenant_id,
        email="dev@memorylane.local",
    )
    mock_execute_result = AsyncMock()
    mock_execute_result.scalar_one_or_none.side_effect = [mock_user_obj, None]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_execute_result)
    mock_db.commit = AsyncMock()
    mock_db.add = AsyncMock()

    fake_token_data = {
        "access_token": "acc-token",
        "refresh_token": "ref-token",
        "token_expiry": "2026-12-01T00:00:00+00:00",
        "scope": "https://www.googleapis.com/auth/photoslibrary.readonly",
    }

    with (
        patch("app.routers.oauth.consume_state_token", return_value=True),
        patch("app.routers.oauth.exchange_code", return_value=fake_token_data),
        patch("app.routers.oauth.get_db") as mock_get_db,
        patch("app.routers.sync.run_google_sync") as mock_sync,
    ):
        mock_get_db.return_value = _AsyncCtx(mock_db)
        response = await client.get(
            f"/oauth/google/callback?code=real-code&state=valid-token:{dev_user_id}"
        )

    assert response.status_code == 200
    assert response.json() == {"status": "connected"}
    mock_sync.assert_called_once()


class _AsyncCtx:
    """Minimal async context manager shim for patching get_db."""

    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, *args: object) -> None:
        pass
