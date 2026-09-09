"""Master Agent + MASTPE orchestrator.

The MasterAgent is the single entry point from user message to completed plan:

    USER → InputAnalysis → (chat answer | Planner → Tool Call → Execution)
         → per-step: validate → risk → permission → tool → verify
         → on failure: ErrorHandler → retry / replan / abort / continue

Every state transition is published as an AgentEvent so the UI mirrors real
state (no mock statuses). Execution runs as an asyncio task registered with
the kill switch; permission prompts pause the task until the user decides.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from backend.agents.micro_agents import (
    AgentFailure,
    ErrorHandlerAgent,
    ExecutionAgent,
    InputAnalysisAgent,
    PlannerAgent,
    ToolCallAgent,
)
from backend.agents.prompts import (
    MASTER_CHAT_SYSTEM,
    MASTER_SUMMARY_SYSTEM,
)
from backend.config import get_settings
from backend.events import event_bus
from backend.logging_utils import get_logger, log_json
from backend.memory.session_store import session_store
from backend.models.schemas import (
    AgentEvent,
    ChatMessage,
    ChatRole,
    Plan,
    PlanStep,
    PermissionDecision,
    RiskLevel,
    TaskState,
    ToolCall,
    ToolResult,
)
from backend.providers.router import router as provider_router
from backend.screen.pipeline import screen_pipeline
from backend.security.permissions import (
    PermissionError_,
    PermissionTimeout,
    permission_manager,
)
from backend.security.risk import classify, permission_rationale, requires_permission
from backend.security.validator import ValidationError, validate_tool_call
from backend.tools import registry, register_tools
from backend.tools.kill_switch_ref import kill_state

log = get_logger("agents.master")


class OrchestratorBusy(Exception):
    pass


class MasterAgent:
    """Owns the MASTPE lifecycle. One plan runs at a time (per backend)."""

    def __init__(self) -> None:
        self.input_analysis = InputAnalysisAgent()
        self.planner = PlannerAgent()
        self.tool_call = ToolCallAgent()
        self.execution = ExecutionAgent()
        self.error_handler = ErrorHandlerAgent()
        self._busy = asyncio.Lock()
        self._tools_ready = False

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    async def handle_message(self, session_id: str, text: str,
                             *, execute: bool = True) -> dict[str, Any]:
        """Full pipeline for one user message. Returns response payload."""
        if self._busy.locked():
            raise OrchestratorBusy("a plan is already running")
        async with self._busy:
            await session_store.add_message(session_id, ChatMessage(
                session_id=session_id, role=ChatRole.USER, content=text))
            await self._emit("planning_started", session_id,
                             message="Analyzing request")

            analysis = await self._run_agent(
                "input_analysis", self.input_analysis.analyze(text))
            category = analysis.get("category", "conversation")

            if category == "unclear":
                question = analysis.get("clarify_question") or \
                    "Could you clarify what you would like me to do?"
                msg = await self._add_assistant(session_id, question)
                await self._emit("completed", session_id, message=question)
                return {"session_id": session_id, "message": msg, "plan": None}

            if category == "conversation":
                answer = await self._chat_answer(session_id, text)
                msg = await self._add_assistant(session_id, answer)
                await self._emit("completed", session_id, message="answered")
                return {"session_id": session_id, "message": msg, "plan": None}

            # category == "task"
            goal = analysis.get("goal") or text
            if not execute:
                plan = await self._build_plan(session_id, goal,
                                              needs_screen=analysis.get("needs_screen"))
                msg = await self._add_assistant(
                    session_id, f"Plan created ({len(plan.steps)} steps):\n"
                    + plan.summary())
                await self._emit("completed", session_id, plan_id=plan.id,
                                 status=TaskState.PENDING.value,
                                 message="plan ready (not executed)")
                return {"session_id": session_id, "message": msg, "plan": plan}

            plan = await self._build_plan(session_id, goal,
                                          needs_screen=analysis.get("needs_screen"))
            result = await self.execute_plan(session_id, plan)
            return {"session_id": session_id, "result": result, "plan": plan}

    # ------------------------------------------------------------------
    # Chat path
    # ------------------------------------------------------------------
    async def _chat_answer(self, session_id: str, text: str) -> str:
        context = await session_store.build_chat_context(session_id, limit=8)
        lines = [f"{m['role']}: {m['content'][:400]}" for m in context]
        prompt = "Conversation so far:\n" + "\n".join(lines[-8:]) + \
            f"\n\nUser now says: {text[:1000]}\nRespond concisely."
        try:
            result = await provider_router.simple_chat(prompt, timeout=60.0)
            answer = result.text.strip()
            if not answer:
                raise AgentFailure("empty chat completion")
            return answer[:3000]
        except Exception as exc:  # noqa: BLE001 - honest failure to user
            log_json(log, 30, "chat_failed", error=type(exc).__name__)
            return ("I could not reach an AI provider for that. "
                    "Check Settings → provider configuration.")

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------
    def _ensure_tools(self) -> None:
        if not self._tools_ready:
            register_tools()
            self._tools_ready = True

    async def _build_plan(self, session_id: str, goal: str,
                          *, needs_screen: bool = False) -> Plan:
        self._ensure_tools()
        screen_json = ""
        screen_size = None
        if needs_screen:
            ctx = await screen_pipeline.get_context()
            screen_json = str(ctx.compact())
            screen_size = (ctx.width, ctx.height)

        roadmap = await self._run_agent(
            "planner",
            lambda: self.planner.plan(goal, registry,
                                      screen_context=screen_json[:4000]))
        if not roadmap:
            raise AgentFailure(
                "the planner could not produce a valid plan for this goal "
                "with the available tools")
        refined = await self._run_agent(
            "tool_call",
            lambda: self.tool_call.refine(roadmap, registry, screen_size))

        steps: list[PlanStep] = []
        for r in refined:
            spec = registry.get(r["tool"]).spec
            risk = classify(spec.risk, r["tool"], r.get("args", {}))
            steps.append(PlanStep(
                description=r["description"] or r["tool"],
                tool=r["tool"], args=r.get("args", {}), risk=risk,
                expected_state=r.get("expected_state", ""),
            ))
        plan = Plan(goal=goal[:500], steps=steps, session_id=session_id)
        await session_store.record_plan(session_id, plan)
        await self._emit("plan_created", session_id, plan_id=plan.id,
                         status=TaskState.PENDING.value,
                         message=f"{len(steps)} steps planned",
                         data={"steps": [self._step_view(s) for s in steps]})
        return plan

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    async def execute_plan(self, session_id: str, plan: Plan) -> dict[str, Any]:
        """Run the plan as a kill-switch-registered task."""
        self._ensure_tools()
        kill_state.reset()
        if kill_state.event is not None:
            kill_state.event.clear()

        task = asyncio.current_task()
        if task is not None:
            from backend.security.kill_switch import kill_switch
            kill_switch.register_task(task)

        settings = get_settings()
        await self._emit("execution_started", session_id, plan_id=plan.id,
                         status=TaskState.IN_PROGRESS.value)
        ok_all = True
        errors: list[str] = []
        retries_used: dict[str, int] = {}

        for index, step in enumerate(plan.steps):
            if kill_state.is_cancelled():
                await self._mark_plan_cancelled(session_id, plan)
                return {"state": TaskState.CANCELLED.value, "plan_id": plan.id,
                        "errors": ["execution cancelled"]}
            plan.session_id = session_id
            outcome = await self._run_step(session_id, plan, step, index,
                                           settings, retries_used)
            if outcome == "abort":
                ok_all = False
                errors.append(f"step {index+1} aborted the plan")
                break
            if outcome == "failed":
                ok_all = False

        if kill_state.is_cancelled():
            await self._mark_plan_cancelled(session_id, plan)
            return {"state": TaskState.CANCELLED.value, "plan_id": plan.id,
                    "errors": ["cancelled by kill switch"]}

        if ok_all:
            final = await self._final_summary(session_id, plan)
            msg = await self._add_assistant(session_id, final)
            await self._emit("completed", session_id, plan_id=plan.id,
                             status=TaskState.COMPLETED.value,
                             message="plan completed")
            return {"state": TaskState.COMPLETED.value, "plan_id": plan.id,
                    "message": final, "errors": []}

        # Plan failed → replan once via error handler context.
        return {"state": TaskState.FAILED.value, "plan_id": plan.id,
                "errors": errors or ["one or more steps failed"]}

    async def _run_step(self, session_id: str, plan: Plan, step: PlanStep,
                        index: int, settings,
                        retries_used: dict[str, int]) -> str:
        """Returns 'ok' | 'failed' | 'abort'."""
        step.state = TaskState.IN_PROGRESS
        await session_store.update_plan_step_state(
            session_id, plan.id, step.id, step.state.value)
        await self._emit("step_started", session_id, plan_id=plan.id,
                         step_id=step.id, status=TaskState.IN_PROGRESS.value,
                         message=step.description,
                         data={"index": index, "step": self._step_view(step)})

        # --- Permission gate -------------------------------------------
        if requires_permission(step.risk, settings.permission_mode):
            granted = await self._permission_gate(session_id, plan, step)
            if not granted:
                step.state = TaskState.CANCELLED
                await session_store.update_plan_step_state(
                    session_id, plan.id, step.id, step.state.value)
                await self._emit("step_cancelled", session_id,
                                 plan_id=plan.id, step_id=step.id,
                                 status=TaskState.CANCELLED.value,
                                 message="permission denied")
                return "abort"

        # --- Validation gate (AI → tool boundary) ----------------------
        call = ToolCall(tool=step.tool, args=step.args, step_id=step.id,
                        plan_id=plan.id, session_id=session_id)
        try:
            spec, clean_args = validate_tool_call(call, registry)
        except ValidationError as exc:
            return await self._handle_step_failure(
                session_id, plan, step, index, settings, retries_used,
                f"validation rejected: {exc}")

        # --- Execution with retry loop ---------------------------------
        max_retries = settings.max_retries_per_step
        while True:
            if kill_state.is_cancelled():
                step.state = TaskState.CANCELLED
                return "abort"
            result = await registry.execute(
                ToolCall(call_id=call.call_id, tool=step.tool, args=clean_args,
                         step_id=step.id, plan_id=plan.id,
                         session_id=session_id),
                _ExecutionContextFactory.build(session_id, plan.id, step.id),
            )
            await self._emit("tool_result", session_id, plan_id=plan.id,
                             step_id=step.id, agent="tool",
                             message=(f"{step.tool} -> "
                                      f"{'ok' if result.ok else 'error'}"),
                             data={"ok": result.ok,
                                   "duration_ms": result.duration_ms})
            narration = await self._run_agent(
                "execution",
                lambda: self.execution.narrate(
                    step.description, step.tool, result.ok,
                    str(result.error or result.data)[:800]))
            await self._emit("step_progress", session_id, plan_id=plan.id,
                             step_id=step.id, agent="execution",
                             message=narration[:300])

            # Quick-path: tool succeeded and the step declared no expected
            # state to verify. Steps WITH an expected_state always go through
            # the error-handler/verification judgement below — no silent pass.
            if result.ok and not step.expected_state:
                step.state = TaskState.COMPLETED
                step.result = result.data
                await session_store.update_plan_step_state(
                    session_id, plan.id, step.id, step.state.value)
                await self._emit("step_completed", session_id,
                                 plan_id=plan.id, step_id=step.id,
                                 status=TaskState.COMPLETED.value,
                                 message=step.description)
                return "ok"

            # Failure or unverified → error handler.
            used = retries_used.get(step.id, 0)
            screen_json = ""
            try:
                screen_json = str(await screen_pipeline.compact_json(20))[:1500]
            except Exception:  # noqa: BLE001 - screen context is advisory
                pass
            judgment = await self._run_agent(
                "error_handler",
                lambda: self.error_handler.judge(
                    step.description, step.tool,
                    str(result.error or "verification failed")[:1200],
                    step.expected_state, screen_json,
                    retries_used=used, max_retries=max_retries))
            recovery = judgment["recovery"]
            if judgment["verdict"] == "success" and result.ok:
                # Handler overrules failed verification (e.g. OCR-blind).
                step.state = TaskState.COMPLETED
                step.result = result.data
                await session_store.update_plan_step_state(
                    session_id, plan.id, step.id, step.state.value)
                await self._emit("step_completed", session_id,
                                 plan_id=plan.id, step_id=step.id,
                                 status=TaskState.COMPLETED.value,
                                 message=judgment["reason"] or step.description)
                return "ok"
            if recovery == "retry" and used < max_retries:
                retries_used[step.id] = used + 1
                if judgment["revised_args"]:
                    merged = dict(clean_args)
                    merged.update(judgment["revised_args"])
                    try:
                        spec2, clean_args = validate_tool_call(
                            ToolCall(tool=step.tool, args=merged,
                                     step_id=step.id, plan_id=plan.id,
                                     session_id=session_id), registry)
                    except ValidationError as exc:
                        return await self._handle_step_failure(
                            session_id, plan, step, index, settings,
                            retries_used, f"revised args rejected: {exc}")
                await self._emit("step_retry", session_id, plan_id=plan.id,
                                 step_id=step.id,
                                 message=judgment["reason"] or "retrying")
                continue
            if recovery == "continue":
                await self._emit("step_failed_continue", session_id,
                                 plan_id=plan.id, step_id=step.id,
                                 status=TaskState.FAILED.value,
                                 message=judgment["reason"])
                return "ok"
            if recovery == "abort":
                step.state = TaskState.FAILED
                step.error = judgment["reason"] or "aborted by error handler"
                await session_store.update_plan_step_state(
                    session_id, plan.id, step.id, step.state.value,
                    error=step.error)
                await self._emit("step_failed", session_id, plan_id=plan.id,
                                 step_id=step.id,
                                 status=TaskState.FAILED.value,
                                 message=judgment["reason"])
                return "abort"
            # replan → treat step as failed; plan-level failure handles it.
            step.state = TaskState.FAILED
            step.error = judgment["reason"] or "replan required"
            await session_store.update_plan_step_state(
                session_id, plan.id, step.id, step.state.value,
                error=step.error)
            await self._emit("step_failed", session_id, plan_id=plan.id,
                             step_id=step.id, status=TaskState.FAILED.value,
                             message=judgment["reason"])
            return "failed"

    # ------------------------------------------------------------------
    # Permission + verification
    # ------------------------------------------------------------------
    async def _permission_gate(self, session_id: str, plan: Plan,
                               step: PlanStep) -> bool:
        args_summary = ", ".join(
            f"{k}={str(v)[:60]}" for k, v in list(step.args.items())[:6])
        req = await permission_manager.request(
            tool=step.tool, description=step.description, risk=step.risk,
            args_summary=args_summary, session_id=session_id,
            plan_id=plan.id, step_id=step.id)
        await self._emit("permission_required", session_id, plan_id=plan.id,
                         step_id=step.id,
                         status=TaskState.WAITING_PERMISSION.value,
                         message=f"{step.tool} needs approval",
                         data={"request_id": req.request_id,
                               "risk": step.risk.value,
                               "tool": step.tool,
                               "args_summary": req.args_summary})
        try:
            decision = await permission_manager.wait_decision(req.request_id)
            allowed = decision == PermissionDecision.APPROVED
        except PermissionTimeout:
            allowed = False
        except PermissionError_:
            allowed = False
        await self._emit("permission_resolved", session_id, plan_id=plan.id,
                         step_id=step.id,
                         message="approved" if allowed else "denied",
                         data={"request_id": req.request_id})
        return allowed

    async def _handle_step_failure(self, session_id: str, plan: Plan,
                                   step: PlanStep, index: int, settings,
                                   retries_used: dict[str, int],
                                   reason: str) -> str:
        step.state = TaskState.FAILED
        step.error = reason
        await session_store.update_plan_step_state(
            session_id, plan.id, step.id, step.state.value, error=reason)
        await self._emit("step_failed", session_id, plan_id=plan.id,
                         step_id=step.id, status=TaskState.FAILED.value,
                         message=reason)
        return "failed"

    async def _mark_plan_cancelled(self, session_id: str, plan: Plan) -> None:
        for step in plan.steps:
            if step.state in (TaskState.PENDING, TaskState.IN_PROGRESS,
                              TaskState.WAITING_PERMISSION):
                step.state = TaskState.CANCELLED
                await session_store.update_plan_step_state(
                    session_id, plan.id, step.id, step.state.value)
        await self._emit("cancelled", session_id, plan_id=plan.id,
                         status=TaskState.CANCELLED.value,
                         message="plan cancelled")

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------
    async def _final_summary(self, session_id: str, plan: Plan) -> str:
        lines = []
        for i, s in enumerate(plan.steps, 1):
            status = s.state.value
            detail = s.error or ""
            lines.append(f"{i}. [{status}] {s.description}"
                         + (f" — {detail}" if detail else ""))
        body = "\n".join(lines)
        try:
            result = await provider_router.generate_for_agent(
                "master", MASTER_SUMMARY_SYSTEM,
                f"Goal: {plan.goal}\n\nStep results:\n{body[:3000]}",
                max_tokens=400, timeout=45.0)
            return result.text.strip()[:3000] or body
        except Exception:  # noqa: BLE001 - deterministic fallback
            return f"Completed: {plan.goal}\n{body}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _run_agent(self, agent: str, coro_or_fn) -> Any:
        """Run an agent call, converting AgentFailure/ProviderError into a
        user-facing error event; re-raises AgentFailure after emitting."""
        try:
            if callable(coro_or_fn):
                return await coro_or_fn()
            return await coro_or_fn
        except AgentFailure as exc:
            await self._emit("agent_error", "", agent=agent,
                             message=str(exc)[:300])
            raise
        except Exception as exc:  # ProviderError etc.
            await self._emit("agent_error", "", agent=agent,
                             message=f"{agent}: {type(exc).__name__}: "
                                     f"{str(exc)[:200]}")
            raise AgentFailure(str(exc)[:300]) from exc

    async def _add_assistant(self, session_id: str, content: str) -> ChatMessage:
        msg = ChatMessage(session_id=session_id, role=ChatRole.MASTER,
                          content=content[:8000])
        await session_store.add_message(session_id, msg)
        return msg

    async def _emit(self, event: str, session_id: str, *, plan_id=None,
                    step_id=None, agent=None, status=None, message="",
                    data=None) -> None:
        await event_bus.publish(AgentEvent(
            event=event, session_id=session_id, plan_id=plan_id,
            step_id=step_id, agent=agent, status=status, message=message,
            data=data or {}))

    @staticmethod
    def _step_view(step: PlanStep) -> dict[str, Any]:
        return {
            "id": step.id, "description": step.description[:200],
            "tool": step.tool, "risk": step.risk.value,
            "state": step.state.value,
            "expected_state": step.expected_state[:200],
        }

    # ------------------------------------------------------------------
    # Chat-only convenience for /api/chat with execute=False
    # ------------------------------------------------------------------
    async def stop_current(self) -> bool:
        """User-initiated stop: set the shared kill flag so the running plan's
        cancellation checks fire, then reset it so new work can start.
        Distinct from the emergency kill switch (no task cancellation)."""
        if not self._busy.locked():
            return False
        kill_state.trigger()
        await self._emit("cancelled", "", message="stop requested by user")
        return True


master_agent = MasterAgent()


class _ExecutionContextFactory:
    @staticmethod
    def build(session_id: str, plan_id: str, step_id: str):
        from backend.tools.base import ExecutionContext
        return ExecutionContext(session_id=session_id, plan_id=plan_id,
                                step_id=step_id,
                                cancelled=kill_state.event)
