from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "MemoryLane API Gateway"
    version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://memorylane:memorylane@localhost:5432/memorylane"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # S3 / MinIO
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket_photos: str = "memorylane-photos"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"  # noqa: S105

    model_config = {"env_prefix": "MEMORYLANE_"}


settings = Settings()
