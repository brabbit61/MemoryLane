import contextlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from celery import Celery
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session_factory, get_db
from app.models import OAuthToken, Photo, User
from app.services.google_photos import (
    create_picker_session,
    delete_picker_session,
    get_media_item_bytes,
    get_picker_session,
    list_picked_items,
    parse_picked_item,
)
from app.services.s3 import upload_photo

_celery = Celery(
    "ingestion", broker=settings.celery_broker_url, backend=settings.celery_backend_url
)

logger = logging.getLogger(__name__)

DbSession = Annotated[AsyncSession, Depends(get_db)]

router = APIRouter(prefix="/sync", tags=["sync"])


def _creds_dict(oauth_token: OAuthToken) -> dict[str, str | None]:
    return {
        "access_token": oauth_token.access_token,
        "refresh_token": oauth_token.refresh_token,
        "token_expiry": (
            oauth_token.token_expiry.isoformat() if oauth_token.token_expiry else None
        ),
        "scope": oauth_token.scope,
    }


async def _load_user_and_token(db: AsyncSession, user_id: uuid.UUID) -> tuple[User, OAuthToken]:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    token = (
        await db.execute(
            select(OAuthToken).where(
                OAuthToken.user_id == user_id,
                OAuthToken.provider == "google",
            )
        )
    ).scalar_one_or_none()
    if token is None:
        raise HTTPException(
            status_code=400,
            detail="No Google OAuth token for this user — complete /oauth/google/init first",
        )
    return user, token


@router.post("/google/{user_id}/start")
async def start_picker_session(user_id: uuid.UUID, db: DbSession) -> dict[str, object]:
    _, oauth_token = await _load_user_and_token(db, user_id)
    session = await create_picker_session(_creds_dict(oauth_token))
    return {
        "session_id": session["id"],
        "picker_uri": session["pickerUri"],
        "expire_time": session.get("expireTime"),
        "polling_config": session.get("pollingConfig"),
        "next_step": (
            f"Open picker_uri in a browser, pick photos, then POST "
            f"/sync/google/{user_id}/ingest/{session['id']}"
        ),
    }


@router.get("/google/{user_id}/session/{session_id}")
async def check_picker_session(
    user_id: uuid.UUID,
    session_id: str,
    db: DbSession,
) -> dict[str, object]:
    _, oauth_token = await _load_user_and_token(db, user_id)
    session = await get_picker_session(_creds_dict(oauth_token), session_id)
    return {
        "session_id": session["id"],
        "media_items_set": session.get("mediaItemsSet", False),
        "expire_time": session.get("expireTime"),
    }


@router.post("/google/{user_id}/ingest/{session_id}")
async def ingest_picked_items(
    user_id: uuid.UUID,
    session_id: str,
    background_tasks: BackgroundTasks,
    db: DbSession,
) -> dict[str, str]:
    # Validate the user and token exist now; the background task re-opens its own session.
    await _load_user_and_token(db, user_id)
    background_tasks.add_task(run_picker_ingest, str(user_id), session_id)
    return {"status": "ingest_started"}


async def run_picker_ingest(user_id: str, session_id: str) -> None:
    """Background task: pull picked items from the Picker session and enqueue enrichment."""
    async with async_session_factory() as db:
        await _ingest_picked_items(db, uuid.UUID(user_id), session_id)


async def _ingest_picked_items(db: AsyncSession, user_id: uuid.UUID, session_id: str) -> None:
    user, oauth_token = await _load_user_and_token(db, user_id)
    creds_dict = _creds_dict(oauth_token)

    async for page in list_picked_items(creds_dict, session_id):
        for item in page:
            parsed = parse_picked_item(item)
            if parsed is None:
                continue

            if parsed.item_type != "PHOTO":
                logger.info(
                    "Skipping non-photo picked item: id=%s type=%s",
                    parsed.external_id,
                    parsed.item_type,
                )
                continue

            existing = await db.execute(
                select(Photo).where(
                    Photo.tenant_id == user.tenant_id,
                    Photo.user_id == user_id,
                    Photo.external_id == parsed.external_id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            photo_bytes = await get_media_item_bytes(parsed.base_url, creds_dict)

            photo = Photo(
                tenant_id=user.tenant_id,
                user_id=user_id,
                s3_key="",
                filename=parsed.filename,
                mime_type=parsed.mime_type,
                file_size_bytes=len(photo_bytes),
                width=parsed.width,
                height=parsed.height,
                taken_at=parsed.taken_at,
                exif_data=parsed.exif_data or None,
                source="google_photos",
                external_id=parsed.external_id,
                status="pending",
            )
            db.add(photo)
            await db.flush()

            s3_key = await upload_photo(
                str(user.tenant_id),
                str(user_id),
                str(photo.id),
                photo_bytes,
                content_type=parsed.mime_type,
            )

            await db.execute(update(Photo).where(Photo.id == photo.id).values(s3_key=s3_key))
            await db.commit()

            _celery.send_task(
                "workers.tasks.enrich_photo", args=[str(photo.id)], queue="enrichment"
            )

    await db.execute(
        update(OAuthToken)
        .where(OAuthToken.id == oauth_token.id)
        .values(last_synced_at=datetime.now(tz=UTC))
    )
    await db.commit()

    # Best-effort cleanup; ignore errors if session already expired.
    with contextlib.suppress(Exception):
        await delete_picker_session(creds_dict, session_id)
