import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clip_text import encode_text
from app.db import get_db
from app.models import SearchResult
from app.services.s3 import presign_photo_url

router = APIRouter(tags=["search"])
DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("/search", response_model=list[SearchResult])
async def search(
    q: str,
    user_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: DbSession = ...,
) -> list[SearchResult]:
    embedding = encode_text(q)
    vec_str = "[" + ",".join(map(str, embedding)) + "]"

    rows = await db.execute(
        text("""
            SELECT p.id, p.s3_key, p.filename, p.taken_at,
                   1 - (pe.embedding <=> CAST(:vec AS vector)) AS score
            FROM photo_embeddings pe
            JOIN photos p ON p.id = pe.photo_id
            WHERE pe.user_id = :uid
            ORDER BY pe.embedding <=> CAST(:vec AS vector)
            LIMIT :lim
        """),
        {"vec": vec_str, "uid": str(user_id), "lim": limit},
    )

    results = []
    for row in rows.mappings():
        results.append(
            SearchResult(
                photo_id=row["id"],
                filename=row["filename"],
                taken_at=row["taken_at"],
                score=float(row["score"]),
                url=presign_photo_url(row["s3_key"]),
            )
        )
    return results
