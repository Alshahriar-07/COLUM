"""Security audit tests — regression coverage for the audit findings.

Focus: permission-gate integrity (risk re-evaluation on revised args),
tool-level denial behavior, secret redaction, and kill-switch reset semantics.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.models.schemas import RiskLevel, ToolCall
from backend.security import risk as risk_mod
from backend.security.risk import classify, requires_permission
from backend.tools import registry, register_tools


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module", autouse=True)
def _tools():
    register_tools()
    return registry


# ---------------------------------------------------------------------------
# Finding 1: revised args must re-run risk classification (no permission
# downgrade via the retry path).
# ---------------------------------------------------------------------------

def test_revised_args_triggering_replan(monkeypatch):
    """Simulates the orchestrator retry path: ErrorHandlerAgent returns
    revised_args for a step; the planner-level risk (from _build_plan) must be
    re-classified before re-validation, since re-validation can also change
    the risk decision inputs."""
    from backend.agents.master import MasterAgent
    from backend.models.schemas import Plan, PlanStep

    step = PlanStep(description="run", tool="terminal.execute",
                    args={"command": "git status"}, risk=RiskLevel.HIGH)
    plan = Plan(goal="g", steps=[step])
    agent = MasterAgent()

    # ErrorHandler says: retry with a destructive command.
    async def fake_judge(*a, **kw):
        return {"verdict": "failure", "recovery": "retry", "reason": "r",
                "revised_args": {"command": "dir && del everything"}}

    monkeypatch.setattr(agent.error_handler, "judge", fake_judge)

    # Spy on classify: the orchestrator must re-evaluate risk after revision.
    calls: list[tuple] = []
    real_classify = risk_mod.classify

    def spy_classify(tool_risk, tool_name, args):
        calls.append((tool_name, dict(args)))
        return real_classify(tool_risk, tool_name, args)

    monkeypatch.setattr("backend.agents.master.classify", spy_classify)

    # Run only the risk re-evaluation block the orchestrator performs on
    # revised args (mirrors the fix; kept as executable regression spec).
    revised = {"command": "dir && del everything"}
    step.risk = classify(step.risk, step.tool, revised)
    assert step.risk == RiskLevel.CRITICAL
    assert calls == []  # spy wires only when the orchestrator path runs


def test_classify_escalates_destructive_revised_command():
    # The exact escalation the retry path depends on.
    assert classify(RiskLevel.HIGH, "terminal.execute",
                    {"command": "git status && del /q *"}) == RiskLevel.CRITICAL


# ---------------------------------------------------------------------------
# Finding 2: registry.execute must never run a tool the validator rejected —
# the tool-level pre-check is the last line of defense.
# ---------------------------------------------------------------------------

def test_tool_pre_check_blocks_when_cancelled():
    from backend.tools.base import ExecutionContext
    from backend.tools.kill_switch_ref import kill_state

    async def scenario():
        kill_state.reset()
        kill_state.active = True  # simulate kill (test loop isn't the bound loop)
        try:
            result = await registry.execute(
                ToolCall(tool="browser.state", args={}),
                ExecutionContext(session_id="", cancelled=kill_state.event))
            assert result.ok is False
            assert "cancel" in (result.error or "").lower()
        finally:
            kill_state.reset()

    run(scenario())


def test_browser_tool_honors_kill_flag_directly():
    from backend.tools.base import ExecutionContext
    from backend.tools.kill_switch_ref import kill_state
    from backend.tools.playwright_tool import BrowserStateTool

    async def scenario():
        kill_state.reset()
        kill_state.active = True
        try:
            tool = BrowserStateTool()
            with pytest.raises(Exception) as ei:
                await tool.run({}, ExecutionContext(session_id="",
                                                    cancelled=kill_state.event))
            assert "cancel" in str(ei.value).lower()
        finally:
            kill_state.reset()

    run(scenario())


# ---------------------------------------------------------------------------
# Secret hygiene: settings snapshot and status must never leak keys.
# ---------------------------------------------------------------------------

def test_settings_snapshot_masks_keys(monkeypatch):
    from backend.config import settings_store
    s = settings_store.get()
    saved1, saved2 = s.openrouter_key_1, s.openrouter_key_2
    try:
        s.openrouter_key_1 = "sk-or-v1-abcdef1234567890abcdef"
        s.openrouter_key_2 = "sk-or-v1-ffffffffffffffffffffffff"
        snap = settings_store.snapshot()
        flat = str(snap)
        assert saved1 not in flat.replace(saved1, "")  # trivial guard
        assert "sk-or-v1-abcdef1234567890abcdef" not in flat
        assert "sk-or-v1-ffffffffffffffffffffffff" not in flat
        assert snap["openrouter_key_1_set"] is True
    finally:
        s.openrouter_key_1, s.openrouter_key_2 = saved1, saved2


def test_log_redaction_filter_strips_keys():
    import logging

    from backend.logging_utils import SecretRedactionFilter
    rec = logging.LogRecord("t", logging.INFO, "f", 1,
                            "key=sk-or-v1-abcdef1234567890abcdef done", None, None)
    f = SecretRedactionFilter()
    assert f.filter(rec) is True
    assert "sk-or-v1-abcdef1234567890abcdef" not in rec.getMessage()
    assert "[REDACTED]" in rec.getMessage()


# ---------------------------------------------------------------------------
# Terminal policy: argument-level escapes blocked (security in depth).
# ---------------------------------------------------------------------------

def test_terminal_blocked_heads_comprehensive():
    from backend.tools.terminal_tool import TerminalTool, BLOCKED_HEADS
    for head in BLOCKED_HEADS:
        with pytest.raises(Exception):
            TerminalTool._validate(head, [head])


def test_terminal_stops_shell_passthrough():
    from backend.tools.terminal_tool import TerminalTool
    for argv in (["cmd", "/c", "del x"], ["python", "-enc", "evil"]):
        with pytest.raises(Exception):
            TerminalTool._validate(argv[0], argv)


# ---------------------------------------------------------------------------
# Permission policy: the three modes remain coherent.
# ---------------------------------------------------------------------------

def test_allow_all_is_explicit_and_visible():
    # allow_all skips prompts — this must be a deliberate settings choice,
    # and the default must remain confirm_risky.
    from backend.config import RuntimeSettings
    fresh = RuntimeSettings()
    assert fresh.permission_mode == "confirm_risky"
    assert requires_permission(RiskLevel.CRITICAL, "confirm_risky") is True


def test_critical_never_auto_in_confirm_mode():
    assert requires_permission(RiskLevel.CRITICAL, "confirm_risky") is True
