"""Agent tests — JSON reconciliation with a stubbed provider router."""
from __future__ import annotations

import asyncio

import pytest

from backend.agents.micro_agents import (
    ErrorHandlerAgent,
    InputAnalysisAgent,
    PlannerAgent,
)
from backend.tools import register_tools, registry


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class StubResult:
    def __init__(self, text: str) -> None:
        self.text = text
        self.provider = "stub"
        self.model = "stub-model"
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0


@pytest.fixture()
def stub_router(monkeypatch):
    """Replace router.generate_for_agent with a scripted stub."""
    calls = []

    async def fake_generate(agent, system_prompt, user_prompt, **kwargs):
        calls.append({"agent": agent, "user": user_prompt})
        scripted = fake_generate.next_text
        return StubResult(scripted)

    fake_generate.next_text = "{}"
    monkeypatch.setattr(
        "backend.agents.micro_agents.provider_router.generate_for_agent",
        fake_generate)
    return fake_generate


@pytest.fixture(scope="module", autouse=True)
def _tools():
    register_tools()
    return registry


# ---------------------------------------------------------------------------
# InputAnalysisAgent
# ---------------------------------------------------------------------------

def test_input_analysis_parses_valid(stub_router):
    stub_router.next_text = ('{"category": "task", "goal": "open example.com", '
                             '"needs_screen": false, "clarify_question": ""}')
    agent = InputAnalysisAgent()
    out = run(agent.analyze("open example.com"))
    assert out["category"] == "task"
    assert out["goal"] == "open example.com"


def test_input_analysis_invalid_category_sanitized(stub_router):
    stub_router.next_text = ('{"category": "weird", "goal": "g", '
                             '"needs_screen": "yes", "clarify_question": ""}')
    agent = InputAnalysisAgent()
    out = run(agent.analyze("do the thing"))
    assert out["category"] == "conversation"
    assert out["needs_screen"] is True  # truthy string → bool True


def test_input_analysis_imperative_fallback_to_task(stub_router):
    stub_router.next_text = '{"category": "conversation", "goal": "", "needs_screen": false, "clarify_question": ""}'
    agent = InputAnalysisAgent()
    out = run(agent.analyze("Open the browser"))
    assert out["category"] == "task"
    assert out["goal"] == "Open the browser"


def test_input_analysis_garbage_output_fails(stub_router):
    stub_router.next_text = "I am sorry, I cannot do that."
    agent = InputAnalysisAgent()
    from backend.agents.micro_agents import AgentFailure
    with pytest.raises(AgentFailure):
        run(agent.analyze("hello"))


# ---------------------------------------------------------------------------
# PlannerAgent — reconciliation against the registry
# ---------------------------------------------------------------------------

def test_planner_drops_unknown_tools(stub_router):
    stub_router.next_text = (
        '{"steps": ['
        '{"description": "nav", "tool": "browser.navigate", '
        ' "args": {"url": "https://example.com"}, "expected_state": "page open"},'
        '{"description": "bad", "tool": "make sandwich", "args": {}, "expected_state": ""}'
        ']}')
    agent = PlannerAgent()
    steps = run(agent.plan("open example.com", registry))
    assert len(steps) == 1
    assert steps[0]["tool"] == "browser.navigate"
    assert steps[0]["args"] == {"url": "https://example.com"}


def test_planner_non_dict_args_rejected(stub_router):
    stub_router.next_text = (
        '{"steps": [{"description": "d", "tool": "browser.open", '
        '"args": "not a dict", "expected_state": ""}]}')
    agent = PlannerAgent()
    steps = run(agent.plan("x", registry))
    assert steps and steps[0]["args"] == {}


def test_planner_steps_not_list_fails(stub_router):
    stub_router.next_text = '{"steps": "nope"}'
    agent = PlannerAgent()
    from backend.agents.micro_agents import AgentFailure
    with pytest.raises(AgentFailure):
        run(agent.plan("x", registry))


# ---------------------------------------------------------------------------
# ErrorHandlerAgent — recovery decision sanity
# ---------------------------------------------------------------------------

def test_error_handler_retries_capped(stub_router):
    stub_router.next_text = (
        '{"verdict": "failure", "recovery": "retry", "reason": "transient", '
        '"revised_args": {}}')
    agent = ErrorHandlerAgent()
    out = run(agent.judge("d", "browser.open", "timeout", "open", "",
                          retries_used=2, max_retries=2))
    # retry budget exhausted → must downgrade to replan
    assert out["recovery"] == "replan"


def test_error_handler_invalid_recovery_sanitized(stub_router):
    stub_router.next_text = (
        '{"verdict": "failure", "recovery": "explode", "reason": "r", '
        '"revised_args": "not a dict"}')
    agent = ErrorHandlerAgent()
    out = run(agent.judge("d", "browser.open", "e", "", "", retries_used=0,
                          max_retries=2))
    assert out["recovery"] == "replan"
    assert out["revised_args"] == {}
