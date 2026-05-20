import io
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.models import Photo, PhotoEmbedding
from app.tasks import _enrich


def _make_minimal_jpeg() -> bytes:
    img = Image.new("RGB", (10, 10), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_photo(
    photo_id: str,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    **overrides: object,
) -> Photo:
    kwargs: dict[str, object] = {
        "id": uuid.UUID(photo_id),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "s3_key": f"originals/{tenant_id}/{user_id}/{photo_id}",
        "status": "pending",
        "source": "google_photos",
        "taken_at": None,
    }
    kwargs.update(overrides)
    return Photo(**kwargs)


@pytest.fixture()
def fake_photo(photo_id: str, tenant_id: uuid.UUID, user_id: uuid.UUID) -> Photo:
    return _make_photo(photo_id, tenant_id, user_id)


def _run_enrich_and_capture_update(
    photo: Photo,
    photo_id: str,
    exif: dict[str, object],
) -> dict[str, object]:
    """Drive _enrich() with the given photo + mocked EXIF and return the values
    dict passed to the UPDATE photos statement."""
    jpeg_bytes = _make_minimal_jpeg()
    fake_embedding = [0.0] * 768

    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=jpeg_bytes))}
    mock_s3.put_object.return_value = {}

    mock_db = MagicMock()
    mock_db.get.return_value = photo
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

    with (
        patch("app.tasks.get_db_session", return_value=mock_db),
        patch("app.tasks._s3_client", return_value=mock_s3),
        patch("app.tasks.encode_image", return_value=fake_embedding),
        patch("app.tasks._extract_exif", return_value=exif),
    ):
        _enrich(photo_id)

    # Inspect the UPDATE statement issued against the photos table. SQLAlchemy
    # core UPDATEs carry the `values` payload in `_values`.
    update_stmt = mock_db.execute.call_args.args[0]
    return {
        (k.name if hasattr(k, "name") else str(k)): v.value for k, v in update_stmt._values.items()
    }


def test_enrich_creates_embedding_and_marks_enriched(
    photo_id: str,
    fake_photo: Photo,
) -> None:
    jpeg_bytes = _make_minimal_jpeg()
    fake_embedding = [0.0] * 768

    mock_s3_resp = {"Body": MagicMock(read=MagicMock(return_value=jpeg_bytes))}
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = mock_s3_resp
    mock_s3.put_object.return_value = {}

    mock_db = MagicMock()
    mock_db.get.return_value = fake_photo
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

    added_objects: list[object] = []
    mock_db.add.side_effect = added_objects.append

    with (
        patch("app.tasks.get_db_session", return_value=mock_db),
        patch("app.tasks._s3_client", return_value=mock_s3),
        patch("app.tasks.encode_image", return_value=fake_embedding),
    ):
        _enrich(photo_id)

    embedding_added = next((obj for obj in added_objects if isinstance(obj, PhotoEmbedding)), None)
    assert embedding_added is not None, "PhotoEmbedding was not added to the session"
    assert len(embedding_added.embedding) == 768

    update_call_args = mock_db.execute.call_args
    assert update_call_args is not None

    mock_db.commit.assert_called_once()


def test_enrich_does_not_overwrite_ingest_set_taken_at(
    photo_id: str,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """When Picker createTime already set taken_at, EXIF DateTimeOriginal must
    not clobber it."""
    ingest_taken_at = datetime(2024, 8, 15, 19, 23, 45, tzinfo=UTC)
    photo = _make_photo(photo_id, tenant_id, user_id, taken_at=ingest_taken_at)
    exif_with_different_date = {"taken_at": "2020-01-01T00:00:00+00:00", "width": 10, "height": 10}

    values = _run_enrich_and_capture_update(photo, photo_id, exif_with_different_date)

    assert "taken_at" not in values, f"Worker overwrote ingest-set taken_at; values={values}"


def test_enrich_fills_taken_at_when_null(
    photo_id: str,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """If ingestion couldn't get createTime (rare), the worker uses EXIF."""
    photo = _make_photo(photo_id, tenant_id, user_id, taken_at=None)
    exif = {"taken_at": "2023-04-01T12:00:00+00:00", "width": 10, "height": 10}

    values = _run_enrich_and_capture_update(photo, photo_id, exif)

    assert values.get("taken_at") == datetime.fromisoformat("2023-04-01T12:00:00+00:00")
