import asyncio
import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import google.auth.transport.requests
import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.config import settings

PICKER_API_BASE = "https://photospicker.googleapis.com/v1"


@dataclass(frozen=True)
class ParsedPickedItem:
    external_id: str
    base_url: str
    item_type: str  # "PHOTO" | "VIDEO" | other
    mime_type: str
    filename: str | None
    width: int | None
    height: int | None
    taken_at: datetime | None
    exif_data: dict[str, object] = field(default_factory=dict)


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[call-overload, no-any-return]
    except (TypeError, ValueError):
        return None


def _parse_rfc3339(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    with contextlib.suppress(ValueError):
        # `datetime.fromisoformat` accepts the trailing "Z" only on 3.11+; normalize for safety.
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    return None


def parse_picked_item(item: dict[str, object]) -> ParsedPickedItem | None:
    """Map a Picker API mediaItem into the fields we persist.

    Returns None when the item lacks `id` or `mediaFile.baseUrl` (unusable rows).
    Callers must still filter by `item_type != "PHOTO"` to skip videos.
    """
    external_id = str(item.get("id") or "")
    if not external_id:
        return None

    media_file = item.get("mediaFile")
    if not isinstance(media_file, dict):
        return None
    base_url = str(media_file.get("baseUrl") or "")
    if not base_url:
        return None

    item_type = str(item.get("type") or "PHOTO").upper()
    metadata = media_file.get("mediaFileMetadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    exif: dict[str, object] = {"source": "picker_api"}
    for src_key, dst_key in (
        ("cameraMake", "camera_make"),
        ("cameraModel", "camera_model"),
    ):
        value = metadata.get(src_key)
        if value:
            exif[dst_key] = value

    photo_meta = metadata.get("photoMetadata") or {}
    if isinstance(photo_meta, dict):
        for src_key, dst_key in (
            ("focalLength", "focal_length"),
            ("apertureFNumber", "aperture_f_number"),
            ("isoEquivalent", "iso_equivalent"),
            ("exposureTime", "exposure_time"),
        ):
            value = photo_meta.get(src_key)
            if value is not None:
                exif[dst_key] = value

    return ParsedPickedItem(
        external_id=external_id,
        base_url=base_url,
        item_type=item_type,
        mime_type=str(media_file.get("mimeType") or "image/jpeg"),
        filename=(str(media_file.get("filename") or "") or None),
        width=_to_int(metadata.get("width")),
        height=_to_int(metadata.get("height")),
        taken_at=_parse_rfc3339(item.get("createTime")),
        exif_data=exif,
    )


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

    return Credentials(  # type: ignore[no-untyped-call]
        token=creds_dict.get("access_token"),
        refresh_token=creds_dict.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",  # noqa: S106
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=scopes,
        expiry=expiry,
    )


def _refreshed_access_token(creds_dict: dict[str, str | None]) -> str:
    """Build Credentials, refresh if expired/expiring, and return the current access token."""
    creds = _build_credentials(creds_dict)
    if not creds.valid:
        creds.refresh(google.auth.transport.requests.Request())  # type: ignore[no-untyped-call]
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
            items = list(data.get("mediaItems") or [])  # type: ignore[call-overload]
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
