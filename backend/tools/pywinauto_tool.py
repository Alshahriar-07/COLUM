"""PyWinAuto adapter — Windows native window management.

Windows-only. Wrapped defensively: import failure or non-Windows OS disables
the tools with an honest error, never a crash.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any

from backend.events import event_bus
from backend.logging_utils import get_logger, log_json
from backend.models.schemas import AgentEvent, RiskLevel
from backend.tools.base import BaseTool, ExecutionContext, ToolError, ToolSpec
from backend.tools.kill_switch_ref import kill_state

log = get_logger("tools.pywinauto")

PYWINAUTO_AVAILABLE = False
if sys.platform == "win32":
    try:
        from pywinauto import Application, Desktop
        from pywinauto.findwindows import ElementNotFoundError
        PYWINAUTO_AVAILABLE = True
    except Exception:  # pragma: no cover
        PYWINAUTO_AVAILABLE = False


def _pre(ctx: ExecutionContext) -> None:
    ctx.raise_if_cancelled()
    if not PYWINAUTO_AVAILABLE:
        raise ToolError("pywinauto is unavailable (Windows-only dependency)")


class WindowListTool(BaseTool):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="window.list",
            description="List visible top-level windows with titles and handles.",
            risk=RiskLevel.LOW, args_schema={}, timeout_s=15.0, category="window",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        _pre(ctx)
        def _list():
            desktop = Desktop(backend="uia")
            windows = desktop.windows()
            out = []
            for w in windows:
                try:
                    if w.is_visible():
                        out.append({
                            "title": w.window_text()[:200],
                            "handle": int(w.handle),
                            "rect": [int(w.rectangle().left), int(w.rectangle().top),
                                     int(w.rectangle().width()), int(w.rectangle().height())],
                        })
                except Exception:
                    continue
            return out[:40]
        windows = await asyncio.to_thread(_list)
        ctx.raise_if_cancelled()
        await event_bus.publish(AgentEvent(event="tool_event",
                                           data={"tool": "window.list", "count": len(windows)}))
        return {"windows": windows, "count": len(windows)}


class WindowFocusTool(BaseTool):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="window.focus",
            description="Bring a window to the foreground by (partial) title match.",
            risk=RiskLevel.MEDIUM, args_schema={"title": "str"}, required=("title",),
            timeout_s=15.0, category="window",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        _pre(ctx)
        title = str(args["title"]).strip()
        if not title or len(title) > 200:
            raise ToolError("title must be a non-empty string (max 200 chars)")
        def _focus():
            desktop = Desktop(backend="uia")
            wins = [w for w in desktop.windows()
                    if title.lower() in (w.window_text() or "").lower()]
            if not wins:
                raise ToolError(f"no window matching {title!r}")
            w = wins[0]
            w.set_focus()
            return w.window_text()[:200]
        try:
            focused = await asyncio.to_thread(_focus)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(f"focus failed: {type(exc).__name__}")
        ctx.raise_if_cancelled()
        await event_bus.publish(AgentEvent(event="tool_event",
                                           data={"tool": "window.focus", "title": focused}))
        return {"focused": focused}


class WindowCloseTool(BaseTool):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="window.close",
            description="Close a top-level window by (partial) title match.",
            risk=RiskLevel.HIGH, args_schema={"title": "str"}, required=("title",),
            timeout_s=20.0, category="window",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        _pre(ctx)
        title = str(args["title"]).strip()
        if not title or len(title) > 200:
            raise ToolError("title must be a non-empty string (max 200 chars)")
        def _close():
            desktop = Desktop(backend="uia")
            wins = [w for w in desktop.windows()
                    if title.lower() in (w.window_text() or "").lower()]
            if not wins:
                raise ToolError(f"no window matching {title!r}")
            target = wins[0]
            name = target.window_text()[:200]
            target.close()
            return name
        try:
            closed = await asyncio.to_thread(_close)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(f"close failed: {type(exc).__name__}")
        ctx.raise_if_cancelled()
        log_json(log, 30, "window_closed", title=closed)
        return {"closed": closed}


def register_pywinauto_tools(reg) -> None:
    reg.register(WindowListTool())
    reg.register(WindowFocusTool())
    reg.register(WindowCloseTool())
    log_json(log, 20, "pywinauto_tools_registered", count=3,
             available=PYWINAUTO_AVAILABLE)
