import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.models import Photo, PhotoEmbedding
from app.tasks import _enrich
from tests.conftest import make_minimal_jpeg


@pytest.fixture()
def fake_photo(photo_id: str, tenant_id: uuid.UUID, user_id: uuid.UUID) -> Photo:
    return Photo(
        id=uuid.UUID(photo_id),
        tenant_id=tenant_id,
        user_id=user_id,
        s3_key=f"originals/{tenant_id}/{user_id}/{photo_id}",
        status="pending",
        source="google_photos",
    )


def test_enrich_creates_embedding_and_marks_enriched(
    photo_id: str,
    fake_photo: Photo,
) -> None:
    jpeg_bytes = make_minimal_jpeg()
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

    embedding_added = next(
        (obj for obj in added_objects if isinstance(obj, PhotoEmbedding)), None
    )
    assert embedding_added is not None, "PhotoEmbedding was not added to the session"
    assert len(embedding_added.embedding) == 768

    update_call_args = mock_db.execute.call_args
    assert update_call_args is not None

    mock_db.commit.assert_called_once()
