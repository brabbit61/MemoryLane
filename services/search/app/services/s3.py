import boto3

from app.config import settings


def presign_photo_url(s3_key: str, expires_in: int = 3600) -> str:
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket_photos, "Key": s3_key},
        ExpiresIn=expires_in,
    )
