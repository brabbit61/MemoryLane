import pytest


@pytest.fixture(autouse=True)
def _env_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests use safe defaults regardless of environment."""
    monkeypatch.setenv("MEMORYLANE_ENVIRONMENT", "test")
    monkeypatch.setenv("MEMORYLANE_DEBUG", "true")
