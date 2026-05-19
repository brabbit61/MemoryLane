import uuid

import pytest


@pytest.fixture()
def photo_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def tenant_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture()
def user_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000002")
