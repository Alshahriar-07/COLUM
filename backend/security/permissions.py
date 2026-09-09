"""Permission manager — the approval flow between security and execution.

Flow: executor classifies a step -> if policy says permission is required, a
PermissionRequest is created and broadcast to the UI; the executor awaits the
user's decision (with timeout). Decisions arrive via the REST API
(`/api/permission/decision`) or the allow-all mode.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

from backend.config import LOGS_DIR, settings_store
from backend.logging_utils import get_logger, log_json
from backend.models.schemas import (
    PermissionDecision,
    PermissionRequest,
    RiskLevel,
    TaskState,
)
from backend.security.risk import permission_rationale

log = get_logger("security.permissions")

PERMISSION_TIMEOUT_S = 300.0  # user has 5 minutes to decide
AUDIT_FILE = LOGS_DIR / "audit" / "permissions.jsonl"


class PermissionError_(Exception):
    """User denied a permission request."""


class PermissionTimeout(Exception):
    """User did not respond in time."""


class PermissionManager:
    def __init__(self) -> None:
        self._pending: dict[str, PermissionRequest] = {}
        self._futures: dict[str, asyncio.Future] = {}
        self._decisions: dict[str, PermissionDecision] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Request lifecycle
    # ------------------------------------------------------------------
    async def request(
        self,
        *,
        tool: str,
        description: str,
        risk: RiskLevel,
        args_summary: str,
        session_id: str = "",
        plan_id: str = "",
        step_id: str = "",
    ) -> PermissionRequest:
        req = PermissionRequest(
            session_id=session_id, plan_id=plan_id, step_id=step_id,
            tool=tool, description=description, risk=risk, args_summary=args_summary,
        )
        async with self._lock:
            self._pending[req.request_id] = req
        log_json(log, 20, "permission_requested", request_id=req.request_id,
                 tool=tool, risk=risk.value)
        self._audit(req, "requested")
        return req

    async def wait_decision(self, request_id: str,
                            timeout: float = PERMISSION_TIMEOUT_S) -> PermissionDecision:
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._futures[request_id] = fut
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as exc:
            self._finalize(request_id, TaskState.FAILED)
            raise PermissionTimeout(
                f"no permission decision within {timeout:.0f}s"
            ) from exc
        finally:
            self._futures.pop(request_id, None)

    def resolve(self, request_id: str, approved: bool) -> PermissionRequest:
        """Called by the API when the user approves/denies."""
        req = self._pending.get(request_id)
        if req is None:
            raise KeyError(f"unknown permission request '{request_id}'")
        decision = PermissionDecision.APPROVED if approved else PermissionDecision.DENIED
        req.decision = decision
        req.state = TaskState.IN_PROGRESS if approved else TaskState.CANCELLED
        self._audit(req, "approved" if approved else "denied")
        log_json(log, 20, "permission_resolved", request_id=request_id,
                 approved=approved)
        fut = self._futures.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(decision)
        return req

    async def cancel_all(self, reason: str = "") -> int:
        """Kill switch support: fail every pending request."""
        async with self._lock:
            pending = list(self._pending.items())
        count = 0
        for rid, req in pending:
            if req.state == TaskState.WAITING_PERMISSION:
                req.state = TaskState.CANCELLED
                count += 1
                self._audit(req, "cancelled", reason=reason)
                fut = self._futures.get(rid)
                if fut is not None and not fut.done():
                    fut.set_exception(PermissionError_("cancelled by kill switch"))
        self._pending.clear()
        return count

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    def get(self, request_id: str) -> Optional[PermissionRequest]:
        return self._pending.get(request_id)

    def pending_list(self) -> list[PermissionRequest]:
        return [r for r in self._pending.values()
                if r.state == TaskState.WAITING_PERMISSION]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _finalize(self, request_id: str, state: TaskState) -> None:
        req = self._pending.get(request_id)
        if req is not None:
            req.state = state

    @staticmethod
    def _audit(req: PermissionRequest, action: str, reason: str = "") -> None:
        """Append-only permission audit trail (no secrets — args are summarized)."""
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": action,
            "request_id": req.request_id,
            "tool": req.tool,
            "risk": req.risk.value,
            "reason": reason,
            "args_summary": req.args_summary[:300],
        }
        try:
            AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001 - audit failure must not break flow
            log_json(log, 40, "permission_audit_write_failed")


permission_manager = PermissionManager()
