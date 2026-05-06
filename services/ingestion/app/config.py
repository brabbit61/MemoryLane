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

    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket_photos: str = "memorylane-photos"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"  # noqa: S105
    aws_region: str = "us-east-1"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8001/oauth/google/callback"
    google_scopes: list[str] = [
        "https://www.googleapis.com/auth/photoslibrary.readonly",
        "openid",
        "email",
    ]

    oauth_state_ttl: int = 600

    model_config = {"env_prefix": "MEMORYLANE_"}


settings = Settings()
