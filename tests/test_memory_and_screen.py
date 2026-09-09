"""Memory + screen pipeline tests (session store, corrupt handling, compact JSON)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from backend.memory.session_store import SessionStore
from backend.models.schemas import (
    ChatMessage,
    ChatRole,
    Plan,
    PlanStep,
    RiskLevel,
    ScreenContext,
    ScreenElement,
)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Session store
# ---------------------------------------------------------------------------

def _make_store(tmp_path: Path) -> SessionStore:
    return SessionStore(directory=tmp_path / "sessions")


def test_create_and_list_sessions(tmp_path):
    async def scenario():
        store = _make_store(tmp_path)
        sid = await store.create_session("Hello world")
        sessions = await store.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == sid
        assert sessions[0]["title"] == "Hello world"
    run(scenario())


def test_messages_persisted_and_truncated_title(tmp_path):
    async def scenario():
        store = _make_store(tmp_path)
        sid = await store.create_session()
        await store.add_message(sid, ChatMessage(
            role=ChatRole.USER, content="open the browser and check example.com"))
        rec = await store.get_session(sid)
        assert rec["summary"]["title"].startswith("open the browser")
        msgs = await store.get_messages(sid)
        assert msgs[0].content.startswith("open the browser")
    run(scenario())


def test_message_ring_buffer(tmp_path):
    async def scenario():
        store = SessionStore(directory=tmp_path / "s")
        sid = await store.create_session()
        from backend.memory.session_store import MAX_MESSAGES_KEPT
        for i in range(MAX_MESSAGES_KEPT + 20):
            await store.add_message(sid, ChatMessage(
                role=ChatRole.USER, content=f"m{i}"))
        rec = await store.get_session(sid)
        assert len(rec["messages"]) == MAX_MESSAGES_KEPT
        assert rec["messages"][0]["content"] == "m20"
    run(scenario())


def test_record_plan_and_step_state(tmp_path):
    async def scenario():
        store = _make_store(tmp_path)
        sid = await store.create_session()
        step = PlanStep(description="do it", tool="browser.open", risk=RiskLevel.LOW)
        plan = Plan(goal="g", steps=[step], session_id=sid)
        await store.record_plan(sid, plan)
        await store.update_plan_step_state(sid, plan.id, step.id, "completed")
        rec = await store.get_session(sid)
        assert rec["plans"][plan.id]["steps"][0]["state"] == "completed"
    run(scenario())


def test_restore_latest_session(tmp_path):
    async def scenario():
        store = _make_store(tmp_path)
        await store.create_session("older")
        sid2 = await store.create_session("newest")
        await store.add_message(sid2, ChatMessage(role=ChatRole.USER,
                                                  content="restore me"))
        # New store instance restores from disk.
        fresh = SessionStore(directory=tmp_path / "sessions")
        restored = fresh.restore_latest()
        assert restored == sid2
    run(scenario())


def test_corrupt_session_quarantined(tmp_path):
    async def scenario():
        d = tmp_path / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        (d / "sess_bad.json").write_text("{ not valid json", encoding="utf-8")
        store = SessionStore(directory=d)
        restored = store.restore_latest()
        assert restored is None
        assert (d / "sess_bad.json.corrupt").exists()
    run(scenario())


def test_session_file_has_no_secrets_field(tmp_path):
    async def scenario():
        store = _make_store(tmp_path)
        sid = await store.create_session("t")
        await store.add_message(sid, ChatMessage(role=ChatRole.USER,
                                                 content="hello"))
        path = tmp_path / "sessions" / f"{sid}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        flat = json.dumps(data).lower()
        assert "api_key" not in flat and "authorization" not in flat
    run(scenario())


# ---------------------------------------------------------------------------
# Screen context schemas (compact JSON contract)
# ---------------------------------------------------------------------------

def test_screen_compact_json_shape():
    ctx = ScreenContext(
        width=1920, height=1080, active_window="Editor",
        elements=[
            ScreenElement(type="button", text="OK", x=10, y=20, width=80, height=30,
                          confidence=0.9),
            ScreenElement(type="text", text="Welcome", x=0, y=0, confidence=0.5),
        ],
    )
    compact = ctx.compact(max_elements=10)
    assert compact["screen"] == {"width": 1920, "height": 1080}
    assert compact["active_window"] == "Editor"
    assert compact["elements"][0]["text"] == "OK"


def test_screen_compact_respects_max_and_confidence_sort():
    els = [ScreenElement(x=i, y=i, confidence=i / 10.0, text=str(i))
           for i in range(1, 11)]
    ctx = ScreenContext(width=100, height=100, elements=els)
    compact = ctx.compact(max_elements=3)
    assert len(compact["elements"]) == 3
    confs = [e["confidence"] for e in compact["elements"]]
    assert confs == sorted(confs, reverse=True)


def test_screen_compact_includes_note_when_degraded():
    ctx = ScreenContext(width=0, height=0, note="OCR unavailable")
    assert "note" in ctx.compact()


# ---------------------------------------------------------------------------
# Screen pipeline status (honest capability reporting)
# ---------------------------------------------------------------------------

def test_screen_status_reports_honestly():
    from backend.screen.pipeline import screen_pipeline
    st = screen_pipeline.status()
    assert isinstance(st["capture_available"], bool)
    assert isinstance(st["ocr_available"], bool)
    assert "screen_enabled" in st


def test_verify_expected_state_handles_ocr_missing():
    from backend.screen import pipeline as pl

    async def scenario():
        sp = pl.ScreenPipeline()
        if not sp.ocr_ready:
            res = await sp.verify_expected_state("hello world visible")
            assert res["verified"] is False
            assert res["method"] == "ocr_unavailable"
        else:
            res = await sp.verify_expected_state("the and should")
            # only stop-words → trivially true, method ocr
            assert res["method"] == "ocr"

    run(scenario())
