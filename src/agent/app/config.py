from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "MemoryLane Agent"
    version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"

    search_service_url: str = "http://search-svc:8002"
    http_timeout_seconds: float = 30.0

    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    langsmith_api_key: str = ""
    langsmith_project: str = "memorylane-agent"

    model_config = {"env_prefix": "MEMORYLANE_"}


settings = Settings()
