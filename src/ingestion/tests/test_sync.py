import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.sync import _ingest_picked_items


def _scalar(value: object) -> MagicMock:
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    return m


@pytest.mark.asyncio()
async def test_picker_ingest_dispatches_enrich_per_new_photo() -> None:
    tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    session_id = "picker-session-xyz"

    from app.models import OAuthToken, Photo, User

    mock_user = User(id=user_id, tenant_id=tenant_id, email="dev@memorylane.local")
    mock_token = OAuthToken(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        provider="google",
        access_token="acc-token",  # noqa: S106
        refresh_token="ref-token",  # noqa: S106
        last_synced_at=None,
    )

    # Picker API mediaItem shape (note: nested mediaFile + mediaFileMetadata)
    media_item = {
        "id": "picker-photo-1",
        "createTime": "2026-05-01T00:00:00Z",
        "type": "PHOTO",
        "mediaFile": {
            "baseUrl": "https://lh3.googleusercontent.com/fake",
            "mimeType": "image/jpeg",
            "filename": "photo1.jpg",
            "mediaFileMetadata": {
                "width": 4032,
                "height": 3024,
                "cameraMake": "Apple",
                "cameraModel": "iPhone 14",
                "photoMetadata": {
                    "focalLength": 4.25,
                    "apertureFNumber": 1.78,
                    "isoEquivalent": 100,
                    "exposureTime": "0.04s",
                },
            },
        },
    }

    created_photo = Photo(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        s3_key="",
        external_id="picker-photo-1",
        status="pending",
        source="google_photos",
    )

    # _load_user_and_token: user select, token select
    # then dedup check (None = not present), then last_synced_at update
    execute_results = [
        _scalar(mock_user),  # _load_user_and_token: user
        _scalar(mock_token),  # _load_user_and_token: token
        _scalar(None),  # dedup check
        MagicMock(),  # UPDATE photos.s3_key
        MagicMock(),  # UPDATE oauth_tokens.last_synced_at
    ]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=execute_results)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()  # AsyncSession.add is synchronous

    added_photos: list[Photo] = []

    def _fake_add(obj: object) -> None:
        if isinstance(obj, Photo):
            obj.id = created_photo.id  # type: ignore[attr-defined]
            added_photos.append(obj)

    mock_db.add.side_effect = _fake_add

    async def _picked_items_gen(
        *args: Any, **kwargs: Any
    ) -> AsyncGenerator[list[dict[str, object]], None]:
        yield [media_item]

    with (
        patch("app.routers.sync.list_picked_items", side_effect=_picked_items_gen),
        patch("app.routers.sync.get_media_item_bytes", return_value=b"fake-bytes"),
        patch("app.routers.sync.upload_photo", return_value="originals/t/u/p"),
        patch("app.routers.sync.delete_picker_session"),
    ):
        await _ingest_picked_items(mock_db, user_id, session_id)

    # Verify Picker metadata was persisted on the inserted Photo row.
    assert len(added_photos) == 1
    saved = added_photos[0]
    assert saved.filename == "photo1.jpg"
    assert saved.mime_type == "image/jpeg"
    assert saved.width == 4032
    assert saved.height == 3024
    assert saved.taken_at is not None
    assert saved.taken_at.year == 2026
    assert saved.exif_data == {
        "source": "picker_api",
        "camera_make": "Apple",
        "camera_model": "iPhone 14",
        "focal_length": 4.25,
        "aperture_f_number": 1.78,
        "iso_equivalent": 100,
        "exposure_time": "0.04s",
    }


@pytest.mark.asyncio()
async def test_picker_ingest_skips_video_items() -> None:
    """type=VIDEO items are filtered out before any S3 / DB / enrich work."""
    tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    session_id = "picker-session-xyz"

    from app.models import OAuthToken, User

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

    video_item = {
        "id": "video-1",
        "type": "VIDEO",
        "mediaFile": {
            "baseUrl": "https://lh3.googleusercontent.com/v",
            "mimeType": "video/mp4",
            "filename": "clip.mp4",
        },
    }

    execute_results = [
        _scalar(mock_user),
        _scalar(mock_token),
        MagicMock(),  # last_synced_at update
    ]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=execute_results)
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    async def _picked_items_gen(
        *args: Any, **kwargs: Any
    ) -> AsyncGenerator[list[dict[str, object]], None]:
        yield [video_item]

    with (
        patch("app.routers.sync.list_picked_items", side_effect=_picked_items_gen),
        patch("app.routers.sync.get_media_item_bytes") as mock_download,
        patch("app.routers.sync.delete_picker_session"),
    ):
        await _ingest_picked_items(mock_db, user_id, session_id)

    mock_download.assert_not_called()
    mock_db.add.assert_not_called()


@pytest.mark.asyncio()
async def test_picker_ingest_skips_items_without_base_url() -> None:
    """A picked item with no mediaFile.baseUrl is skipped, not crashed on."""
    tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    session_id = "picker-session-xyz"

    from app.models import OAuthToken, User

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

    # Item missing mediaFile entirely. parse_picked_item returns None and the
    # loop short-circuits before any dedup query.
    bad_item = {"id": "broken-1", "type": "PHOTO"}

    execute_results = [
        _scalar(mock_user),
        _scalar(mock_token),
        MagicMock(),  # last_synced_at update
    ]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=execute_results)
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    async def _picked_items_gen(
        *args: Any, **kwargs: Any
    ) -> AsyncGenerator[list[dict[str, object]], None]:
        yield [bad_item]

    with (
        patch("app.routers.sync.list_picked_items", side_effect=_picked_items_gen),
        patch("app.routers.sync.get_media_item_bytes") as mock_download,
        patch("app.routers.sync.delete_picker_session"),
    ):
        await _ingest_picked_items(mock_db, user_id, session_id)

    mock_download.assert_not_called()
