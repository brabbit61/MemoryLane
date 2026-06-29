"""Wiring checks for the real HttpBackend (mocked HTTP — no services needed).

Run: pytest src/ui/tests   (or just `python src/ui/tests/test_backend.py`).
Covers the non-trivial bits: sign-in existence semantics and the
agent/search response -> UI dataclass mapping.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import memorylane.integration as ie

USER = "00000000-0000-0000-0000-000000000002"
TENANT = "00000000-0000-0000-0000-000000000001"


def _resp(status: int = 200, payload: dict | None = None) -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload or {}
    m.raise_for_status = lambda: None
    return m


def test_sign_in_rejects_bad_uuids() -> None:
    assert ie.HttpBackend().sign_in("not-a-uuid", "also-bad") is False


def test_sign_in_404_means_unknown_user() -> None:
    with patch.object(ie.requests, "get", return_value=_resp(404)):
        assert ie.HttpBackend().sign_in(USER, TENANT) is False


def test_sign_in_200_succeeds_and_caches_tenant() -> None:
    b = ie.HttpBackend()
    with patch.object(ie.requests, "get", return_value=_resp(200, {"auth_url": "http://x"})):
        assert b.sign_in(USER, TENANT) is True
    assert b._tenant[USER] == TENANT


def test_search_maps_agent_response_to_dataclasses() -> None:
    b = ie.HttpBackend()
    payload = {
        "results": [{"photo_id": "p1", "score": 0.91, "url": "http://t/1"}],
        "reasoning": ["semantic_search: 24 candidates"],
    }
    with patch.object(ie.requests, "post", return_value=_resp(200, payload)):
        sr = b.search(USER, "beach", 12)
    assert sr.results[0].id == "p1"
    assert sr.results[0].thumbnail_url == "http://t/1"
    assert abs(sr.results[0].score - 0.91) < 1e-9
    assert sr.reasoning[0].tool == "agent"
    assert "semantic_search" in sr.reasoning[0].detail


def test_library_count_reads_count_field() -> None:
    b = ie.HttpBackend()
    b._tenant[USER] = TENANT
    with patch.object(ie.requests, "get", return_value=_resp(200, {"count": 7})):
        assert b.library_count(USER) == 7


def test_create_picker_session_400_is_friendly() -> None:
    with patch.object(ie.requests, "post", return_value=_resp(400)):
        try:
            ie.HttpBackend().create_picker_session(USER)
            raise AssertionError("expected RuntimeError")
        except RuntimeError as exc:
            assert "connected" in str(exc)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
