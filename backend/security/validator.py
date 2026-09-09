"""Action validation — the gate between AI plans and tool execution.

A `PlanStep`/`ToolCall` must pass `validate_tool_call` before the registry ever
runs it. Validation covers: tool allowlist (registry existence), argument
schema, required args, coordinate bounds, string size limits, and path safety
for extraction tools. Every rejection is audit-logged.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.logging_utils import get_logger, log_json
from backend.models.schemas import RiskLevel, ToolCall
from backend.tools.base import ToolRegistry, ToolSpec
from backend.tools.kill_switch_ref import kill_state

log = get_logger("security.validator")

MAX_STR_ARG = 20000
MAX_LIST_LEN = 100
MAX_DICT_KEYS = 50


class ValidationError(Exception):
    def __init__(self, reason: str, audit: bool = True) -> None:
        super().__init__(reason)
        self.reason = reason
        self.audit = audit


def audit_log(event: str, **fields: Any) -> None:
    """Structured security audit log (data/logs/audit/ is handled by log file)."""
    log_json(log, 20, f"audit_{event}", **fields)


def validate_tool_call(call: ToolCall, reg: ToolRegistry) -> tuple[ToolSpec, dict[str, Any]]:
    """Validate a tool call against the registry. Returns (spec, clean_args).

    Raises ValidationError with a safe message on any violation.
    """
    if kill_state.is_cancelled():
        raise ValidationError("execution is stopped (kill switch active)", audit=False)

    # 1) Allowlist: the tool must exist in the registry.
    if not reg.exists(call.tool):
        audit_log("reject", reason="unknown_tool", tool=call.tool)
        raise ValidationError(f"tool '{call.tool}' is not in the allowlist")

    spec = reg.get(call.tool).spec

    # 2) Args must be a dict of str -> JSON value.
    args = call.args
    if not isinstance(args, dict):
        audit_log("reject", reason="args_not_dict", tool=call.tool)
        raise ValidationError("tool arguments must be an object")
    if len(args) > MAX_DICT_KEYS:
        audit_log("reject", reason="too_many_args", tool=call.tool)
        raise ValidationError("too many arguments")

    # 3) Size/type sanity for every value (deep traversal).
    try:
        _check_value(args, 0)
    except ValidationError as exc:
        audit_log("reject", reason="bad_arg", tool=call.tool, detail=exc.reason)
        raise

    # 4) Registry-level schema validation (types + required args + unknown args).
    tool = reg.get(call.tool)
    try:
        tool.validate_args(args)
    except Exception as exc:  # ToolError
        audit_log("reject", reason="schema", tool=call.tool, detail=str(exc))
        raise ValidationError(str(exc))

    # 5) Tool-specific safety checks.
    if call.tool.startswith("mouse.") and ("x" in args or "y" in args):
        _validate_coordinates(args, spec)
    if call.tool == "mouse.drag":
        _validate_coordinates({"x": args.get("from_x"), "y": args.get("from_y")}, spec)
        _validate_coordinates({"x": args.get("to_x"), "y": args.get("to_y")}, spec)
    if call.tool == "pdf.extract":
        _validate_pdf_path(args.get("path"))

    audit_log("accept", tool=call.tool, risk=spec.risk.value,
              session_id=call.session_id, plan_id=call.plan_id, step_id=call.step_id)
    return spec, args


def _check_value(v: Any, depth: int) -> None:
    if depth > 4:
        raise ValidationError("argument nesting too deep")
    if isinstance(v, str):
        if len(v) > MAX_STR_ARG:
            raise ValidationError("string argument too long")
    elif isinstance(v, bool) or isinstance(v, int) or isinstance(v, float):
        return
    elif isinstance(v, list):
        if len(v) > MAX_LIST_LEN:
            raise ValidationError("list argument too long")
        for item in v:
            _check_value(item, depth + 1)
    elif isinstance(v, dict):
        if len(v) > MAX_DICT_KEYS:
            raise ValidationError("object argument too large")
        for k, item in v.items():
            if not isinstance(k, str):
                raise ValidationError("object keys must be strings")
            _check_value(item, depth + 1)
    elif v is None:
        return
    else:
        raise ValidationError(f"unsupported argument type: {type(v).__name__}")


def _screen_size() -> tuple[int, int] | None:
    try:
        import mss
        with mss.mss() as sct:
            m = sct.monitors[1]
            return int(m["width"]), int(m["height"])
    except Exception:
        try:
            import pyautogui
            size = pyautogui.size()
            return int(size.width), int(size.height)
        except Exception:
            return None


def _validate_coordinates(args: dict[str, Any], spec: ToolSpec) -> None:
    x, y = args.get("x"), args.get("y")
    if not isinstance(x, int) or not isinstance(y, int):
        raise ValidationError("coordinates must be integers")
    size = _screen_size()
    if size is None:
        raise ValidationError("screen size unavailable; cannot validate coordinates")
    sw, sh = size
    if not (-8 <= x <= sw + 8 and -8 <= y <= sh + 8):
        audit_log("reject", reason="coordinates_out_of_bounds",
                  tool=spec.name, x=x, y=y, screen=[sw, sh])
        raise ValidationError(
            f"coordinates ({x}, {y}) are outside the screen ({sw}x{sh})"
        )


def _validate_pdf_path(raw: Any) -> None:
    if not isinstance(raw, str) or not raw.strip():
        raise ValidationError("pdf path must be a non-empty string")
    raw_path = raw.strip()
    # Traversal check on the RAW path first: resolve() collapses '..' segments,
    # so checking afterwards would never see them.
    if ".." in Path(raw_path).parts:
        audit_log("reject", reason="pdf_path_traversal", path=raw_path[:200])
        raise ValidationError("path traversal is not allowed")
    p = Path(raw_path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    p = p.resolve()
    if p.suffix.lower() != ".pdf":
        audit_log("reject", reason="pdf_bad_suffix", path=str(p))
        raise ValidationError("file must have a .pdf extension")
    # Existence is checked at execution; here we only block obvious traversal.
