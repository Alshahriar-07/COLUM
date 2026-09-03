"""Event bus for inter-component communication."""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

from app.utils.logging import get_logger


logger = get_logger("event_bus")


@dataclass
class Event:
    """Event data structure."""
    type: str
    data: Any = None
    source: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_id: str = field(default_factory=lambda: str(uuid4()))


EventHandler = Callable[[Event], Any]


class EventBus:
    """Async event bus for decoupled component communication."""

    def __init__(self):
        self._handlers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._wildcard_handlers: List[EventHandler] = []
        self._history: List[Event] = []
        self._max_history = 1000
        self._running = False

    def subscribe(self, event_type: str, handler: EventHandler) -> str:
        """Subscribe to an event type. Returns subscription ID."""
        sub_id = str(uuid4())
        self._handlers[event_type].append(handler)
        logger.debug("Subscribed to event", event_type=event_type, subscription_id=sub_id)
        return sub_id

    def subscribe_wildcard(self, handler: EventHandler) -> str:
        """Subscribe to all events."""
        sub_id = str(uuid4())
        self._wildcard_handlers.append(handler)
        return sub_id

    def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        """Unsubscribe a handler from an event type."""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
                return True
            except ValueError:
                pass
        return False

    def unsubscribe_wildcard(self, handler: EventHandler) -> bool:
        """Unsubscribe a wildcard handler."""
        try:
            self._wildcard_handlers.remove(handler)
            return True
        except ValueError:
            return False

    async def publish(self, event: Event) -> None:
        """Publish an event to all subscribers."""
        self._add_to_history(event)

        handlers = self._handlers.get(event.type, [])
        all_handlers = handlers + self._wildcard_handlers

        if not all_handlers:
            return

        tasks = []
        for handler in all_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    tasks.append(handler(event))
                else:
                    handler(event)
            except Exception as e:
                logger.error("Handler error", event_type=event.type, error=str(e))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def publish_sync(self, event: Event) -> None:
        """Publish an event synchronously."""
        self._add_to_history(event)

        handlers = self._handlers.get(event.type, [])
        all_handlers = handlers + self._wildcard_handlers

        for handler in all_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.create_task(handler(event))
                else:
                    handler(event)
            except Exception as e:
                logger.error("Handler error", event_type=event.type, error=str(e))

    def _add_to_history(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_history(self, event_type: Optional[str] = None, limit: int = 100) -> List[Event]:
        """Get event history."""
        events = self._history
        if event_type:
            events = [e for e in events if e.type == event_type]
        return events[-limit:]

    def clear_history(self) -> None:
        self._history.clear()


_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


# Common event types
class Events:
    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"

    # Assistant lifecycle
    ASSISTANT_STATE_CHANGED = "assistant.state_changed"
    ASSISTANT_ACTIVATED = "assistant.activated"
    ASSISTANT_DEACTIVATED = "assistant.deactivated"

    # Voice events
    VOICE_WAKE_WORD_DETECTED = "voice.wake_word_detected"
    VOICE_LISTENING_STARTED = "voice.listening_started"
    VOICE_LISTENING_STOPPED = "voice.listening_stopped"
    VOICE_TRANSCRIPTION = "voice.transcription"
    VOICE_SPEAKING_STARTED = "voice.speaking_started"
    VOICE_SPEAKING_STOPPED = "voice.speaking_stopped"

    # AI events
    AI_REQUEST_STARTED = "ai.request_started"
    AI_REQUEST_COMPLETED = "ai.request_completed"
    AI_REQUEST_FAILED = "ai.request_failed"
    AI_STREAMING_CHUNK = "ai.streaming_chunk"

    # Tool events
    TOOL_CALL_REQUESTED = "tool.call_requested"
    TOOL_CALL_STARTED = "tool.call_started"
    TOOL_CALL_COMPLETED = "tool.call_completed"
    TOOL_CALL_FAILED = "tool.call_failed"

    # UI events
    UI_MESSAGE_RECEIVED = "ui.message_received"
    UI_MESSAGE_SENT = "ui.message_sent"
    UI_STATUS_CHANGED = "ui.status_changed"