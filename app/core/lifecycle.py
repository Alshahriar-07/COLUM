"""Lifecycle manager for COLUM components."""

import asyncio
from typing import Any, Dict, List, Optional

from app.config.loader import Config
from app.core.event_bus import EventBus, Events
from app.utils.logging import get_logger


logger = get_logger("lifecycle")


class Component:
    """Base class for lifecycle-managed components."""

    def __init__(self, name: str):
        self.name = name
        self._started = False

    async def start(self) -> None:
        """Start the component."""
        if self._started:
            return
        await self._do_start()
        self._started = True
        logger.info("Component started", component=self.name)

    async def stop(self) -> None:
        """Stop the component."""
        if not self._started:
            return
        await self._do_stop()
        self._started = False
        logger.info("Component stopped", component=self.name)

    async def _do_start(self) -> None:
        pass

    async def _do_stop(self) -> None:
        pass

    @property
    def is_started(self) -> bool:
        return self._started


class LifecycleManager:
    """Manages the lifecycle of all COLUM components."""

    def __init__(self, config: Config):
        self._config = config
        self._components: List[Component] = []
        self._event_bus: Optional[EventBus] = None
        self._tasks: List[asyncio.Task] = []

    @property
    def event_bus(self) -> EventBus:
        if self._event_bus is None:
            self._event_bus = EventBus()
        return self._event_bus

    def register(self, component: Component) -> None:
        """Register a component for lifecycle management."""
        self._components.append(component)
        logger.debug("Component registered", component=component.name)

    async def start(self) -> None:
        """Start all registered components."""
        logger.info("Starting lifecycle manager")

        for component in self._components:
            try:
                await component.start()
            except Exception as e:
                logger.error("Failed to start component", component=component.name, error=str(e))
                raise

        await self.event_bus.publish(Event(type=Events.SYSTEM_STARTUP, source="lifecycle"))

    async def stop(self) -> None:
        """Stop all registered components in reverse order."""
        logger.info("Stopping lifecycle manager")

        await self.event_bus.publish(Event(type=Events.SYSTEM_SHUTDOWN, source="lifecycle"))

        for component in reversed(self._components):
            try:
                await component.stop()
            except Exception as e:
                logger.error("Failed to stop component", component=component.name, error=str(e))

        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    def create_task(self, coro, name: str = "") -> asyncio.Task:
        """Create a managed background task."""
        task = asyncio.create_task(coro, name=name)
        self._tasks.append(task)
        return task

    def get_component(self, name: str) -> Optional[Component]:
        """Get a registered component by name."""
        for comp in self._components:
            if comp.name == name:
                return comp
        return None


_lifecycle_manager: Optional[LifecycleManager] = None


def get_lifecycle_manager() -> Optional[LifecycleManager]:
    return _lifecycle_manager


def set_lifecycle_manager(manager: LifecycleManager) -> None:
    global _lifecycle_manager
    _lifecycle_manager = manager