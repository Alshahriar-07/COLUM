"""In-process event bus.

Agents and tools publish `AgentEvent`s; the WebSocket endpoint streams them to
the frontend. A bounded deque keeps recent events for late-joining clients and
for the status endpoint.
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Callable, Deque, Set

from backend.logging_utils import get_logger
from backend.models.schemas import AgentEvent

log = get_logger("events")


class EventBus:
    def __init__(self, history_size: int = 500) -> None:
        self._subscribers: Set[asyncio.Queue] = set()
        self._history: Deque[AgentEvent] = deque(maxlen=history_size)
        self._lock = asyncio.Lock()

    async def publish(self, event: AgentEvent) -> None:
        self._history.append(event)
        async with self._lock:
            dead: list[asyncio.Queue] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subscribers.discard(q)
                log.warning("dropped slow websocket subscriber")

    def publish_nowait(self, event: AgentEvent) -> None:
        """Safe from sync contexts (tool threads). Schedules publish on the loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Called from a non-async context: remember via history only if no loop.
            self._history.append(event)
            return
        loop.create_task(self.publish(event))

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        for ev in list(self._history):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                break
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def recent(self, limit: int = 100) -> list[AgentEvent]:
        return list(self._history)[-limit:]


event_bus = EventBus()

Listener = Callable[[AgentEvent], None]
_listeners: list[Listener] = []


def add_listener(fn: Listener) -> None:
    _listeners.append(fn)


def notify_listeners(event: AgentEvent) -> None:
    for fn in _listeners:
        try:
            fn(event)
        except Exception:  # noqa: BLE001 - listener errors must not break the bus
            log.exception("event listener failed")
