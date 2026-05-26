from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "MemoryLane Search"
    version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://memorylane:memorylane@localhost:5432/memorylane"

    s3_endpoint_url: str | None = None
    s3_bucket_photos: str = "memorylane-photos"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"  # noqa: S105
    aws_region: str = "us-east-1"

    clip_model_name: str = "ViT-L-14"
    clip_pretrained: str = "openai"
    # Text encoding (<50 ms on CPU per query) does not need a GPU. The GPU is
    # reserved for the celery-worker image-encoding path. Override via
    # MEMORYLANE_CLIP_DEVICE=cuda if a GPU node is available.
    clip_device: str = "cpu"

    model_config = {"env_prefix": "MEMORYLANE_"}


settings = Settings()
