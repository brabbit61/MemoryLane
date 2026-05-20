from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "MemoryLane Ingestion Service"
    version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://memorylane:memorylane@localhost:5432/memorylane"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_backend_url: str = "redis://localhost:6379/1"

    # None / empty => boto3 uses the real AWS S3 endpoint for aws_region.
    # Set to http://minio:9000 (compose) or http://localhost:9000 (host) for MinIO.
    s3_endpoint_url: str | None = None
    s3_bucket_photos: str = "memorylane-photos"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"  # noqa: S105
    aws_region: str = "us-east-1"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8001/oauth/google/callback"
    # Photos Library API was deprecated for library-wide reads on 2025-03-31.
    # The Picker API replaces it: user explicitly selects photos via a Google-hosted UI.
    google_scopes: list[str] = [
        "https://www.googleapis.com/auth/photospicker.mediaitems.readonly",
        "openid",
        "email",
    ]

    oauth_state_ttl: int = 600

    model_config = {"env_prefix": "MEMORYLANE_"}


settings = Settings()
