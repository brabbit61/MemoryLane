from typing import Any

import aioboto3

from app.config import settings

_session = aioboto3.Session(
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
)


def _client() -> Any:
    return _session.client("s3", endpoint_url=settings.s3_endpoint_url)


async def ensure_bucket_exists() -> None:
    async with _client() as s3:
        try:
            await s3.head_bucket(Bucket=settings.s3_bucket_photos)
        except Exception:
            await s3.create_bucket(Bucket=settings.s3_bucket_photos)


def photo_s3_key(tenant_id: str, user_id: str, photo_id: str) -> str:
    return f"originals/{tenant_id}/{user_id}/{photo_id}"


async def upload_photo(
    tenant_id: str,
    user_id: str,
    photo_id: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    key = photo_s3_key(tenant_id, user_id, photo_id)
    async with _client() as s3:
        await s3.put_object(
            Bucket=settings.s3_bucket_photos,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    return key
