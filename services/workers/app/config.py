from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://memorylane:memorylane@localhost:5432/memorylane"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_backend_url: str = "redis://localhost:6379/1"

    # None / empty => boto3 uses the real AWS S3 endpoint for aws_region.
    s3_endpoint_url: str | None = None
    s3_bucket_photos: str = "memorylane-photos"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"  # noqa: S105
    aws_region: str = "us-east-1"

    clip_model_name: str = "ViT-L-14"
    clip_pretrained: str = "openai"
    clip_device: str = "cuda"

    model_config = {"env_prefix": "MEMORYLANE_"}


settings = Settings()
