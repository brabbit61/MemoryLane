import boto3
from botocore.client import Config

from app.config import settings

# Buckets with SSE-KMS reject SigV2 presigned URLs ("require AWS Signature
# Version 4"). Force SigV4 so GETs against KMS-encrypted objects authenticate.
_client = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint_url or None,
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region_name=settings.aws_region,
    config=Config(signature_version="s3v4"),
)


def presign_photo_url(s3_key: str, expires_in: int = 3600) -> str:
    return _client.generate_presigned_url(  # type: ignore[no-any-return]
        "get_object",
        Params={"Bucket": settings.s3_bucket_photos, "Key": s3_key},
        ExpiresIn=expires_in,
    )
