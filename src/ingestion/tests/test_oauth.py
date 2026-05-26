import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio()
async def test_oauth_init_returns_auth_url(
    client: AsyncClient,
    mock_redis: AsyncMock,
    override_db: AsyncMock,
    dev_user_id: uuid.UUID,
) -> None:
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = object()  # user exists
    override_db.execute = AsyncMock(return_value=user_result)

    with patch("app.routers.oauth.create_state_token", return_value="test-token"):
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
    user_id = uuid.uuid4()
    # consume_state_token returns False (state not in Redis)
    with patch("app.routers.oauth.consume_state_token", return_value=False):
        response = await client.get(
            f"/oauth/google/callback?code=fake-code&state=bad-token:{user_id}"
        )

    assert response.status_code == 400


@pytest.mark.asyncio()
async def test_callback_success(
    client: AsyncClient,
    mock_redis: AsyncMock,
    override_db: AsyncMock,
    dev_user_id: uuid.UUID,
    dev_tenant_id: uuid.UUID,
) -> None:
    from app.models import User

    mock_user_obj = User(
        id=dev_user_id,
        tenant_id=dev_tenant_id,
        email="dev@memorylane.local",
    )
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = mock_user_obj
    no_token_result = MagicMock()
    no_token_result.scalar_one_or_none.return_value = None  # no existing oauth_token

    override_db.execute = AsyncMock(side_effect=[user_result, no_token_result])
    override_db.commit = AsyncMock()
    override_db.add = MagicMock()  # AsyncSession.add is synchronous

    fake_token_data = {
        "access_token": "acc-token",
        "refresh_token": "ref-token",
        "token_expiry": "2026-12-01T00:00:00+00:00",
        "scope": "https://www.googleapis.com/auth/photospicker.mediaitems.readonly",
    }

    with (
        patch("app.routers.oauth.consume_state_token", return_value=True),
        patch("app.routers.oauth.exchange_code", return_value=fake_token_data),
    ):
        response = await client.get(
            f"/oauth/google/callback?code=real-code&state=valid-token:{dev_user_id}"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "connected"
    # Callback no longer auto-triggers sync — user must call /sync/.../start manually
    assert "next_step" in body
