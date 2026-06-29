"""
memorylane.backend
==================

This module defines the *seam* between the MemoryLane Streamlit UI and your
codebase / APIs. The UI (``app.py``) only ever talks to a ``MemoryLaneBackend``;
it never imports your internals directly. To integrate:

    1. Implement every method of ``MemoryLaneBackend`` against your code/API.
       (See ``integration.py`` for an HTTP/Google-Photos-Picker skeleton.)
    2. Return it from ``get_backend()`` instead of ``DemoBackend()``.

Everything below the ``DemoBackend`` line is throwaway demo data so the app runs
out of the box — delete it once your backend is wired.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol


# --------------------------------------------------------------------------- #
#  Data contracts                                                             #
# --------------------------------------------------------------------------- #
@dataclass
class PhotoResult:
    """One photo returned by a search."""

    id: str
    score: float  # similarity score, 0..1
    thumbnail_url: str | None = None  # https URL to a thumbnail
    # Fallback used only by the demo renderer when thumbnail_url is None:
    gradient: str | None = None


@dataclass
class ReasoningStep:
    """One step in the agent's tool-call trace, shown in the expander."""

    tool: str  # e.g. "semantic_search"
    detail: str  # human-readable result of the step


@dataclass
class SearchResult:
    results: list[PhotoResult] = field(default_factory=list)
    reasoning: list[ReasoningStep] = field(default_factory=list)


@dataclass
class PickerSession:
    """Mirrors a Google Photos Picker API session."""

    id: str
    picker_uri: str  # URL the user opens to pick photos
    media_items_set: bool = False  # True once the user finishes picking


@dataclass
class MediaItem:
    id: str
    base_url: str
    filename: str = ""
    gradient: str | None = None  # demo-only


@dataclass
class IngestProgress:
    done: int  # items ingested so far in this batch
    total: int  # items selected for this batch
    library_total: int  # running total across the whole library
    last_item: MediaItem | None = None


# --------------------------------------------------------------------------- #
#  The interface your backend must satisfy                                    #
# --------------------------------------------------------------------------- #
class MemoryLaneBackend(Protocol):
    # ---- auth -------------------------------------------------------------- #
    def sign_in(self, user_id: str, tenant_id: str) -> bool:
        """Authenticate the user. Return True on success. ``tenant_id`` scopes
        every downstream query (the services require it)."""

    def connect_url(self, user_id: str) -> str | None:
        """URL the user opens once to grant Google Photos access, or None if the
        backend needs no separate consent step (e.g. the demo)."""

    def library_count(self, user_id: str) -> int:
        """Number of photos already ingested & searchable for this user."""

    # ---- google photos picker --------------------------------------------- #
    def create_picker_session(self, user_id: str) -> PickerSession:
        """POST a new Picker session; return its id + pickerUri."""

    def poll_picker_session(self, session_id: str) -> PickerSession:
        """GET the session; ``media_items_set`` flips True when the user is done."""

    def list_picked_media(self, session_id: str) -> list[MediaItem]:
        """List the media items the user selected in the Picker."""

    # ---- ingestion --------------------------------------------------------- #
    def ingest(self, user_id: str, items: list[MediaItem]) -> Iterator[IngestProgress]:
        """Ingest selected photos (download, embed, index). Yield progress so the
        UI can render a live bar. Yield once per item (or per batch)."""

    # ---- search ------------------------------------------------------------ #
    def search(self, user_id: str, query: str, limit: int) -> SearchResult:
        """Run the agentic search. Return ranked results + the reasoning trace."""


# --------------------------------------------------------------------------- #
#  Wire your real backend here                                                #
# --------------------------------------------------------------------------- #
def get_backend() -> MemoryLaneBackend:
    """HttpBackend (real services) when MEMORYLANE_USE_HTTP is set, else the
    in-memory DemoBackend so the app is clickable with zero infra."""
    if os.environ.get("MEMORYLANE_USE_HTTP", "").lower() in ("1", "true", "yes"):
        from .integration import HttpBackend

        return HttpBackend()
    return DemoBackend()


# =========================================================================== #
#  DEMO BACKEND — delete once your real backend is wired                      #
# =========================================================================== #
_GRADIENTS = [
    "linear-gradient(160deg,#f6b878,#e8794f 55%,#7a3b6b)",
    "linear-gradient(160deg,#f7d9b0,#e0a463 60%,#9c5a3c)",
    "linear-gradient(160deg,#bfe3e0,#5fa9b0 55%,#2f6f86)",
    "linear-gradient(160deg,#e9b27a,#c46a3a 55%,#7a3326)",
    "linear-gradient(160deg,#5a4633,#8a5a2f 55%,#e3a14a)",
    "linear-gradient(160deg,#dfe7a8,#a9c25f 55%,#5f8a4a)",
    "linear-gradient(160deg,#e6a9b6,#9a6aa0 55%,#caa24a)",
    "linear-gradient(160deg,#cfe0ea,#8fb6cf 55%,#5a7fa0)",
    "linear-gradient(160deg,#f3d27a,#c7a23e 60%,#6f7a3a)",
]


class DemoBackend:
    """In-memory fake so the UI is fully clickable without your services."""

    def __init__(self) -> None:
        self._library = 1204
        self._session_started_at = 0.0

    def sign_in(self, user_id: str, tenant_id: str = "") -> bool:
        return bool(user_id.strip())

    def connect_url(self, user_id: str) -> str | None:
        return None  # demo is always "connected"

    def library_count(self, user_id: str) -> int:
        return self._library

    def create_picker_session(self, user_id: str) -> PickerSession:
        self._session_started_at = time.time()
        return PickerSession(
            id="demo-sess-8f2a",
            picker_uri="https://photos.google.com/picker/session/8f2a",
            media_items_set=False,
        )

    def poll_picker_session(self, session_id: str) -> PickerSession:
        # Pretend the user finishes picking ~4s after the session opens.
        done = (time.time() - self._session_started_at) > 4
        return PickerSession(id=session_id, picker_uri="", media_items_set=done)

    def list_picked_media(self, session_id: str) -> list[MediaItem]:
        return [
            MediaItem(
                id=f"m{i}",
                base_url="",
                filename=f"IMG_{i:04d}.jpg",
                gradient=_GRADIENTS[i % len(_GRADIENTS)],
            )
            for i in range(48)
        ]

    def ingest(self, user_id: str, items: list[MediaItem]) -> Iterator[IngestProgress]:
        total = len(items)
        for i, item in enumerate(items, start=1):
            time.sleep(0.05)  # simulate work
            self._library += 1
            yield IngestProgress(done=i, total=total, library_total=self._library, last_item=item)

    def search(self, user_id: str, query: str, limit: int) -> SearchResult:
        time.sleep(1.2)  # simulate agent latency
        q = query.lower()
        if (not q.strip()) or any(w in q for w in ("snow", "nothing", "xyzzy")):
            return SearchResult(results=[], reasoning=[])  # empty state
        results = [
            PhotoResult(
                id=f"p{i}",
                score=max(0.40, 0.912 - i * 0.0075),
                gradient=_GRADIENTS[i % len(_GRADIENTS)],
            )
            for i in range(limit)
        ]
        reasoning = [
            ReasoningStep("semantic_search", f'query "{query}" → 24 candidates'),
            ReasoningStep("date_filter_search", "narrowed to summer 2023"),
            ReasoningStep("Reflector", "confidence high, stopping after iteration 2"),
        ]
        return SearchResult(results=results, reasoning=reasoning)
