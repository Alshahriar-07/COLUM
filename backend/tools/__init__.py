"""COLUM tool system — adapters + registry population."""
from backend.tools.base import (
    BaseTool,
    ExecutionContext,
    ToolCancelledError,
    ToolError,
    ToolRegistry,
    ToolSpec,
    registry,
)
from backend.tools.kill_switch_ref import kill_state


def register_tools() -> None:
    """Populate the global registry with every adapter. Idempotent."""
    if registry.specs():
        return
    from backend.tools.extraction_tools import register_extraction_tools
    from backend.tools.playwright_tool import register_playwright_tools
    from backend.tools.pyautogui_tool import register_pyautogui_tools
    from backend.tools.pywinauto_tool import register_pywinauto_tools
    from backend.tools.terminal_tool import register_terminal_tools

    register_pyautogui_tools(registry)
    register_playwright_tools(registry)
    register_terminal_tools(registry)
    register_extraction_tools(registry)
    register_pywinauto_tools(registry)


__all__ = [
    "BaseTool", "ExecutionContext", "ToolCancelledError", "ToolError",
    "ToolRegistry", "ToolSpec", "registry", "register_tools", "kill_state",
]
