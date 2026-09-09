"""Tool system base: tool spec, base class, execution context, registry.

Every tool declares name/description/input schema/risk/timeout. The registry is
the ONLY bridge between AI planning and execution: a `ToolCall` is validated
against registry specs by the security layer before `run` is ever invoked.
"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.logging_utils import get_logger, log_json
from backend.models.schemas import RiskLevel, ToolCall, ToolResult
from backend.tools.kill_switch_ref import kill_state

log = get_logger("tools")


@dataclass
class ToolSpec:
    name: str                       # dotted name, e.g. "mouse.click"
    description: str
    risk: RiskLevel
    args_schema: dict[str, str]     # arg name -> type name (str|int|float|bool|list|dict)
    required: tuple[str, ...] = ()
    timeout_s: float = 30.0
    category: str = "general"

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk.value,
            "args_schema": dict(self.args_schema),
            "required": list(self.required),
            "timeout_s": self.timeout_s,
            "category": self.category,
        }


@dataclass
class ExecutionContext:
    session_id: str = ""
    plan_id: str = ""
    step_id: str = ""
    cancelled: "asyncio.Event | None" = None

    def raise_if_cancelled(self) -> None:
        if self.cancelled is not None and self.cancelled.is_set():
            raise ToolCancelledError("execution cancelled by kill switch or user")
        # Defense-in-depth: also honor the global kill flag. The captured
        # event can be stale/unbound (loop rebinding, out-of-orchestrator use);
        # the flag is always authoritative.
        if kill_state.is_cancelled():
            raise ToolCancelledError("execution cancelled by kill switch or user")


class ToolError(Exception):
    pass


class ToolCancelledError(ToolError):
    """Raised when a kill switch / user stop interrupted execution."""


class BaseTool(ABC):
    spec: ToolSpec

    @abstractmethod
    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        """Execute the tool with pre-validated args."""

    def validate_args(self, args: dict[str, Any]) -> None:
        """Structural validation against the spec; raises ToolError on violation."""
        allowed = set(self.spec.args_schema)
        for k in args:
            if k not in allowed:
                raise ToolError(f"{self.spec.name}: unknown argument '{k}'")
        for req in self.spec.required:
            if req not in args:
                raise ToolError(f"{self.spec.name}: missing required argument '{req}'")
        type_map = {"str": str, "int": int, "float": (int, float), "bool": bool, "list": list, "dict": dict}
        for k, v in args.items():
            expected = self.spec.args_schema.get(k)
            py = type_map.get(expected)
            if py is None:
                continue
            if expected == "float" and isinstance(v, bool):
                raise ToolError(f"{self.spec.name}: argument '{k}' must be {expected}")
            if not isinstance(v, py):
                raise ToolError(f"{self.spec.name}: argument '{k}' must be {expected}, got {type(v).__name__}")


class ToolRegistry:
    """Central registry. `register_tools()` in `__init__` populates all adapters."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.spec.name in self._tools:
            raise ToolError(f"tool '{tool.spec.name}' registered twice")
        self._tools[tool.spec.name] = tool

    def get(self, name: str) -> BaseTool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"unknown tool '{name}'")
        return tool

    def exists(self, name: str) -> bool:
        return name in self._tools

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def describe_all(self) -> list[dict[str, Any]]:
        return [t.spec.describe() for t in self._tools.values()]

    async def execute(self, call: ToolCall, ctx: ExecutionContext) -> ToolResult:
        """Validate + run with timeout, cancellation checks, and full logging."""
        started = time.monotonic()
        try:
            tool = self.get(call.tool)
        except ToolError as exc:
            return ToolResult(call_id=call.call_id, tool=call.tool, ok=False,
                              error=str(exc), duration_ms=0)
        try:
            tool.validate_args(call.args)
            ctx.raise_if_cancelled()
        except ToolError as exc:
            return ToolResult(call_id=call.call_id, tool=call.tool, ok=False,
                              error=str(exc), duration_ms=0)

        log_json(log, 20, "tool_start", tool=call.tool,
                 risk=tool.spec.risk.value, plan_id=call.plan_id, step_id=call.step_id)
        try:
            timeout = max(1.0, float(tool.spec.timeout_s))
            data = await asyncio.wait_for(tool.run(call.args, ctx), timeout=timeout)
            duration_ms = int((time.monotonic() - started) * 1000)
            if not isinstance(data, dict):
                data = {"result": data}
            log_json(log, 20, "tool_done", tool=call.tool, ok=True, duration_ms=duration_ms)
            return ToolResult(call_id=call.call_id, tool=call.tool, ok=True,
                              data=data, duration_ms=duration_ms)
        except ToolCancelledError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            log_json(log, 30, "tool_cancelled", tool=call.tool, duration_ms=duration_ms)
            return ToolResult(call_id=call.call_id, tool=call.tool, ok=False,
                              error=str(exc), duration_ms=duration_ms,
                              data={"cancelled": True})
        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - started) * 1000)
            timeout = spec_timeout(tool)
            log_json(log, 30, "tool_timeout", tool=call.tool, timeout_s=timeout)
            return ToolResult(call_id=call.call_id, tool=call.tool, ok=False,
                              error=f"tool '{call.tool}' timed out after {timeout}s",
                              duration_ms=duration_ms)
        except Exception as exc:  # noqa: BLE001 - tool adapter boundary
            duration_ms = int((time.monotonic() - started) * 1000)
            log_json(log, 30, "tool_error", tool=call.tool, error=type(exc).__name__)
            return ToolResult(call_id=call.call_id, tool=call.tool, ok=False,
                              error=f"{type(exc).__name__}: {exc}", duration_ms=duration_ms)


def spec_timeout(tool: BaseTool) -> float:
    return max(1.0, float(tool.spec.timeout_s))


registry = ToolRegistry()
