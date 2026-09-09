"""Kill state shared flag — low-level, import-cycle-free reference for tools.

The real kill switch logic lives in `backend/security/kill_switch.py`; this
module only holds the shared cancellation event so blocking tool code can
check cancellation cheaply, from any thread.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Optional


class KillState:
    def __init__(self) -> None:
        self._event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self.active = False
        self.generation = 0  # increments on each kill; stale work can detect it

    def bind_loop(self) -> Optional[asyncio.Event]:
        """Bind the cancellation event to the running loop (called at startup)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return self._event
        with self._lock:
            if self._loop is not loop or self._event is None:
                self._loop = loop
                self._event = asyncio.Event()
                if self.active:
                    self._event.set()
            return self._event

    @property
    def event(self) -> Optional[asyncio.Event]:
        return self._event

    def trigger(self) -> None:
        """Thread-safe: set the event on the bound loop from any thread."""
        with self._lock:
            self.active = True
            self.generation += 1
            loop, event = self._loop, self._event
        if loop is not None and event is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                pass

    def reset(self) -> None:
        with self._lock:
            self.active = False
            loop, event = self._loop, self._event
        if loop is not None and event is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(event.clear)
            except RuntimeError:
                pass

    def is_cancelled(self) -> bool:
        ev = self._event
        return bool(self.active or (ev is not None and ev.is_set()))


kill_state = KillState()
