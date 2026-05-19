import io
import uuid

import pytest
from PIL import Image


@pytest.fixture()
def photo_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def tenant_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture()
def user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000002")


def make_minimal_jpeg() -> bytes:
    """Create a 10x10 red JPEG in memory."""
    img = Image.new("RGB", (10, 10), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()
