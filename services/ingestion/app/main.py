from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import oauth, sync
from app.services.s3 import ensure_bucket_exists


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)  # type: ignore[no-untyped-call]
    app.state.redis = redis_client
    await ensure_bucket_exists()
    yield
    await redis_client.aclose()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(oauth.router)
app.include_router(sync.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "version": settings.version, "status": "running"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/ready")
async def readiness() -> dict[str, str]:
    return {"status": "ready"}
