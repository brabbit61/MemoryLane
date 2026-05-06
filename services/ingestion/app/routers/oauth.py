import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import OAuthToken, User
from app.services.google_photos import build_auth_url, exchange_code
from app.services.redis_state import consume_state_token, create_state_token

router = APIRouter(prefix="/oauth", tags=["oauth"])


@router.get("/google/init")
async def google_oauth_init(
    user_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    state_token = await create_state_token(request.app.state.redis)
    await request.app.state.redis.set(f"oauth_user:{state_token}", str(user_id), ex=600)
    auth_url = build_auth_url(f"{state_token}:{user_id}")
    return {"auth_url": auth_url}


@router.get("/google/callback")
async def google_oauth_callback(
    code: str,
    state: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    parts = state.split(":", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    state_token, user_id_str = parts[0], parts[1]

    valid = await consume_state_token(request.app.state.redis, state_token)
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid or expired state token")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid user_id in state") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    token_data = await exchange_code(code)

    token_expiry: datetime | None = None
    if token_data.get("token_expiry"):
        token_expiry = datetime.fromisoformat(str(token_data["token_expiry"]))
        if token_expiry.tzinfo is None:
            token_expiry = token_expiry.replace(tzinfo=timezone.utc)

    existing_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.user_id == user_id,
            OAuthToken.provider == "google",
        )
    )
    oauth_token = existing_result.scalar_one_or_none()

    if oauth_token is None:
        oauth_token = OAuthToken(
            tenant_id=user.tenant_id,
            user_id=user_id,
            provider="google",
            access_token=str(token_data["access_token"]),
            refresh_token=token_data.get("refresh_token"),
            token_expiry=token_expiry,
            scope=token_data.get("scope"),
        )
        db.add(oauth_token)
    else:
        await db.execute(
            update(OAuthToken)
            .where(OAuthToken.id == oauth_token.id)
            .values(
                access_token=str(token_data["access_token"]),
                refresh_token=token_data.get("refresh_token") or oauth_token.refresh_token,
                token_expiry=token_expiry,
                scope=token_data.get("scope"),
                updated_at=datetime.now(tz=timezone.utc),
            )
        )

    await db.commit()

    from app.routers.sync import run_google_sync

    background_tasks.add_task(run_google_sync, str(user_id))

    return {"status": "connected"}
