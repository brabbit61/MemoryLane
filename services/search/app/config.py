from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "MemoryLane Search"
    version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://memorylane:memorylane@localhost:5432/memorylane"

    model_config = {"env_prefix": "MEMORYLANE_"}


settings = Settings()
