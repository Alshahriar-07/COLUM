"""Tool system tests: registry integrity, argument validation, terminal policy."""
from __future__ import annotations

import pytest

from backend.models.schemas import RiskLevel
from backend.tools import registry, register_tools
from backend.tools.base import ToolError


@pytest.fixture(scope="module", autouse=True)
def _tools():
    register_tools()
    return registry


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = {
    # pyautogui
    "mouse.move", "mouse.click", "mouse.double_click", "mouse.right_click",
    "mouse.scroll", "mouse.drag", "keyboard.type", "keyboard.press",
    "keyboard.hotkey",
    # playwright
    "browser.open", "browser.navigate", "browser.extract", "browser.click",
    "browser.type", "browser.fill_form", "browser.state", "browser.close",
    # terminal
    "terminal.execute",
    # extraction
    "pdf.extract", "web.parse",
    # pywinauto
    "window.list", "window.focus", "window.close",
}


def test_all_expected_tools_registered(_tools):
    names = {s.name for s in registry.specs()}
    missing = EXPECTED_TOOLS - names
    assert not missing, f"missing tools: {missing}"


def test_no_duplicate_registration():
    with pytest.raises(ToolError):
        registry.register(registry.get("mouse.click"))


def test_every_spec_has_schema_and_timeout(_tools):
    for spec in registry.specs():
        assert spec.description, spec.name
        assert spec.timeout_s >= 1.0, spec.name
        assert spec.risk in RiskLevel
        for req in spec.required:
            assert req in spec.args_schema, f"{spec.name}: required {req} not in schema"


def test_risky_tools_declared_higher_risk(_tools):
    assert registry.get("terminal.execute").spec.risk == RiskLevel.HIGH
    assert registry.get("window.close").spec.risk == RiskLevel.HIGH
    assert registry.get("keyboard.type").spec.risk in (RiskLevel.MEDIUM,)


# ---------------------------------------------------------------------------
# Registry validation paths
# ---------------------------------------------------------------------------

def test_unknown_tool_raises(_tools):
    with pytest.raises(ToolError):
        registry.get("no.such_tool")


def test_validate_args_rejects_unknown(_tools):
    tool = registry.get("mouse.click")
    with pytest.raises(ToolError):
        tool.validate_args({"x": 1, "y": 2, "z": 3})


def test_validate_args_rejects_missing_required(_tools):
    tool = registry.get("mouse.click")
    with pytest.raises(ToolError):
        tool.validate_args({"x": 1})


def test_validate_args_rejects_wrong_type(_tools):
    tool = registry.get("mouse.click")
    with pytest.raises(ToolError):
        tool.validate_args({"x": "a", "y": 2})


def test_validate_args_accepts_valid(_tools):
    tool = registry.get("mouse.click")
    tool.validate_args({"x": 10, "y": 20})  # must not raise


# ---------------------------------------------------------------------------
# Terminal allowlist policy (string-level, no execution)
# ---------------------------------------------------------------------------

def test_terminal_blocks_destructive_heads():
    from backend.tools.terminal_tool import TerminalTool
    for head in ("format", "shutdown", "reg", "wmic", "taskkill"):
        with pytest.raises(ToolError):
            TerminalTool._validate(head, [head])


def test_terminal_blocks_unknown_head():
    from backend.tools.terminal_tool import TerminalTool
    with pytest.raises(ToolError):
        TerminalTool._validate("curl", ["curl", "http://evil.example"])


def test_terminal_allows_readonly_heads():
    from backend.tools.terminal_tool import TerminalTool
    TerminalTool._validate("dir", ["dir"])          # must not raise
    TerminalTool._validate("git", ["git", "status"])


def test_terminal_blocks_dangerous_arguments():
    from backend.tools.terminal_tool import TerminalTool
    with pytest.raises(ToolError):
        TerminalTool._validate("python", ["python", "-c", "import os", "-enc", "x"])
    with pytest.raises(ToolError):
        TerminalTool._validate("python", ["python", "script.py", "del"])


# ---------------------------------------------------------------------------
# Registry.execute error paths (no real tools run)
# ---------------------------------------------------------------------------

def test_execute_unknown_tool_returns_error_result():
    import asyncio
    from backend.models.schemas import ToolCall
    from backend.tools.base import ExecutionContext

    async def scenario():
        result = await registry.execute(
            ToolCall(tool="no.such_tool", args={}),
            ExecutionContext())
        assert result.ok is False
        assert "unknown tool" in (result.error or "").lower()

    asyncio.new_event_loop().run_until_complete(scenario())


def test_execute_schema_violation_returns_error_result():
    import asyncio
    from backend.models.schemas import ToolCall
    from backend.tools.base import ExecutionContext

    async def scenario():
        result = await registry.execute(
            ToolCall(tool="browser.navigate", args={}),  # missing url
            ExecutionContext())
        assert result.ok is False
        assert "required" in (result.error or "").lower()

    asyncio.new_event_loop().run_until_complete(scenario())
