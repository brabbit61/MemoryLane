"""
integration.py
=======================

Real backend that wires the Streamlit UI to the MemoryLane microservices:

    agent-svc       POST /agent/search                    (search + reasoning)
    ingestion-svc   GET  /oauth/google/init               (connect Google)
                    POST /sync/google/{uid}/start          (open picker)
                    GET  /sync/google/{uid}/session/{sid}  (poll picking)
                    POST /sync/google/{uid}/ingest/{sid}   (start ingest)

Enable it by setting ``MEMORYLANE_USE_HTTP=1`` (see ``backend.get_backend``).
Service URLs default to localhost dev ports and are overridable via env.

Known gaps (the backend doesn't expose these yet — surfaced honestly, not faked):
  * No picked-media list endpoint  -> ``list_picked_media`` returns [].
  * Ingest is fire-and-forget      -> ``ingest`` triggers the job and yields a
                                       single terminal progress tick.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import requests

from .backend import (
    IngestProgress,
    MediaItem,
    PhotoResult,
    PickerSession,
    ReasoningStep,
    SearchResult,
)

AGENT_URL = os.environ.get("MEMORYLANE_AGENT_URL", "http://localhost:8003").rstrip("/")
SEARCH_URL = os.environ.get("MEMORYLANE_SEARCH_URL", "http://localhost:8002").rstrip("/")
INGESTION_URL = os.environ.get("MEMORYLANE_INGESTION_URL", "http://localhost:8001").rstrip("/")

# The agent runs an LLM loop; give it room. Picker/oauth calls are quick.
AGENT_TIMEOUT = float(os.environ.get("MEMORYLANE_AGENT_TIMEOUT", "120"))


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


class HttpBackend:
    def __init__(self) -> None:
        self._tenant: dict[str, str] = {}  # user_id -> tenant_id
        self._picker_user: dict[str, str] = {}  # session_id -> user_id

    # ---- auth -------------------------------------------------------------- #
    def sign_in(self, user_id: str, tenant_id: str) -> bool:
        # No passwords in this system — "sign in" just confirms the user exists.
        # Services key everything off UUIDs, so reject bad shapes up front, then
        # probe the DB via oauth/init, which 404s for an unknown user.
        if not (_is_uuid(user_id) and _is_uuid(tenant_id)):
            return False
        r = requests.get(
            f"{INGESTION_URL}/oauth/google/init", params={"user_id": user_id}, timeout=30
        )
        if r.status_code == 404:
            return False
        r.raise_for_status()
        self._tenant[user_id] = tenant_id
        return True

    def connect_url(self, user_id: str) -> str | None:
        """OAuth URL the user opens once to grant Google Photos access."""
        r = requests.get(
            f"{INGESTION_URL}/oauth/google/init", params={"user_id": user_id}, timeout=30
        )
        r.raise_for_status()
        return r.json()["auth_url"]

    def library_count(self, user_id: str) -> int:
        tenant_id = self._tenant.get(user_id)
        if not tenant_id:
            return 0
        try:
            r = requests.get(
                f"{SEARCH_URL}/photos/count",
                params={"tenant_id": tenant_id, "user_id": user_id},
                timeout=30,
            )
            r.raise_for_status()
            return int(r.json()["count"])
        except requests.RequestException:
            return 0  # count is cosmetic; never block the UI on it

    # ---- google photos picker --------------------------------------------- #
    def create_picker_session(self, user_id: str) -> PickerSession:
        r = requests.post(f"{INGESTION_URL}/sync/google/{user_id}/start", timeout=30)
        if r.status_code == 400:
            raise RuntimeError("Google Photos isn't connected yet — use Connect first.")
        r.raise_for_status()
        data = r.json()
        sid = data["session_id"]
        self._picker_user[sid] = user_id
        return PickerSession(id=sid, picker_uri=data["picker_uri"], media_items_set=False)

    def poll_picker_session(self, session_id: str) -> PickerSession:
        user_id = self._picker_user[session_id]
        r = requests.get(f"{INGESTION_URL}/sync/google/{user_id}/session/{session_id}", timeout=30)
        r.raise_for_status()
        data = r.json()
        return PickerSession(
            id=session_id, picker_uri="", media_items_set=bool(data.get("media_items_set"))
        )

    def list_picked_media(self, session_id: str) -> list[MediaItem]:
        # ponytail: the API ingests picked items server-side and doesn't list them
        # back to the client. Nothing to show; ingest() drives off the session id.
        return []

    # ---- ingestion --------------------------------------------------------- #
    def ingest(self, user_id: str, items: list[MediaItem]) -> Iterator[IngestProgress]:
        # `items` is unused: the ingest endpoint works off the most-recent picker
        # session for this user, not a client-supplied item list.
        session_id = next((sid for sid, uid in self._picker_user.items() if uid == user_id), None)
        if session_id is None:
            raise RuntimeError("No active picker session to ingest.")
        r = requests.post(f"{INGESTION_URL}/sync/google/{user_id}/ingest/{session_id}", timeout=30)
        r.raise_for_status()
        # Fire-and-forget background job — no per-item progress is exposed, so emit
        # a single terminal tick to advance the UI to its "done" state.
        yield IngestProgress(done=1, total=1, library_total=self.library_count(user_id))

    # ---- search ------------------------------------------------------------ #
    def search(self, user_id: str, query: str, limit: int) -> SearchResult:
        tenant_id = self._tenant.get(user_id)
        r = requests.post(
            f"{AGENT_URL}/agent/search",
            json={
                "query": query,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "limit": limit,
            },
            timeout=AGENT_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        results = [
            PhotoResult(id=str(p["photo_id"]), score=float(p["score"]), thumbnail_url=p["url"])
            for p in data.get("results", [])
        ]
        reasoning = [ReasoningStep(tool="agent", detail=str(s)) for s in data.get("reasoning", [])]
        return SearchResult(results=results, reasoning=reasoning)
