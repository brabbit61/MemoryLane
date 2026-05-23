import uuid
from datetime import datetime
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
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    camera_make: str | None = None,
    min_latitude: float | None = None,
    max_latitude: float | None = None,
    min_longitude: float | None = None,
    max_longitude: float | None = None,
    db: DbSession = ...,
) -> list[SearchResult]:
    # Scope the DB session to this tenant so RLS policies enforce isolation.
    await db.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": str(tenant_id)})

    embedding = encode_text(q)
    vec_str = "[" + ",".join(map(str, embedding)) + "]"

    conditions: list[str] = ["pe.tenant_id = :tid", "pe.user_id = :uid"]
    params: dict[str, object] = {
        "vec": vec_str,
        "tid": str(tenant_id),
        "uid": str(user_id),
        "lim": limit,
    }

    if start_date is not None:
        conditions.append("p.taken_at >= :start_date")
        params["start_date"] = start_date
    if end_date is not None:
        conditions.append("p.taken_at <= :end_date")
        params["end_date"] = end_date
    if camera_make is not None:
        conditions.append("p.exif_data->>'make' ILIKE :camera_make")
        params["camera_make"] = f"%{camera_make}%"
    if min_latitude is not None:
        conditions.append("p.latitude >= :min_latitude")
        params["min_latitude"] = min_latitude
    if max_latitude is not None:
        conditions.append("p.latitude <= :max_latitude")
        params["max_latitude"] = max_latitude
    if min_longitude is not None:
        conditions.append("p.longitude >= :min_longitude")
        params["min_longitude"] = min_longitude
    if max_longitude is not None:
        conditions.append("p.longitude <= :max_longitude")
        params["max_longitude"] = max_longitude

    where_clause = " AND ".join(conditions)

    # where_clause is built from hardcoded condition strings; user values are all parameterized.
    query = (
        "SELECT p.id, p.s3_key, p.filename, p.taken_at,"  # noqa: S608
        " 1 - (pe.embedding <=> CAST(:vec AS vector)) AS score"
        " FROM photo_embeddings pe"
        " JOIN photos p ON p.id = pe.photo_id"
        f"WHERE {where_clause}"
        " ORDER BY pe.embedding <=> CAST(:vec AS vector)"
        " LIMIT :lim"
    )
    rows = await db.execute(text(query), params)

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
