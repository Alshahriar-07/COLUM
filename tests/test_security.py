"""Security layer tests: validator gate, risk classification, permission flow."""
from __future__ import annotations

import asyncio

import pytest

from backend.models.schemas import RiskLevel, ToolCall
from backend.security.risk import classify, requires_permission
from backend.security.validator import ValidationError, validate_tool_call
from backend.tools import registry, register_tools


@pytest.fixture(scope="module", autouse=True)
def _tools():
    register_tools()
    return registry


# ---------------------------------------------------------------------------
# Validator gate — the AI → tool boundary
# ---------------------------------------------------------------------------

def test_unknown_tool_rejected(_tools):
    call = ToolCall(tool="definitely.not_a_tool", args={})
    with pytest.raises(ValidationError):
        validate_tool_call(call, registry)


def test_valid_low_risk_call_accepted(_tools):
    call = ToolCall(tool="browser.state", args={})
    spec, args = validate_tool_call(call, registry)
    assert spec.name == "browser.state"
    assert args == {}


def test_unknown_argument_rejected(_tools):
    call = ToolCall(tool="mouse.click", args={"x": 10, "y": 10, "evil": "x"})
    with pytest.raises(ValidationError):
        validate_tool_call(call, registry)


def test_missing_required_arg_rejected(_tools):
    call = ToolCall(tool="browser.navigate", args={})
    with pytest.raises(ValidationError):
        validate_tool_call(call, registry)


def test_wrong_type_rejected(_tools):
    call = ToolCall(tool="mouse.click", args={"x": "left", "y": 10})
    with pytest.raises(ValidationError):
        validate_tool_call(call, registry)


def test_oversized_string_rejected(_tools):
    call = ToolCall(tool="keyboard.type", args={"text": "A" * 30000})
    with pytest.raises(ValidationError):
        validate_tool_call(call, registry)


def test_nested_nonsense_rejected(_tools):
    call = ToolCall(tool="browser.fill_form", args={"fields": [{"a": {"b": {"c": {"d": {"e": 1}}}}}]})
    with pytest.raises(ValidationError):
        validate_tool_call(call, registry)


def test_pdf_path_traversal_rejected(_tools):
    call = ToolCall(tool="pdf.extract", args={"path": "../../../etc/passwd.pdf"})
    with pytest.raises(ValidationError):
        validate_tool_call(call, registry)


def test_pdf_bad_suffix_rejected(_tools):
    call = ToolCall(tool="pdf.extract", args={"path": "C:/windows/system32/config.sys"})
    with pytest.raises(ValidationError):
        validate_tool_call(call, registry)


# ---------------------------------------------------------------------------
# Risk classification — escalation heuristics
# ---------------------------------------------------------------------------

def test_terminal_always_high(_tools):
    assert classify(RiskLevel.LOW, "terminal.execute", {"command": "dir"}) \
        == RiskLevel.HIGH


def test_terminal_destructive_becomes_critical(_tools):
    assert classify(RiskLevel.LOW, "terminal.execute",
                    {"command": "echo && del *.*"}) == RiskLevel.CRITICAL


def test_keyboard_type_with_destructive_text_escalates(_tools):
    assert classify(RiskLevel.LOW, "keyboard.type",
                    {"text": "please run del something"}) == RiskLevel.HIGH


def test_long_typing_escalates_to_medium(_tools):
    assert classify(RiskLevel.LOW, "keyboard.type",
                    {"text": "x" * 501}) == RiskLevel.MEDIUM


def test_window_close_is_high(_tools):
    assert classify(RiskLevel.LOW, "window.close", {"title": "x"}) == RiskLevel.HIGH


def test_registry_risk_never_lowered(_tools):
    # mouse.drag is declared MEDIUM; classify must not lower it.
    assert classify(RiskLevel.HIGH, "mouse.drag", {}) == RiskLevel.HIGH


# ---------------------------------------------------------------------------
# Permission policy
# ---------------------------------------------------------------------------

def test_confirm_risky_policy():
    assert requires_permission(RiskLevel.LOW, "confirm_risky") is False
    assert requires_permission(RiskLevel.MEDIUM, "confirm_risky") is True
    assert requires_permission(RiskLevel.HIGH, "confirm_risky") is True
    assert requires_permission(RiskLevel.CRITICAL, "confirm_risky") is True


def test_allow_all_policy():
    for r in RiskLevel:
        assert requires_permission(r, "allow_all") is False


def test_strict_policy():
    for r in RiskLevel:
        assert requires_permission(r, "strict") is True


# ---------------------------------------------------------------------------
# Permission manager flow
# ---------------------------------------------------------------------------

def test_permission_request_and_resolution():
    from backend.security.permissions import PermissionManager
    from backend.models.schemas import PermissionDecision

    async def scenario():
        pm = PermissionManager()
        req = await pm.request(tool="mouse.click", description="d", risk=RiskLevel.MEDIUM,
                               args_summary="x=1", session_id="s", plan_id="p", step_id="st")
        task = asyncio.ensure_future(pm.wait_decision(req.request_id, timeout=2))
        await asyncio.sleep(0.01)
        pm.resolve(req.request_id, True)
        decision = await task
        assert decision == PermissionDecision.APPROVED
        assert pm.pending_list() == []

    asyncio.new_event_loop().run_until_complete(scenario())


def test_permission_cancel_all():
    from backend.security.permissions import PermissionError_, PermissionManager

    async def scenario():
        pm = PermissionManager()
        req = await pm.request(tool="terminal.execute", description="d",
                               risk=RiskLevel.HIGH, args_summary="")
        task = asyncio.ensure_future(pm.wait_decision(req.request_id, timeout=5))
        await asyncio.sleep(0.01)
        await pm.cancel_all(reason="kill switch")
        with pytest.raises(PermissionError_):
            await task
        assert pm.pending_list() == []

    asyncio.new_event_loop().run_until_complete(scenario())
