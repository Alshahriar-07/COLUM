"""PyAutoGUI adapter — validated desktop automation.

All blocking pyautogui calls run in worker threads. Coordinates are validated
against the actual screen size; out-of-bounds targets are rejected. PyAutoGUI
FAILSAFE (slam mouse to a screen corner) stays enabled as an independent
emergency stop. Every action checks the kill switch before and after.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from backend.events import event_bus
from backend.logging_utils import get_logger, log_json
from backend.models.schemas import AgentEvent, RiskLevel
from backend.tools.base import BaseTool, ExecutionContext, ToolError
from backend.tools.kill_switch_ref import kill_state

log = get_logger("tools.pyautogui")

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    PYAUTOGUI_AVAILABLE = True
except Exception:  # pragma: no cover - headless/no-display environments
    pyautogui = None
    PYAUTOGUI_AVAILABLE = False

MAX_TEXT_LEN = 2000
KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_+\-]+$")
_VALID_SPECIAL = {
    "shift", "ctrl", "alt", "win", "enter", "esc", "escape", "tab", "space",
    "backspace", "delete", "home", "end", "pageup", "pagedown", "up", "down",
    "left", "right", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9",
    "f10", "f11", "f12", "insert", "printscreen", "capslock", "numlock",
}


class _PyAutoToolBase(BaseTool):
    def _pre(self, ctx: ExecutionContext) -> None:
        if not PYAUTOGUI_AVAILABLE:
            raise ToolError("pyautogui is unavailable in this environment")
        ctx.raise_if_cancelled()
        if kill_state.is_cancelled():
            ctx.raise_if_cancelled()

    @staticmethod
    def _validate_xy(x: Any, y: Any) -> tuple[int, int]:
        try:
            xi, yi = int(x), int(y)
        except (TypeError, ValueError) as exc:
            raise ToolError(f"coordinates must be integers, got ({x!r}, {y!r})") from exc
        if not PYAUTOGUI_AVAILABLE:
            return xi, yi
        sw, sh = pyautogui.size()
        # Small tolerance for multi-monitor edge coordinates.
        if not (-8 <= xi <= sw + 8 and -8 <= yi <= sh + 8):
            raise ToolError(
                f"coordinates ({xi}, {yi}) are outside the screen ({sw}x{sh})"
            )
        return xi, yi

    async def _run_blocking(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def _emit(self, event: str, data: dict[str, Any]) -> None:
        await event_bus.publish(AgentEvent(event=event, data=data))


class MouseMoveTool(_PyAutoToolBase):
    def __init__(self) -> None:
        from backend.tools.base import ToolSpec
        self.spec = ToolSpec(
            name="mouse.move", description="Move the mouse cursor to (x, y).",
            risk=RiskLevel.LOW, args_schema={"x": "int", "y": "int",
                                             "duration": "float"},
            required=("x", "y"), timeout_s=10.0, category="desktop",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        x, y = self._validate_xy(args["x"], args["y"])
        duration = min(max(float(args.get("duration", 0.2)), 0.0), 3.0)
        await self._run_blocking(pyautogui.moveTo, x, y, duration=duration)
        ctx.raise_if_cancelled()
        pos = await self._run_blocking(pyautogui.position)
        await self._emit("tool_event", {"tool": "mouse.move", "x": x, "y": y})
        return {"moved_to": [pos.x, pos.y]}


class MouseClickTool(_PyAutoToolBase):
    def __init__(self, variant: str) -> None:
        from backend.tools.base import ToolSpec
        names = {
            "click": ("mouse.click", "Click the left mouse button at (x, y).", 1, "left"),
            "double_click": ("mouse.double_click", "Double-click at (x, y).", 2, "left"),
            "right_click": ("mouse.right_click", "Right-click at (x, y).", 1, "right"),
        }
        self.variant = variant
        name, desc, clicks, button = names[variant]
        self._clicks, self._button = clicks, button
        self.spec = ToolSpec(
            name=name, description=desc, risk=RiskLevel.LOW,
            args_schema={"x": "int", "y": "int"}, required=("x", "y"),
            timeout_s=10.0, category="desktop",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        x, y = self._validate_xy(args["x"], args["y"])
        await self._run_blocking(
            pyautogui.click, x, y, clicks=self._clicks, button=self._button,
            interval=0.08 if self._clicks > 1 else 0,
        )
        ctx.raise_if_cancelled()
        await self._emit("tool_event", {"tool": self.spec.name, "x": x, "y": y,
                                        "button": self._button})
        return {"clicked": [x, y], "button": self._button,
                "clicks": self._clicks}


class MouseScrollTool(_PyAutoToolBase):
    def __init__(self) -> None:
        from backend.tools.base import ToolSpec
        self.spec = ToolSpec(
            name="mouse.scroll",
            description="Scroll the mouse wheel. Positive amount scrolls up.",
            risk=RiskLevel.LOW, args_schema={"amount": "int", "x": "int", "y": "int"},
            required=("amount",), timeout_s=10.0, category="desktop",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        amount = int(args["amount"])
        if amount == 0:
            raise ToolError("scroll amount must be non-zero")
        amount = max(-3000, min(3000, amount))
        if "x" in args and "y" in args:
            x, y = self._validate_xy(args["x"], args["y"])
            await self._run_blocking(pyautogui.scroll, amount, x=x, y=y)
            pos = [x, y]
        else:
            await self._run_blocking(pyautogui.scroll, amount)
            pos = await self._run_blocking(pyautogui.position)
            pos = [pos.x, pos.y]
        ctx.raise_if_cancelled()
        await self._emit("tool_event", {"tool": "mouse.scroll", "amount": amount})
        return {"scrolled": amount, "at": pos}


class MouseDragTool(_PyAutoToolBase):
    def __init__(self) -> None:
        from backend.tools.base import ToolSpec
        self.spec = ToolSpec(
            name="mouse.drag",
            description="Drag from (from_x, from_y) to (to_x, to_y) with the left button.",
            risk=RiskLevel.MEDIUM,
            args_schema={"from_x": "int", "from_y": "int", "to_x": "int", "to_y": "int",
                         "duration": "float"},
            required=("from_x", "from_y", "to_x", "to_y"), timeout_s=20.0,
            category="desktop",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        fx, fy = self._validate_xy(args["from_x"], args["from_y"])
        tx, ty = self._validate_xy(args["to_x"], args["to_y"])
        duration = min(max(float(args.get("duration", 0.5)), 0.1), 5.0)
        await self._run_blocking(pyautogui.moveTo, fx, fy, duration=0.15)
        ctx.raise_if_cancelled()
        await self._run_blocking(pyautogui.dragTo, tx, ty, duration=duration, button="left")
        ctx.raise_if_cancelled()
        await self._emit("tool_event", {"tool": "mouse.drag", "from": [fx, fy], "to": [tx, ty]})
        return {"dragged_from": [fx, fy], "dragged_to": [tx, ty]}


class KeyboardTypeTool(_PyAutoToolBase):
    def __init__(self) -> None:
        from backend.tools.base import ToolSpec
        self.spec = ToolSpec(
            name="keyboard.type", description="Type text into the focused window.",
            risk=RiskLevel.MEDIUM, args_schema={"text": "str", "interval": "float"},
            required=("text",), timeout_s=60.0, category="desktop",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        text = str(args["text"])
        if not text:
            raise ToolError("text must be non-empty")
        if len(text) > MAX_TEXT_LEN:
            raise ToolError(f"text exceeds maximum length of {MAX_TEXT_LEN} characters")
        interval = min(max(float(args.get("interval", 0.02)), 0.0), 0.5)
        await self._run_blocking(pyautogui.typewrite, text, interval=interval)
        ctx.raise_if_cancelled()
        await self._emit("tool_event", {"tool": "keyboard.type", "length": len(text)})
        return {"typed_chars": len(text)}


class KeyboardPressTool(_PyAutoToolBase):
    def __init__(self) -> None:
        from backend.tools.base import ToolSpec
        self.spec = ToolSpec(
            name="keyboard.press", description="Press a single key (e.g. 'enter').",
            risk=RiskLevel.MEDIUM, args_schema={"key": "str", "presses": "int"},
            required=("key",), timeout_s=15.0, category="desktop",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        key = _validate_key(args["key"])
        presses = max(1, min(int(args.get("presses", 1)), 20))
        await self._run_blocking(pyautogui.press, key, presses=presses, interval=0.08)
        ctx.raise_if_cancelled()
        await self._emit("tool_event", {"tool": "keyboard.press", "key": key})
        return {"pressed": key, "presses": presses}


class KeyboardHotkeyTool(_PyAutoToolBase):
    def __init__(self) -> None:
        from backend.tools.base import ToolSpec
        self.spec = ToolSpec(
            name="keyboard.hotkey",
            description="Press a key combination, e.g. keys ['ctrl','s'].",
            risk=RiskLevel.MEDIUM, args_schema={"keys": "list"}, required=("keys",),
            timeout_s=15.0, category="desktop",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        keys = args.get("keys")
        if not isinstance(keys, list) or not 1 <= len(keys) <= 4:
            raise ToolError("keys must be a list of 1-4 key names")
        validated = [_validate_key(k) for k in keys]
        await self._run_blocking(pyautogui.hotkey, *validated)
        ctx.raise_if_cancelled()
        combo = "+".join(validated)
        await self._emit("tool_event", {"tool": "keyboard.hotkey", "keys": combo})
        return {"hotkey": combo}


def _validate_key(key: Any) -> str:
    if not isinstance(key, str):
        raise ToolError("key names must be strings")
    k = key.strip().lower()
    if not KEY_PATTERN.match(k):
        raise ToolError(f"invalid key name: {key!r}")
    if k not in _VALID_SPECIAL and not k.isalnum():
        raise ToolError(f"key not in allowed set: {key!r}")
    return k


def register_pyautogui_tools(reg) -> None:
    reg.register(MouseMoveTool())
    reg.register(MouseClickTool("click"))
    reg.register(MouseClickTool("double_click"))
    reg.register(MouseClickTool("right_click"))
    reg.register(MouseScrollTool())
    reg.register(MouseDragTool())
    reg.register(KeyboardTypeTool())
    reg.register(KeyboardPressTool())
    reg.register(KeyboardHotkeyTool())
    log_json(log, 20, "pyautogui_tools_registered", count=9, available=PYAUTOGUI_AVAILABLE)
