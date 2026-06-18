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
async def search_photos(
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
    """Search photos by natural language description with optional filters.

    Use filters only when the query mentions them:
    - Time ("last summer", "in 2023"): set start_date and end_date (ISO 8601, e.g. "2023-06-01")
    - Camera brand ("my Canon"): set camera_make
    - Geographic area: set min/max latitude and longitude

    Omit unused filters. All supplied filters combine as AND constraints.
    """
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
