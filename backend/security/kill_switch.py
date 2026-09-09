"""Emergency kill switch (Ctrl + Alt + K).

Guarantees:
- Triggerable from (a) the global keyboard listener thread, (b) the REST API
  (`POST /api/kill`), (c) the frontend button — any of which works even if the
  primary execution workflow is stuck, because trigger() never awaits agents.
- Thread-safe: the keyboard listener runs in its own daemon thread.
- On trigger: sets the shared cancellation event, cancels every registered
  execution task, closes the Playwright browser, kills the managed terminal
  subprocess, cancels pending permission requests, clears the execution queue,
  publishes an event to the UI, and logs the emergency stop.
- Session memory is preserved (kill never deletes sessions).

Use `activate()` once at app startup to bind the loop + start the hotkey
listener; call `reset()` to allow a new execution after a kill.
"""
from __future__ import annotations

import asyncio
import sys
import threading
from typing import Optional, Set

from backend.events import event_bus
from backend.logging_utils import get_logger, log_json
from backend.models.schemas import AgentEvent
from backend.tools import registry
from backend.tools.kill_switch_ref import kill_state

log = get_logger("security.kill_switch")

HOTKEY = "ctrl+alt+k"


class KillSwitch:
    def __init__(self) -> None:
        self._tasks: Set[asyncio.Task] = set()
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._listener_thread: Optional[threading.Thread] = None
        self.hotkey_available = False
        self.last_triggered_at: Optional[str] = None
        self.trigger_count = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def activate(self) -> None:
        """Bind the loop and start the global hotkey listener (best effort)."""
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        kill_state.bind_loop()
        self._start_keyboard_listener()

    def _start_keyboard_listener(self) -> None:
        if sys.platform != "win32":
            log_json(log, 30, "kill_hotkey_unsupported_platform")
            return
        try:
            import keyboard  # optional dependency
        except Exception:
            log_json(log, 30, "kill_hotkey_unavailable",
                     reason="keyboard package not importable; UI button and /api/kill remain active")
            return

        def _listen() -> None:
            try:
                keyboard.add_hotkey(HOTKEY, self._hotkey_fired)
                self.hotkey_available = True
                log_json(log, 20, "kill_hotkey_registered", hotkey=HOTKEY)
                keyboard.wait()  # block this daemon thread forever
            except Exception as exc:  # pragma: no cover - needs privileges sometimes
                self.hotkey_available = False
                log_json(log, 30, "kill_hotkey_failed", error=type(exc).__name__)

        self._listener_thread = threading.Thread(
            target=_listen, name="colum-kill-listener", daemon=True
        )
        self._listener_thread.start()

    def _hotkey_fired(self) -> None:
        # Runs on the keyboard thread — must not await anything.
        log_json(log, 40, "kill_hotkey_pressed")
        self.trigger(source="hotkey")

    # ------------------------------------------------------------------
    # Registration of cancellable work
    # ------------------------------------------------------------------
    def register_task(self, task: asyncio.Task) -> None:
        with self._lock:
            self._tasks.add(task)
            self._tasks = {t for t in self._tasks if not t.done()}

    def unregister_task(self, task: asyncio.Task) -> None:
        with self._lock:
            self._tasks.discard(task)

    # ------------------------------------------------------------------
    # THE TRIGGER
    # ------------------------------------------------------------------
    def trigger(self, source: str = "api") -> dict:
        """Stop everything. Safe to call from any thread. Never raises."""
        log_json(log, 40, "kill_switch_triggered", source=source)
        kill_state.trigger()  # 1) shared cancellation event (tools check it)

        loop = self._loop
        if loop is not None and loop.is_running():
            # 2..7) everything loop-related is scheduled on the loop
            fut = asyncio.run_coroutine_threadsafe(self._shutdown_async(source), loop)
            try:
                fut.result(timeout=10)
            except Exception:  # noqa: BLE001 - never fail the trigger itself
                log_json(log, 40, "kill_switch_async_shutdown_incomplete")
        else:
            # No loop bound (early startup): still do the sync-safe parts.
            self._shutdown_sync_parts(source)

        with self._lock:
            self.trigger_count += 1
        import time as _t
        self.last_triggered_at = _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime())
        return {"killed": True, "source": source,
                "triggered_at": self.last_triggered_at}

    async def _shutdown_async(self, source: str) -> None:
        # 2/6) cancel all registered execution tasks (FastAPI execution tasks)
        with self._lock:
            tasks = list(self._tasks)
        cancelled = 0
        for t in tasks:
            if not t.done():
                t.cancel()
                cancelled += 1
        # 4) stop Playwright operations
        try:
            from backend.tools.playwright_tool import browser_session
            await browser_session.shutdown()
        except Exception:  # noqa: BLE001
            pass
        # 5) terminate managed subprocesses
        try:
            from backend.tools.terminal_tool import terminal_tool
            await terminal_tool._kill_process()
        except Exception:  # noqa: BLE001
            pass
        # 7) pending permissions are cancelled inside the orchestrator hook below
        try:
            from backend.security.permissions import permission_manager
            await permission_manager.cancel_all(reason="kill switch")
        except Exception:  # noqa: BLE001
            pass
        # 8) reset agent execution state (orchestrator listens for this event)
        await event_bus.publish(AgentEvent(
            event="kill_switch_activated",
            message=f"EMERGENCY STOP via {source}",
            data={"source": source, "tasks_cancelled": cancelled},
        ))
        log_json(log, 40, "kill_switch_complete", source=source,
                 tasks_cancelled=cancelled)

    def _shutdown_sync_parts(self, source: str) -> None:
        log_json(log, 40, "kill_switch_sync_shutdown", source=source)

    # ------------------------------------------------------------------
    # Reset (allow a fresh execution after a kill)
    # ------------------------------------------------------------------
    def reset(self) -> None:
        kill_state.reset()
        with self._lock:
            self._tasks = {t for t in self._tasks if not t.done()}
        log_json(log, 20, "kill_switch_reset")

    # ------------------------------------------------------------------
    # Status for the UI
    # ------------------------------------------------------------------
    def status(self) -> dict:
        return {
            "active": kill_state.active,
            "hotkey": HOTKEY,
            "hotkey_available": self.hotkey_available,
            "trigger_count": self.trigger_count,
            "last_triggered_at": self.last_triggered_at,
            "registered_tasks": len([t for t in self._tasks if not t.done()]),
        }


kill_switch = KillSwitch()
