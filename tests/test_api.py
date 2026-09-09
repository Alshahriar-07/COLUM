"""API integration tests — real endpoints via FastAPI TestClient (no network)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture(scope="module")
def client():
    # TestClient runs lifespan: logging, session restore, tool registration,
    # kill-switch activation (hotkey listener degrades gracefully if unavailable).
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_status_endpoint_shape(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    for key in ("providers", "usage", "kill_switch", "screen", "voice"):
        assert key in body
    # Secrets must never appear in status output.
    assert "openrouter_key_1" not in str(body)


def test_settings_roundtrip_masks_secrets(client):
    r = client.post("/api/settings", json={"theme": "dark"})
    assert r.status_code == 200
    snap = r.json()["settings"]
    assert snap["theme"] == "dark"
    # Keys are masked, never echoed in clear.
    assert "openrouter_key_1" not in snap
    assert "openrouter_key_1_masked" in snap
    # restore
    client.post("/api/settings", json={"theme": "light"})


def test_settings_rejects_invalid_permission_mode(client):
    r = client.post("/api/settings", json={"permission_mode": "yolo"})
    assert r.status_code == 200
    assert "permission_mode" not in r.json()["applied"]


def test_kill_and_reset_cycle(client):
    r = client.post("/api/kill")
    assert r.status_code == 200
    assert r.json()["killed"] is True
    # UI state shows the kill
    st = client.get("/api/status").json()
    assert st["kill_switch"]["active"] is True
    r2 = client.post("/api/kill/reset")
    assert r2.status_code == 200
    st2 = client.get("/api/status").json()
    assert st2["kill_switch"]["active"] is False


def test_screen_endpoint_returns_compact_json(client):
    r = client.get("/api/screen")
    assert r.status_code == 200
    body = r.json()
    # Honest degraded output is fine; fabricated elements are not.
    assert "screen" in body or "note" in body


def test_voice_status_honest(client):
    r = client.get("/api/voice/status")
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "faster_whisper"
    assert isinstance(body["available"], bool)


def test_voice_transcribe_empty_payload_is_error_not_crash(client):
    r = client.post("/api/voice/transcribe", json={"audio_b64": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]


def test_session_flow(client):
    # create via a chat with a provider-less fallback path is env-dependent;
    # exercise the session endpoints directly instead.
    sessions = client.get("/api/session").json()["sessions"]
    assert isinstance(sessions, list)


def test_permission_decision_unknown_404(client):
    r = client.post("/api/permission/decision",
                    json={"request_id": "perm_nope", "approved": True})
    assert r.status_code == 404


def test_stop_nothing_running(client):
    r = client.post("/api/stop")
    assert r.status_code == 200
    assert r.json()["stopped"] is False


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "COLUM" in r.text


# ---------------------------------------------------------------------------
# Security wiring visible through the API
# ---------------------------------------------------------------------------

def test_permission_pending_empty_initially(client):
    r = client.get("/api/permission/pending")
    assert r.status_code == 200
    assert r.json()["pending"] == []
