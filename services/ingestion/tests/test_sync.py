import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.sync import _sync_google_photos


async def _fake_media_gen(
    items: list[dict],
) -> AsyncGenerator[list[dict], None]:
    yield items


@pytest.mark.asyncio()
async def test_sync_dispatches_enrich_per_new_photo() -> None:
    tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")

    from app.models import OAuthToken, Photo, User

    mock_user = User(id=user_id, tenant_id=tenant_id, email="dev@memorylane.local")
    mock_token = OAuthToken(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        provider="google",
        access_token="acc",  # noqa: S106
        refresh_token="ref",  # noqa: S106
        last_synced_at=None,
    )

    media_item = {
        "id": "google-photo-1",
        "baseUrl": "https://photos.google.com/fake",
        "mimeType": "image/jpeg",
        "filename": "photo1.jpg",
    }

    created_photo = Photo(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        s3_key="",
        external_id="google-photo-1",
        status="pending",
        source="google_photos",
    )

    execute_results = [
        _scalar(mock_user),
        _scalar(mock_token),
        _scalar(None),
        MagicMock(),
        MagicMock(),
    ]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=execute_results)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.add = AsyncMock()

    async def _fake_add(obj: object) -> None:
        if isinstance(obj, Photo):
            obj.id = created_photo.id  # type: ignore[attr-defined]

    mock_db.add.side_effect = _fake_add

    async def _media_gen(*args, **kwargs):  # type: ignore[no-untyped-def]
        yield [media_item]

    with (
        patch("app.routers.sync.list_media_items", side_effect=_media_gen),
        patch("app.routers.sync.get_media_item_bytes", return_value=b"fake-bytes"),
        patch("app.routers.sync.upload_photo", return_value="originals/t/u/p"),
        patch("app.routers.sync.dispatch_enrich_photo") as mock_dispatch,
    ):
        await _sync_google_photos(mock_db, user_id)

    mock_dispatch.assert_called_once_with(str(created_photo.id))


def _scalar(value: object) -> MagicMock:
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    return m
