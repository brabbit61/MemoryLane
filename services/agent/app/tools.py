from typing import Any

import httpx
from langchain_core.tools import tool

from app.config import settings

_ParamValue = str | int | float | bool | None
_Params = dict[str, _ParamValue]


async def _call_search(params: _Params) -> list[dict[str, Any]]:
    """Shared transport: strips None values, calls /search, raises on error."""
    clean: dict[str, str | int | float | bool] = {k: v for k, v in params.items() if v is not None}
    url = f"{settings.search_service_url}/search"
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        try:
            response = await client.get(url, params=clean)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Search service timed out: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Search service error {exc.response.status_code}: {exc.response.text}"
            ) from exc
    return response.json()  # type: ignore[no-any-return]


@tool
async def semantic_search(
    query: str,
    tenant_id: str,
    user_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search photos by natural language description. Returns semantically ranked results.
    Use for open-ended queries with no specific date or camera/location constraints."""
    return await _call_search(
        {"q": query, "tenant_id": tenant_id, "user_id": user_id, "limit": limit}
    )


@tool
async def date_filter_search(
    query: str,
    tenant_id: str,
    user_id: str,
    start_date: str,
    end_date: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search photos within a date range. Use when the query mentions time
    (e.g. 'last summer', 'in 2023', 'from my birthday').
    start_date and end_date must be ISO 8601 strings (e.g. '2023-06-01')."""
    return await _call_search(
        {
            "q": query,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        }
    )


@tool
async def metadata_filter_search(
    query: str,
    tenant_id: str,
    user_id: str,
    camera_make: str | None = None,
    min_latitude: float | None = None,
    max_latitude: float | None = None,
    min_longitude: float | None = None,
    max_longitude: float | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search photos with camera or location filters. Use when the query mentions
    a camera brand or a geographic area. All filter params are optional — supply
    only the relevant ones."""
    return await _call_search(
        {
            "q": query,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "camera_make": camera_make,
            "min_latitude": min_latitude,
            "max_latitude": max_latitude,
            "min_longitude": min_longitude,
            "max_longitude": max_longitude,
            "limit": limit,
        }
    )


@tool
async def combined_filter_search(
    query: str,
    tenant_id: str,
    user_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    camera_make: str | None = None,
    min_latitude: float | None = None,
    max_latitude: float | None = None,
    min_longitude: float | None = None,
    max_longitude: float | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search photos with both date-range and camera/location filters in a single call.
    Use when the query mentions time AND location or camera — e.g. 'Paris trip last summer
    on my Canon'. Prefer this over calling date_filter_search and metadata_filter_search
    separately; the backend applies all constraints as a single SQL WHERE clause, so results
    are a true intersection rather than two independently ranked lists that must be merged."""
    return await _call_search(
        {
            "q": query,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
            "camera_make": camera_make,
            "min_latitude": min_latitude,
            "max_latitude": max_latitude,
            "min_longitude": min_longitude,
            "max_longitude": max_longitude,
            "limit": limit,
        }
    )
