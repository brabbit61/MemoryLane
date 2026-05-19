import secrets

import redis.asyncio as aioredis

from app.config import settings

_KEY_PREFIX = "oauth_state:"


def _key(token: str) -> str:
    return f"{_KEY_PREFIX}{token}"


async def create_state_token(redis: aioredis.Redis) -> str:  # type: ignore[type-arg]
    token = secrets.token_urlsafe(32)
    await redis.set(_key(token), "1", ex=settings.oauth_state_ttl)
    return token


async def consume_state_token(redis: aioredis.Redis, token: str) -> bool:  # type: ignore[type-arg]
    """Atomically get-and-delete the state token. Returns True if it existed."""
    result = await redis.getdel(_key(token))
    return result is not None
