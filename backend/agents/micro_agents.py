"""MASTPE micro-agents — structured JSON generation over the provider router.

Rules:
- Every agent resolves its model via the router (per-agent overrides, env
  defaults) and never hard-codes a model.
- LLM output is parsed with `extract_json` and reconciled against the tool
  registry; malformed output raises AgentFailure (treated as a provider-level
  failure by the orchestrator).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from backend.agents.prompts import (
    ERROR_HANDLER_SYSTEM_TEMPLATE,
    EXECUTION_SYSTEM,
    INPUT_ANALYSIS_SYSTEM,
    PLANNER_SYSTEM_TEMPLATE,
    TOOL_CALL_SYSTEM_TEMPLATE,
    tool_catalog,
)
from backend.config import get_settings
from backend.logging_utils import get_logger, log_json
from backend.models.schemas import PlanStep, RiskLevel, TaskState
from backend.providers.base import extract_json
from backend.providers.router import router as provider_router
from backend.tools.base import ToolRegistry

log = get_logger("agents")

_CONVERSATION_MARKERS = (
    "what", "who", "why", "when", "how", "explain", "tell me", "hi", "hello",
    "thanks", "thank you", "can you explain", "?",
)


class AgentFailure(Exception):
    """An agent could not produce a usable result."""


def _strip_fences(text: str) -> str:
    return text.strip()


class _BaseAgent:
    name = "base"

    async def _generate_json(self, system_prompt: str, user_prompt: str,
                             *, temperature: float = 0.1,
                             max_tokens: int = 2048,
                             timeout: float = 60.0) -> dict[str, Any]:
        result = await provider_router.generate_for_agent(
            self.name, system_prompt, user_prompt,
            temperature=temperature, max_tokens=max_tokens, timeout=timeout,
            require_json=True,
        )
        parsed = extract_json(result.text)
        if not isinstance(parsed, dict):
            log_json(log, 30, "agent_json_invalid", agent=self.name,
                     raw_len=len(result.text))
            raise AgentFailure(f"{self.name} returned unparseable output")
        return parsed

    async def _generate_text(self, system_prompt: str, user_prompt: str,
                             *, temperature: float = 0.3,
                             max_tokens: int = 400,
                             timeout: float = 45.0) -> str:
        result = await provider_router.generate_for_agent(
            self.name, system_prompt, user_prompt,
            temperature=temperature, max_tokens=max_tokens, timeout=timeout,
        )
        return result.text.strip()


class InputAnalysisAgent(_BaseAgent):
    name = "input_analysis"

    async def analyze(self, user_message: str) -> dict[str, Any]:
        parsed = await self._generate_json(
            INPUT_ANALYSIS_SYSTEM,
            f"User message:\n\"\"\"\n{user_message[:3000]}\n\"\"\"",
        )
        category = str(parsed.get("category", "conversation")).lower().strip()
        if category not in ("task", "conversation", "unclear"):
            category = "conversation"
        out = {
            "category": category,
            "goal": str(parsed.get("goal", ""))[:500].strip(),
            "needs_screen": bool(parsed.get("needs_screen", False)),
            "clarify_question": str(parsed.get("clarify_question", ""))[:300],
        }
        # Deterministic guardrails around the LLM classification.
        lowered = user_message.lower().strip()
        if out["category"] == "conversation" and any(
                lowered.startswith(m) for m in ("open ", "click ", "type ", "run ")):
            out["category"] = "task"
        if not out["goal"]:
            out["goal"] = user_message.strip()[:300]
        log_json(log, 20, "input_analyzed", category=out["category"],
                 needs_screen=out["needs_screen"])
        return out


class PlannerAgent(_BaseAgent):
    name = "planner"

    async def plan(self, goal: str, reg: ToolRegistry,
                   *, screen_context: str = "",
                   max_steps: Optional[int] = None) -> list[dict[str, Any]]:
        settings = get_settings()
        cap = max_steps or settings.max_steps_per_plan
        catalog = tool_catalog(reg)
        system = PLANNER_SYSTEM_TEMPLATE.format(
            max_steps=cap, catalog=catalog)
        user = f"Goal: {goal}"
        if screen_context:
            user += f"\n\nCurrent screen context:\n{screen_context}"
        parsed = await self._generate_json(system, user, temperature=0.2)
        steps = parsed.get("steps")
        if not isinstance(steps, list):
            raise AgentFailure("planner returned no steps list")
        clean: list[dict[str, Any]] = []
        for s in steps[:cap]:
            if not isinstance(s, dict):
                continue
            tool = str(s.get("tool", "")).strip()
            if not reg.exists(tool):
                continue  # reject unknown tools silently at roadmap level
            clean.append({
                "description": str(s.get("description", ""))[:400],
                "tool": tool,
                "args": s.get("args") if isinstance(s.get("args"), dict) else {},
                "expected_state": str(s.get("expected_state", ""))[:300],
            })
        if parsed.get("impossible_reason"):
            log_json(log, 20, "planner_impossible",
                     reason=str(parsed["impossible_reason"])[:200])
        return clean


class ToolCallAgent(_BaseAgent):
    name = "tool_call"

    async def refine(self, roadmap: list[dict[str, Any]], reg: ToolRegistry,
                     screen_size: tuple[int, int] | None = None
                     ) -> list[dict[str, Any]]:
        catalog = tool_catalog(reg)
        roadmap_txt = "\n".join(
            f"{i+1}. {s['description']} (tool={s['tool']}, args={s['args']})"
            for i, s in enumerate(roadmap))
        screen = f"{screen_size[0]}x{screen_size[1]}" if screen_size else "unknown"
        system = TOOL_CALL_SYSTEM_TEMPLATE.format(catalog=catalog, screen=screen)
        parsed = await self._generate_json(system, roadmap_txt, temperature=0.1)
        steps = parsed.get("steps")
        if not isinstance(steps, list) or not steps:
            # Tool Call agent failed to refine; fall back to roadmap as-is.
            log_json(log, 20, "tool_call_fallback_to_roadmap")
            return roadmap
        refined: list[dict[str, Any]] = []
        for s in steps[: len(roadmap)]:
            if not isinstance(s, dict):
                continue
            tool = str(s.get("tool", "")).strip()
            if not reg.exists(tool):
                continue
            args = s.get("args") if isinstance(s.get("args"), dict) else {}
            refined.append({
                "description": str(s.get("description", ""))[:400],
                "tool": tool,
                "args": args,
                "expected_state": str(s.get("expected_state", ""))[:300],
            })
        # Sanity: every arg must be in the tool schema; else keep roadmap args.
        for r in refined:
            spec = reg.get(r["tool"]).spec
            schema = set(spec.args_schema)
            r["args"] = {k: v for k, v in r["args"].items() if k in schema}
        return refined or roadmap


class ExecutionAgent(_BaseAgent):
    name = "execution"

    async def narrate(self, description: str, tool: str,
                      ok: bool, result_summary: str) -> str:
        try:
            return await self._generate_text(
                EXECUTION_SYSTEM,
                f"Step: {description}\nTool: {tool}\n"
                f"Result: {'OK' if ok else 'ERROR'}\n{result_summary[:1500]}",
                max_tokens=200,
            )
        except Exception:  # narration must never block execution
            return (f"Step completed: {description}"
                    if ok else f"Step failed: {description}")


class ErrorHandlerAgent(_BaseAgent):
    name = "error_handler"

    async def judge(self, description: str, tool: str, error: str,
                    expected_state: str, screen_json: str,
                    *, retries_used: int = 0,
                    max_retries: int = 2) -> dict[str, Any]:
        system = ERROR_HANDLER_SYSTEM_TEMPLATE.format(
            max_retries=max_retries, screen=screen_json or "(unavailable)")
        user = (f"Step: {description}\nTool: {tool}\n"
                f"Expected: {expected_state or '(not declared)'}\n"
                f"Error/result: {error[:1200]}\n"
                f"Retries already used: {retries_used}/{max_retries}")
        parsed = await self._generate_json(system, user, temperature=0.1)
        verdict = str(parsed.get("verdict", "failure")).lower()
        recovery = str(parsed.get("recovery", "replan")).lower()
        if verdict not in ("success", "failure"):
            verdict = "failure"
        if recovery not in ("continue", "retry", "replan", "abort"):
            recovery = "replan"
        if retries_used >= max_retries and recovery == "retry":
            recovery = "replan"
        revised = parsed.get("revised_args")
        return {
            "verdict": verdict,
            "recovery": recovery,
            "reason": str(parsed.get("reason", ""))[:400],
            "revised_args": revised if isinstance(revised, dict) else {},
        }
