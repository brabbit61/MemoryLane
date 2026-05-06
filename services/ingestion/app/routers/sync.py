import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_factory, get_db
from app.models import OAuthToken, Photo, User
from app.services.google_photos import get_media_item_bytes, list_media_items
from app.services.s3 import upload_photo
from app.tasks import dispatch_enrich_photo

router = APIRouter(prefix="/sync", tags=["sync"])


async def run_google_sync(user_id: str) -> None:
    """Runs the full Google Photos sync for a user. Called as a BackgroundTask."""
    async with async_session_factory() as db:
        await _sync_google_photos(db, uuid.UUID(user_id))


async def _sync_google_photos(db: AsyncSession, user_id: uuid.UUID) -> None:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return

    token_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user_id,
            OAuthToken.provider == "google",
        )
    )
    oauth_token = token_result.scalar_one_or_none()
    if oauth_token is None:
        return

    creds_dict: dict[str, str | None] = {
        "access_token": oauth_token.access_token,
        "refresh_token": oauth_token.refresh_token,
        "token_expiry": oauth_token.token_expiry.isoformat() if oauth_token.token_expiry else None,
        "scope": oauth_token.scope,
    }

    start_date = oauth_token.last_synced_at

    async for page in list_media_items(creds_dict, start_date=start_date):
        for item in page:
            external_id = str(item.get("id", ""))
            if not external_id:
                continue

            existing = await db.execute(
                select(Photo).where(
                    Photo.tenant_id == user.tenant_id,
                    Photo.user_id == user_id,
                    Photo.external_id == external_id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            base_url = str(item.get("baseUrl", ""))
            mime_type = str(item.get("mimeType", "image/jpeg"))
            filename = str(item.get("filename", ""))

            photo_bytes = await get_media_item_bytes(base_url)

            photo = Photo(
                tenant_id=user.tenant_id,
                user_id=user_id,
                s3_key="",
                filename=filename or None,
                mime_type=mime_type,
                file_size_bytes=len(photo_bytes),
                source="google_photos",
                external_id=external_id,
                status="pending",
            )
            db.add(photo)
            await db.flush()

            s3_key = await upload_photo(
                str(user.tenant_id),
                str(user_id),
                str(photo.id),
                photo_bytes,
                content_type=mime_type,
            )

            await db.execute(
                update(Photo).where(Photo.id == photo.id).values(s3_key=s3_key)
            )
            await db.commit()

            dispatch_enrich_photo(str(photo.id))

    await db.execute(
        update(OAuthToken)
        .where(OAuthToken.id == oauth_token.id)
        .values(last_synced_at=datetime.now(tz=timezone.utc))
    )
    await db.commit()


@router.post("/google/{user_id}")
async def sync_google_photos(
    user_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(User).where(User.id == user_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="User not found")

    background_tasks.add_task(run_google_sync, str(user_id))
    return {"status": "sync_started"}
