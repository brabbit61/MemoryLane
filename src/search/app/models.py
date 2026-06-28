import uuid
from datetime import datetime

from pydantic import BaseModel


class SearchResult(BaseModel):
    photo_id: uuid.UUID
    filename: str | None
    taken_at: datetime | None
    score: float
    url: str


class PhotoCount(BaseModel):
    count: int
