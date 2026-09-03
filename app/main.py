"""COLUM main application entry point."""

import asyncio
import signal
import sys
from pathlib import Path

from app.config.loader import get_config
from app.core.lifecycle import LifecycleManager, set_lifecycle_manager
from app.core.server import get_server
from app.utils.logging import setup_logging, get_logger


logger = get_logger("main")


class COLUMApplication:
    """Main COLUM application."""

    def __init__(self):
        self._config = get_config()
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def initialize(self) -> None:
        """Initialize the application."""
        self._setup_logging()
        logger.info("COLUM initializing", version="Beta 1.0")

        self._log_config_summary()

    def _setup_logging(self) -> None:
        log_config = self._config.get_section("logging")
        setup_logging(
            level=log_config.get("level", "INFO"),
            log_file=log_config.get("file"),
            max_file_size_mb=log_config.get("max_file_size_mb", 10),
            backup_count=log_config.get("backup_count", 5),
            format_type=log_config.get("format", "json"),
            console_output=log_config.get("console_output", True),
        )

    def _log_config_summary(self) -> None:
        logger.info(
            "Configuration loaded",
            assistant_name=self._config.get("assistant", "name"),
            wake_word=self._config.get("assistant", "wake_word"),
            openrouter_mode=self._config.get("openrouter", "mode"),
            voice_stt=self._config.get("voice", "stt_provider"),
            voice_tts=self._config.get("voice", "tts_provider"),
        )

    async def start(self) -> None:
        """Start the application."""
        self._running = True
        logger.info("COLUM starting")

        from app.core.event_bus import get_event_bus, Events

        self._lifecycle = LifecycleManager(self._config)
        set_lifecycle_manager(self._lifecycle)

        server = get_server(self._config.get_section("server"))
        self._lifecycle.register(ServerComponent(server))

        await self._lifecycle.start()

        event_bus = get_event_bus()
        await event_bus.publish(Event(type=Events.SYSTEM_STARTUP, source="main"))

        await server.start()

        self._setup_signal_handlers()

        logger.info("COLUM started successfully")

    async def stop(self) -> None:
        """Stop the application."""
        if not self._running:
            return

        logger.info("COLUM stopping")
        self._running = False

        from app.core.event_bus import get_event_bus, Events

        event_bus = get_event_bus()
        await event_bus.publish(Event(type=Events.SYSTEM_SHUTDOWN, source="main"))

        if hasattr(self, "_lifecycle"):
            await self._lifecycle.stop()

        self._shutdown_event.set()
        logger.info("COLUM stopped")

    def _setup_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                pass

    async def run(self) -> None:
        """Run the application until shutdown."""
        await self.initialize()
        await self.start()
        await self._shutdown_event.wait()
        await self.stop()


class ServerComponent:
    """Wrapper for server as a lifecycle component."""

    def __init__(self, server):
        self._server = server
        self.name = "server"

    async def _do_start(self) -> None:
        pass

    async def _do_stop(self) -> None:
        await self._server.stop()

    @property
    def is_started(self) -> bool:
        return True


async def main() -> int:
    """Main entry point."""
    app = COLUMApplication()
    try:
        await app.run()
        return 0
    except Exception as e:
        logger.exception("Fatal error", error=str(e))
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))