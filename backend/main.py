"""COLUM FastAPI application — API surface + static frontend + WebSocket.

Lifespan: setup logging → restore latest session → register tools →
activate kill switch (hotkey listener + loop binding). Endpoints never bypass
the security layer: tool execution only happens through the orchestrator.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.agents.master import OrchestratorBusy, master_agent
from backend.config import (
    FRONTEND_DIR,
    config,
    settings_store,
)
from backend.events import event_bus
from backend.logging_utils import get_logger, log_json, setup_logging
from backend.memory.session_store import session_store
from backend.models.schemas import (
    ChatMessage,
    ChatRequest,
    ChatRole,
    PermissionDecisionRequest,
    RiskLevel,
    SettingsUpdateRequest,
    TranscribeResponse,
)
from backend.providers.router import router as provider_router
from backend.screen.pipeline import screen_pipeline
from backend.security.kill_switch import kill_switch
from backend.security.permissions import permission_manager
from backend.security.risk import permission_rationale
from backend.tools import register_tools, registry
from backend.tools.kill_switch_ref import kill_state
from backend.voice.stt import stt_engine

log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(config.log_level)
    restored = session_store.restore_latest()
    register_tools()
    kill_switch.activate()
    kill_state.bind_loop()
    log_json(log, 20, "colum_started", host=config.host, port=config.port,
             restored_session=restored or "",
             tools=len(registry.specs()))
    yield
    try:
        from backend.tools.playwright_tool import browser_session
        await browser_session.shutdown()
    except Exception:  # noqa: BLE001
        pass
    log_json(log, 20, "colum_stopped")


app = FastAPI(title=config.app_name, version=config.version, lifespan=lifespan)


# ---------------------------------------------------------------------------
# Status / settings / providers
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def status() -> dict[str, Any]:
    return {
        "app": config.app_name,
        "version": config.version,
        "providers": provider_router.status(),
        "usage": provider_router.usage(),
        "kill_switch": kill_switch.status(),
        "screen": screen_pipeline.status(),
        "voice": stt_engine.status(),
        "permissions_pending": len(permission_manager.pending_list()),
        "events_recent": [e.model_dump(mode="json")
                          for e in event_bus.recent(30)],
    }


@app.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    snap = settings_store.snapshot()
    snap["rationale"] = permission_rationale(RiskLevel.MEDIUM,
                                              snap["permission_mode"])
    return snap


@app.post("/api/settings")
async def update_settings(req: SettingsUpdateRequest) -> dict[str, Any]:
    applied = settings_store.update(**req.model_dump(exclude_none=True))
    provider_router.sync_from_settings()
    log_json(log, 20, "settings_updated", applied=applied)
    return {"applied": applied, "settings": settings_store.snapshot()}


# ---------------------------------------------------------------------------
# Chat / plan / execute
# ---------------------------------------------------------------------------

@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    sid = await session_store.ensure_session(req.session_id)
    try:
        payload = await master_agent.handle_message(
            sid, req.message, execute=req.execute)
    except OrchestratorBusy:
        raise HTTPException(status_code=409,
                            detail="a plan is already running; stop it first")
    except Exception as exc:  # noqa: BLE001 - surfaced honestly to the UI
        log_json(log, 30, "chat_error", error=type(exc).__name__)
        msg = ChatMessage(session_id=sid, role=ChatRole.ERROR,
                          content=f"execution error: {type(exc).__name__}: "
                                  f"{str(exc)[:400]}")
        await session_store.add_message(sid, msg)
        return {"session_id": sid, "message": msg.model_dump(mode="json"),
                "plan": None, "plan_state": "failed"}
    plan = payload.get("plan")
    return {
        "session_id": sid,
        "message": payload["message"].model_dump(mode="json")
        if isinstance(payload.get("message"), ChatMessage)
        else payload.get("message"),
        "plan": plan.model_dump(mode="json") if plan else None,
        "plan_state": plan.steps[-1].state.value if plan and plan.steps else None,
    }


@app.post("/api/plan")
async def plan_only(req: ChatRequest) -> dict[str, Any]:
    req.execute = False
    return await chat(req)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

@app.get("/api/permission/pending")
async def permission_pending() -> dict[str, Any]:
    return {"pending": [r.model_dump(mode="json")
                        for r in permission_manager.pending_list()]}


@app.post("/api/permission/decision")
async def permission_decision(req: PermissionDecisionRequest) -> dict[str, Any]:
    try:
        permission_manager.resolve(req.request_id, req.approved)
    except KeyError:
        raise HTTPException(status_code=404,
                            detail="unknown or already-resolved request")
    return {"ok": True, "request_id": req.request_id,
            "approved": req.approved}


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------

@app.get("/api/screen")
async def screen(max_elements: Optional[int] = None) -> dict[str, Any]:
    return await screen_pipeline.compact_json(max_elements)


@app.get("/api/screen/status")
async def screen_status() -> dict[str, Any]:
    return screen_pipeline.status()


# ---------------------------------------------------------------------------
# Sessions / memory
# ---------------------------------------------------------------------------

@app.get("/api/session")
async def session_list() -> dict[str, Any]:
    return {"sessions": await session_store.list_sessions()}


@app.get("/api/session/{session_id}")
async def session_get(session_id: str) -> dict[str, Any]:
    rec = await session_store.get_session(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="session not found")
    msgs = await session_store.get_messages(session_id, limit=100)
    return {
        "session_id": session_id,
        "summary": rec.get("summary", {}),
        "messages": [m.model_dump(mode="json") for m in msgs],
        "plans": rec.get("plans", {}),
    }


@app.delete("/api/session/{session_id}")
async def session_delete(session_id: str) -> dict[str, Any]:
    deleted = await session_store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="session not found")
    return {"deleted": session_id}


# ---------------------------------------------------------------------------
# Voice
# ---------------------------------------------------------------------------

@app.post("/api/voice/transcribe")
async def voice_transcribe(payload: dict[str, Any]) -> TranscribeResponse:
    audio_b64 = payload.get("audio_b64", "")
    import base64
    try:
        raw = base64.b64decode(audio_b64) if audio_b64 else b""
    except Exception:  # noqa: BLE001
        raw = b""
    result = await stt_engine.transcribe_wav(raw)
    return TranscribeResponse(**result)


@app.get("/api/voice/status")
async def voice_status() -> dict[str, Any]:
    return stt_engine.status()


# ---------------------------------------------------------------------------
# Kill switch / stop
# ---------------------------------------------------------------------------

@app.post("/api/kill")
async def kill() -> dict[str, Any]:
    result = kill_switch.trigger(source="api")
    return result


@app.post("/api/kill/reset")
async def kill_reset() -> dict[str, Any]:
    kill_switch.reset()
    return {"active": kill_state.active}


@app.post("/api/stop")
async def stop_current() -> dict[str, Any]:
    stopped = await master_agent.stop_current()
    return {"stopped": stopped}


# ---------------------------------------------------------------------------
# WebSocket — live AgentEvent stream
# ---------------------------------------------------------------------------

@app.websocket("/ws/events")
async def ws_events(ws: WebSocket) -> None:
    await ws.accept()
    queue = event_bus.subscribe()
    try:
        while True:
            event = await queue.get()
            await ws.send_json(event.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log_json(log, 30, "ws_error", error=type(exc).__name__)
    finally:
        event_bus.unsubscribe(queue)


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

assets_dir = FRONTEND_DIR / "assets"
if assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

for _static_dir, _mount in ((FRONTEND_DIR / "css", "/css"),
                            (FRONTEND_DIR / "js", "/js")):
    if _static_dir.is_dir():
        app.mount(_mount, StaticFiles(directory=str(_static_dir)), name=_mount.strip("/"))


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "app": config.app_name}
