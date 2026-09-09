"""Risk classification.

Default levels come from tool registry specs; this module refines them with
argument-aware heuristics (e.g. typing long text into an unknown window,
terminal command content) so dangerous variants of a low-risk tool can be
escalated. Classification never lowers a registry-declared risk.
"""
from __future__ import annotations

from typing import Any

from backend.models.schemas import RiskLevel
from backend.tools.base import ToolRegistry

# Argument heuristics: (tool name, predicate) -> minimum risk
_TEXT_COMMAND_HINTS = (
    "rm ", "del ", "format ", "shutdown", "reg ", "remove-item",
)


def classify(tool_risk: RiskLevel, tool_name: str, args: dict[str, Any]) -> RiskLevel:
    """Return the final risk for a validated tool call (never below registry risk)."""
    risk = tool_risk
    order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]

    if tool_name == "terminal.execute":
        cmd = str(args.get("command", "")).lower()
        if any(h in cmd for h in _TEXT_COMMAND_HINTS):
            return RiskLevel.CRITICAL
        return RiskLevel.HIGH

    if tool_name in ("window.close",):
        return RiskLevel.HIGH

    if tool_name == "keyboard.type":
        text = str(args.get("text", ""))
        lowered = text.lower()
        # Typing that looks like a command into a terminal is high risk.
        if any(h in lowered for h in _TEXT_COMMAND_HINTS):
            return RiskLevel.HIGH
        if len(text) > 500:
            return RiskLevel.MEDIUM

    if tool_name == "mouse.drag":
        return max_safe(order, risk, RiskLevel.MEDIUM)

    return risk


def max_safe(order: list[RiskLevel], *levels: RiskLevel) -> RiskLevel:
    idx = max(order.index(l) for l in levels)
    return order[idx]


def requires_permission(risk: RiskLevel, mode: str) -> bool:
    """Policy: decide if a permission prompt is needed.

    Modes (backend.config.PermissionMode):
    - confirm_risky: LOW auto, MEDIUM/HIGH/CRITICAL prompt
    - allow_all:     everything auto (explicit user opt-in, visible in UI)
    - strict:        everything prompts
    """
    if mode == "allow_all":
        return False
    if mode == "strict":
        return True
    # confirm_risky
    return risk != RiskLevel.LOW


def permission_rationale(risk: RiskLevel, mode: str) -> str:
    if mode == "allow_all":
        return "auto-approved (allow-all mode enabled by user)"
    if mode == "strict":
        return "requires approval (strict mode)"
    return "auto-approved (low risk)" if risk == RiskLevel.LOW else "requires approval (risky action)"
