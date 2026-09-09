"""COLUM session memory — compact JSON session persistence.

Sessions live in `data/sessions/<session_id>.json` with a compact summary (no
secrets, no raw tool-output dumps). The latest session can be restored at
startup. Corrupt files are quarantined (renamed `.corrupt`), never crash the
backend. All writes are atomic (tmp file + replace) and offloaded to a thread.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.config import SESSIONS_DIR
from backend.logging_utils import get_logger, log_json
from backend.models.schemas import ChatMessage, Plan, SessionSummary

log = get_logger("memory")

MAX_MESSAGES_KEPT = 200          # ring size per session
MAX_MESSAGE_CHARS = 8000         # truncate pathological messages on disk
SUMMARY_MAX_CHARS = 2000


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SessionStore:
    """Thread-safe, asyncio-friendly JSON session store."""

    def __init__(self, directory: Path = SESSIONS_DIR) -> None:
        self._dir = Path(directory)
        self._sessions: dict[str, dict[str, Any]] = {}   # sid -> full record
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def restore_latest(self) -> Optional[str]:
        """Synchronous startup restore: load the most recently updated session.

        Returns the session id, or None when no recoverable session exists.
        Corrupt files are quarantined, never raised.
        """
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            candidates = sorted(
                self._dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError as exc:
            log_json(log, 30, "session_restore_scan_failed", error=type(exc).__name__)
            return None
        for path in candidates:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                sid = record.get("session_id")
                if not sid:
                    continue
                record.setdefault("messages", [])
                record.setdefault("summary", SessionSummary(
                    session_id=sid).model_dump(mode="json"))
                self._sessions[sid] = record
                log_json(log, 20, "session_restored", session_id=sid,
                         messages=len(record["messages"]))
                return sid
            except Exception as exc:  # noqa: BLE001 - corruption must not crash
                self._quarantine(path)
                log_json(log, 30, "session_corrupt_quarantined",
                         file=path.name, error=type(exc).__name__)
        return None

    def _quarantine(self, path: Path) -> None:
        try:
            path.rename(path.with_suffix(path.suffix + ".corrupt"))
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------
    async def create_session(self, title: str = "New session") -> str:
        async with self._lock:
            sid = f"sess_{uuid.uuid4().hex[:12]}"
            summary = SessionSummary(session_id=sid, title=title[:120])
            self._sessions[sid] = {
                "session_id": sid,
                "messages": [],
                "summary": summary.model_dump(mode="json"),
                "plans": {},
            }
            await self._persist_locked(sid)
            return sid

    async def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        async with self._lock:
            return self._sessions.get(session_id)

    async def list_sessions(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [self._summary_view(rec) for rec in
                    sorted(self._sessions.values(),
                           key=lambda r: r.get("summary", {}).get("updated_at", ""),
                           reverse=True)]

    async def ensure_session(self, session_id: Optional[str]) -> str:
        """Return a valid session id: existing, or a freshly created one."""
        if session_id:
            async with self._lock:
                if session_id in self._sessions:
                    return session_id
        return await self.create_session()

    async def delete_session(self, session_id: str) -> bool:
        async with self._lock:
            rec = self._sessions.pop(session_id, None)
        if rec is None:
            return False
        path = self._dir / f"{session_id}.json"
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return True

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------
    async def add_message(self, session_id: str, message: ChatMessage) -> None:
        async with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                return
            entry = message.model_dump(mode="json")
            entry["content"] = str(entry.get("content", ""))[:MAX_MESSAGE_CHARS]
            messages: list[dict[str, Any]] = rec["messages"]
            messages.append(entry)
            if len(messages) > MAX_MESSAGES_KEPT:
                del messages[: len(messages) - MAX_MESSAGES_KEPT]
            summary = rec["summary"]
            summary["message_count"] = len(messages)
            summary["updated_at"] = _now_iso()
            if not messages or summary["title"] == "New session":
                first = (message.content or "").strip()
                if first:
                    summary["title"] = first[:60]
            await self._persist_locked(session_id)

    async def get_messages(self, session_id: str,
                           limit: int = 50) -> list[ChatMessage]:
        async with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                return []
            entries = rec["messages"][-limit:]
        out: list[ChatMessage] = []
        for e in entries:
            try:
                out.append(ChatMessage(**e))
            except Exception:  # skip malformed entries honestly
                continue
        return out

    async def build_chat_context(self, session_id: str,
                                 limit: int = 12) -> list[dict[str, str]]:
        """Recent conversation as provider `messages` (user/assistant only)."""
        msgs = await self.get_messages(session_id, limit=limit)
        out: list[dict[str, str]] = []
        for m in msgs:
            if m.role.value in ("user", "master"):
                out.append({
                    "role": "assistant" if m.role.value == "master" else "user",
                    "content": m.content[:1500],
                })
        return out

    # ------------------------------------------------------------------
    # Plans & summaries
    # ------------------------------------------------------------------
    async def record_plan(self, session_id: str, plan: Plan) -> None:
        async with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                return
            rec["plans"][plan.id] = {
                "plan_id": plan.id,
                "goal": plan.goal[:500],
                "steps": [
                    {"id": s.id, "description": s.description[:300],
                     "tool": s.tool, "risk": s.risk.value, "state": s.state.value}
                    for s in plan.steps
                ],
                "created_at": plan.created_at.isoformat(),
            }
            rec["summary"]["last_plan_id"] = plan.id
            rec["summary"]["updated_at"] = _now_iso()
            await self._persist_locked(session_id)

    async def update_plan_step_state(self, session_id: str, plan_id: str,
                                     step_id: str, state: str,
                                     error: Optional[str] = None) -> None:
        async with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                return
            plan = rec.get("plans", {}).get(plan_id)
            if not plan:
                return
            for s in plan["steps"]:
                if s["id"] == step_id:
                    s["state"] = state
                    if error:
                        s["error"] = str(error)[:300]
            rec["summary"]["updated_at"] = _now_iso()
            await self._persist_locked(session_id)

    async def set_summary(self, session_id: str, summary_text: str,
                          facts: Optional[list[str]] = None) -> None:
        async with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                return
            rec["summary"]["summary"] = (summary_text or "")[:SUMMARY_MAX_CHARS]
            if facts:
                rec["summary"]["facts"] = [str(f)[:200] for f in facts[:20]]
            rec["summary"]["updated_at"] = _now_iso()
            await self._persist_locked(session_id)

    async def summarize_and_store(self, session_id: str, text: str) -> None:
        """Compact summary generation: uses the router if available, else a
        deterministic extract of the recent conversation. Never raises."""
        summary = ""
        facts: list[str] = []
        try:
            from backend.providers.router import router as provider_router
            context = await self.build_chat_context(session_id, limit=10)
            convo = "\n".join(f"{m['role']}: {m['content'][:400]}"
                              for m in context) or text[:1500]
            result = await provider_router.simple_chat(
                "Summarize this session in at most 5 short bullet-like lines, "
                "then a line 'FACTS:' with up to 5 durable facts. Be factual.\n\n"
                f"{convo}", timeout=45.0)
            body = result.text.strip()[:SUMMARY_MAX_CHARS]
            if "\nFACTS:" in body:
                head, tail = body.split("\nFACTS:", 1)
                summary, facts = head.strip(), [
                    l.strip("-• ").strip() for l in tail.strip().splitlines()
                    if l.strip()][:5]
            else:
                summary = body
        except Exception as exc:  # noqa: BLE001 - fall back to local extract
            log_json(log, 20, "session_summary_fallback", error=type(exc).__name__)
            msgs = await self.get_messages(session_id, limit=6)
            summary = " | ".join(
                f"{m.role.value}: {m.content[:120]}" for m in msgs)[:SUMMARY_MAX_CHARS]
        await self.set_summary(session_id, summary, facts)

    # ------------------------------------------------------------------
    # Persistence internals
    # ------------------------------------------------------------------
    def _summary_view(self, rec: dict[str, Any]) -> dict[str, Any]:
        s = rec.get("summary", {})
        return {
            "session_id": rec["session_id"],
            "title": s.get("title", "New session"),
            "summary": s.get("summary", ""),
            "message_count": s.get("message_count", 0),
            "updated_at": s.get("updated_at", ""),
        }

    async def _persist_locked(self, session_id: str) -> None:
        rec = self._sessions.get(session_id)
        if rec is None:
            return
        await asyncio.to_thread(self._write_sync, session_id, rec)

    def _write_sync(self, session_id: str, rec: dict[str, Any]) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path = self._dir / f"{session_id}.json"
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(rec, ensure_ascii=False, default=str),
                           encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            log_json(log, 40, "session_write_failed",
                     session_id=session_id, error=type(exc).__name__)


session_store = SessionStore()
