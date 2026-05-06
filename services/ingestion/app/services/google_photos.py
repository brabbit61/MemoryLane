import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.config import settings


def _build_flow() -> Flow:
    config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uris": [settings.google_redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(
        config,
        scopes=settings.google_scopes,
        redirect_uri=settings.google_redirect_uri,
    )


def build_auth_url(state: str) -> str:
    flow = _build_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        include_granted_scopes="true",
    )
    return str(auth_url)


def _exchange_code_sync(code: str) -> dict[str, str | None]:
    flow = _build_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    expiry_str = creds.expiry.isoformat() if creds.expiry else None
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_expiry": expiry_str,
        "scope": " ".join(creds.scopes) if creds.scopes else None,
    }


async def exchange_code(code: str) -> dict[str, str | None]:
    return await asyncio.to_thread(_exchange_code_sync, code)


def _build_credentials(creds_dict: dict[str, str | None]) -> Credentials:
    expiry: datetime | None = None
    if creds_dict.get("token_expiry"):
        expiry = datetime.fromisoformat(str(creds_dict["token_expiry"]))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)

    scopes = None
    if creds_dict.get("scope"):
        scopes = str(creds_dict["scope"]).split()

    return Credentials(  # type: ignore[no-untyped-call]
        token=creds_dict.get("access_token"),
        refresh_token=creds_dict.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",  # noqa: S106
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=scopes,
        expiry=expiry,
    )


async def list_media_items(
    creds_dict: dict[str, str | None],
    start_date: datetime | None = None,
) -> AsyncGenerator[list[dict[str, object]], None]:
    """Async generator that yields pages of mediaItem dicts."""

    def _fetch_page(page_token: str | None) -> tuple[list[dict[str, object]], str | None]:
        creds = _build_credentials(creds_dict)
        service = build("photoslibrary", "v1", credentials=creds, static_discovery=False)

        body: dict[str, object] = {"pageSize": 100}
        if start_date:
            body["filters"] = {
                "dateFilter": {
                    "ranges": [
                        {
                            "startDate": {
                                "year": start_date.year,
                                "month": start_date.month,
                                "day": start_date.day,
                            },
                            "endDate": {"year": 9999, "month": 12, "day": 31},
                        }
                    ]
                }
            }
        if page_token:
            body["pageToken"] = page_token

        resp = service.mediaItems().search(body=body).execute()
        items: list[dict[str, object]] = resp.get("mediaItems", [])
        next_token: str | None = resp.get("nextPageToken")
        return items, next_token

    page_token: str | None = None
    while True:
        items, next_token = await asyncio.to_thread(_fetch_page, page_token)
        if items:
            yield items
        if not next_token:
            break
        page_token = next_token


async def get_media_item_bytes(base_url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(f"{base_url}=d")
        resp.raise_for_status()
        return resp.content
