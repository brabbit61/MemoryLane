import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """Shape-compatible with services/search/app/models.py:SearchResult."""

    photo_id: uuid.UUID
    filename: str | None
    taken_at: datetime | None
    score: float
    url: str


class AgentSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    limit: int = 20


class AgentSearchResponse(BaseModel):
    results: list[SearchResult]
    reasoning: list[str]
