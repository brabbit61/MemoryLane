import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import google.auth.transport.requests
import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.config import settings

PICKER_API_BASE = "https://photospicker.googleapis.com/v1"


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


def build_auth_url(state: str) -> tuple[str, str]:
    """Return (auth_url, code_verifier). The verifier MUST be persisted and passed
    to exchange_code() during the callback — Google's PKCE requires the same
    verifier on both ends."""
    flow = _build_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        include_granted_scopes="true",
    )
    return auth_url, flow.code_verifier


def _exchange_code_sync(code: str, code_verifier: str | None) -> dict[str, str | None]:
    flow = _build_flow()
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials
    expiry_str = creds.expiry.isoformat() if creds.expiry else None
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_expiry": expiry_str,
        "scope": " ".join(creds.scopes) if creds.scopes else None,
    }


async def exchange_code(code: str, code_verifier: str | None = None) -> dict[str, str | None]:
    return await asyncio.to_thread(_exchange_code_sync, code, code_verifier)


def _build_credentials(creds_dict: dict[str, str | None]) -> Credentials:
    expiry: datetime | None = None
    if creds_dict.get("token_expiry"):
        parsed = datetime.fromisoformat(str(creds_dict["token_expiry"]))
        # google-auth's internal `_helpers.utcnow()` returns NAIVE UTC, so the
        # expiry passed into Credentials must also be naive UTC — otherwise the
        # `expired` property raises TypeError on aware/naive comparison.
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC).replace(tzinfo=None)
        expiry = parsed

    scopes = None
    if creds_dict.get("scope"):
        scopes = str(creds_dict["scope"]).split()

    return Credentials(
        token=creds_dict.get("access_token"),
        refresh_token=creds_dict.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=scopes,
        expiry=expiry,
    )


def _refreshed_access_token(creds_dict: dict[str, str | None]) -> str:
    """Build Credentials, refresh if expired/expiring, and return the current access token."""
    creds = _build_credentials(creds_dict)
    if not creds.valid:
        creds.refresh(google.auth.transport.requests.Request())
    return str(creds.token)


async def _picker_access_token(creds_dict: dict[str, str | None]) -> str:
    return await asyncio.to_thread(_refreshed_access_token, creds_dict)


async def create_picker_session(creds_dict: dict[str, str | None]) -> dict[str, object]:
    """Create a Picker session. Returns dict with `id`, `pickerUri`, `mediaItemsSet`, etc."""
    token = await _picker_access_token(creds_dict)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{PICKER_API_BASE}/sessions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={},
        )
        resp.raise_for_status()
        data: dict[str, object] = resp.json()
        return data


async def get_picker_session(
    creds_dict: dict[str, str | None],
    session_id: str,
) -> dict[str, object]:
    """Poll a Picker session — check `mediaItemsSet` to know when the user is done."""
    token = await _picker_access_token(creds_dict)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{PICKER_API_BASE}/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        data: dict[str, object] = resp.json()
        return data


async def list_picked_items(
    creds_dict: dict[str, str | None],
    session_id: str,
) -> AsyncGenerator[list[dict[str, object]], None]:
    """Paginate through media items the user picked in this Picker session."""
    token = await _picker_access_token(creds_dict)
    page_token: str | None = None
    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            params: dict[str, str] = {"sessionId": session_id, "pageSize": "100"}
            if page_token:
                params["pageToken"] = page_token
            resp = await client.get(
                f"{PICKER_API_BASE}/mediaItems",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            resp.raise_for_status()
            data: dict[str, object] = resp.json()
            items = list(data.get("mediaItems") or [])
            if items:
                yield items
            next_token = data.get("nextPageToken")
            if not next_token:
                break
            page_token = str(next_token)


async def delete_picker_session(
    creds_dict: dict[str, str | None],
    session_id: str,
) -> None:
    """Best-effort cleanup of the Picker session after ingest completes."""
    token = await _picker_access_token(creds_dict)
    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.delete(
            f"{PICKER_API_BASE}/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        )


async def get_media_item_bytes(base_url: str, creds_dict: dict[str, str | None]) -> bytes:
    """Download original bytes for a picked item.

    Picker API base URLs require an Authorization header AND the `=d` suffix.
    """
    token = await _picker_access_token(creds_dict)
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            f"{base_url}=d",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.content
