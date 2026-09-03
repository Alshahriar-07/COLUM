"""HTTP and WebSocket server for frontend-backend communication."""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional, Set

from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import Response

from app.config.loader import get_config
from app.core.event_bus import get_event_bus, Events
from app.utils.logging import get_logger


logger = get_logger("server")


class COLUMServer(web.Application):
    """HTTP and WebSocket server for COLUM."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__()
        self._config = config or get_config().get_section("server")
        self._host = self._config.get("host", "127.0.0.1")
        self._http_port = self._config.get("http_port", 8765)
        self._ws_port = self._config.get("ws_port", 8766)
        self._cors_origins = set(self._config.get("cors_origins", []))

        self._ws_clients: Set[web.WebSocketResponse] = set()
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

        self._setup_routes()
        self._setup_event_listeners()

    def _setup_routes(self) -> None:
        self.router.add_get("/health", self._health_check)
        self.router.add_get("/api/status", self._get_status)
        self.router.add_get("/api/config", self._get_config)
        self.router.add_post("/api/chat", self._chat)
        self.router.add_get("/ws", self._websocket_handler)

        frontend_path = Path(__file__).parent.parent.parent / "frontend"
        if frontend_path.exists():
            self.router.add_static("/", frontend_path, show_index=True)

    def _setup_event_listeners(self) -> None:
        event_bus = get_event_bus()

        async def on_assistant_state_changed(event):
            await self._broadcast({
                "type": "assistant_state",
                "data": event.data
            })

        async def on_message_received(event):
            await self._broadcast({
                "type": "message",
                "data": event.data
            })

        async def on_tool_call_started(event):
            await self._broadcast({
                "type": "tool_started",
                "data": event.data
            })

        async def on_tool_call_completed(event):
            await self._broadcast({
                "type": "tool_completed",
                "data": event.data
            })

        event_bus.subscribe(Events.ASSISTANT_STATE_CHANGED, on_assistant_state_changed)
        event_bus.subscribe(Events.UI_MESSAGE_RECEIVED, on_message_received)
        event_bus.subscribe(Events.TOOL_CALL_STARTED, on_tool_call_started)
        event_bus.subscribe(Events.TOOL_CALL_COMPLETED, on_tool_call_completed)

    async def _health_check(self, request: Request) -> Response:
        return web.json_response({"status": "ok", "service": "COLUM"})

    async def _get_status(self, request: Request) -> Response:
        from app.core.lifecycle import get_lifecycle_manager
        lifecycle = get_lifecycle_manager()
        return web.json_response({
            "status": "running",
            "components": [c.name for c in lifecycle._components if c.is_started],
        })

    async def _get_config(self, request: Request) -> Response:
        config = get_config().get_all()
        safe_config = {k: v for k, v in config.items() if k != "openrouter" or "api_key" not in str(v)}
        if "openrouter" in safe_config and isinstance(safe_config["openrouter"], dict):
            safe_config["openrouter"] = {k: v for k, v in safe_config["openrouter"].items() if k != "api_key"}
        return web.json_response(safe_config)

    async def _chat(self, request: Request) -> Response:
        try:
            data = await request.json()
            message = data.get("message", "")
            if not message:
                return web.json_response({"error": "Message required"}, status=400)

            event_bus = get_event_bus()
            await event_bus.publish(Event(
                type=Events.UI_MESSAGE_RECEIVED,
                data={"message": message, "source": "http"},
                source="server"
            ))

            return web.json_response({"status": "received"})
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

    async def _websocket_handler(self, request: Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self._ws_clients.add(ws)
        logger.info("WebSocket client connected", client_count=len(self._ws_clients))

        try:
            await self._broadcast({"type": "connected", "data": {}})
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_ws_message(msg.data)
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error("WebSocket error", error=ws.exception())
        finally:
            self._ws_clients.discard(ws)
            logger.info("WebSocket client disconnected", client_count=len(self._ws_clients))

        return ws

    async def _handle_ws_message(self, data: str) -> None:
        try:
            msg = json.loads(data)
            msg_type = msg.get("type")

            if msg_type == "chat":
                event_bus = get_event_bus()
                await event_bus.publish(Event(
                    type=Events.UI_MESSAGE_RECEIVED,
                    data={"message": msg.get("message", ""), "source": "ws"},
                    source="server"
                ))
            elif msg_type == "ping":
                await self._broadcast({"type": "pong", "data": {}})

        except json.JSONDecodeError:
            logger.warning("Invalid WebSocket message", data=data)

    async def _broadcast(self, message: Dict[str, Any]) -> None:
        if not self._ws_clients:
            return

        data = json.dumps(message)
        disconnected = set()

        for ws in self._ws_clients:
            try:
                await ws.send_str(data)
            except Exception:
                disconnected.add(ws)

        for ws in disconnected:
            self._ws_clients.discard(ws)

    async def start(self) -> None:
        self._runner = web.AppRunner(self)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self._host, self._http_port)
        await self._site.start()

        logger.info("HTTP server started", host=self._host, port=self._http_port)

    async def stop(self) -> None:
        for ws in self._ws_clients:
            await ws.close()

        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

        logger.info("Server stopped")


_server_instance: Optional[COLUMServer] = None


def get_server(config: Optional[Dict[str, Any]] = None) -> COLUMServer:
    global _server_instance
    if _server_instance is None:
        _server_instance = COLUMServer(config)
    return _server_instance