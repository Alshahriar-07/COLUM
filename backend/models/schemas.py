"""COLUM core data models.

All internal communication uses these typed Pydantic models. In particular:
LLM output is NEVER executed — it must first be parsed into a `Plan` /
`PlanStep` structure and pass through `security.validator`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskState(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_PERMISSION = "waiting_permission"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PermissionDecision(str, Enum):
    APPROVED = "approved"
    DENIED = "denied"
    AUTO = "auto"          # auto-approved by policy (low risk)
    ALLOW_ALL = "allow_all"  # auto-approved because allow-all mode is on


# ---------------------------------------------------------------------------
# Screen context
# ---------------------------------------------------------------------------

class ScreenElement(BaseModel):
    type: str = "text"                     # button | input | text | link | image | window | other
    text: str = ""
    x: int
    y: int
    width: int = 0
    height: int = 0
    confidence: float = 1.0


class ScreenContext(BaseModel):
    width: int
    height: int
    captured_at: datetime = Field(default_factory=utcnow)
    elements: list[ScreenElement] = Field(default_factory=list)
    active_window: str = ""
    note: str = ""                          # e.g. degraded mode explanations

    def compact(self, max_elements: int = 60) -> dict[str, Any]:
        els = sorted(self.elements, key=lambda e: -e.confidence)[:max_elements]
        return {
            "screen": {"width": self.width, "height": self.height},
            "active_window": self.active_window,
            "elements": [e.model_dump() for e in els],
            **({"note": self.note} if self.note else {}),
        }


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

class PlanStep(BaseModel):
    id: str = Field(default_factory=lambda: new_id("step"))
    description: str
    tool: str                                   # must exist in the tool registry
    args: dict[str, Any] = Field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    requires_permission: Optional[bool] = None  # None => decide via security policy
    expected_state: str = ""                    # human-readable expected outcome
    depends_on: list[str] = Field(default_factory=list)
    state: TaskState = TaskState.PENDING
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    @field_validator("tool")
    @classmethod
    def tool_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("tool name must be non-empty")
        return v


class Plan(BaseModel):
    id: str = Field(default_factory=lambda: new_id("plan"))
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    session_id: str = ""
    recovery_of: Optional[str] = None           # plan id this replan recovers

    def summary(self) -> str:
        lines = [f"Goal: {self.goal}"]
        for i, s in enumerate(self.steps, 1):
            lines.append(f"  {i}. [{s.risk.value}] {s.description} ({s.tool})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool calls & results
# ---------------------------------------------------------------------------

class ToolCall(BaseModel):
    call_id: str = Field(default_factory=lambda: new_id("call"))
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    step_id: Optional[str] = None
    plan_id: Optional[str] = None
    session_id: str = ""


class ToolResult(BaseModel):
    call_id: str
    tool: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: int = 0
    started_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class PermissionRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: new_id("perm"))
    session_id: str = ""
    plan_id: str = ""
    step_id: str = ""
    tool: str
    description: str
    risk: RiskLevel
    args_summary: str = ""                       # redacted, human-readable args
    created_at: datetime = Field(default_factory=utcnow)
    state: TaskState = TaskState.WAITING_PERMISSION
    decision: Optional[PermissionDecision] = None


# ---------------------------------------------------------------------------
# Sessions & messages
# ---------------------------------------------------------------------------

class ChatRole(str, Enum):
    USER = "user"
    MASTER = "master"
    SYSTEM = "system"
    AGENT = "agent"
    TOOL = "tool"
    ERROR = "error"


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: new_id("msg"))
    session_id: str = ""
    role: ChatRole
    content: str
    agent: Optional[str] = None                  # e.g. "planner"
    created_at: datetime = Field(default_factory=utcnow)
    meta: dict[str, Any] = Field(default_factory=dict)


class SessionSummary(BaseModel):
    session_id: str
    title: str = "New session"
    summary: str = ""
    facts: list[str] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    message_count: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    last_plan_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Agent events (streamed to the UI over WebSocket)
# ---------------------------------------------------------------------------

class AgentEvent(BaseModel):
    """Every lifecycle moment the UI must reflect (tasking Phase 22)."""
    event: str                                   # planning_started, agent_started, ...
    session_id: str = ""
    plan_id: Optional[str] = None
    step_id: Optional[str] = None
    agent: Optional[str] = None
    model: Optional[str] = None
    status: Optional[str] = None                 # TaskState-style status string
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# API request/response bodies
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: Optional[str] = None
    execute: bool = True                         # plan+execute; False => plan only


class ChatResponse(BaseModel):
    session_id: str
    message: ChatMessage
    plan: Optional[Plan] = None
    plan_state: Optional[TaskState] = None


class PermissionDecisionRequest(BaseModel):
    request_id: str
    approved: bool


class SettingsUpdateRequest(BaseModel):
    active_provider: Optional[str] = None
    openrouter_key_1: Optional[str] = None
    openrouter_key_2: Optional[str] = None
    agent_models: Optional[dict[str, str]] = None
    permission_mode: Optional[str] = None
    theme: Optional[str] = None
    screen_enabled: Optional[bool] = None
    screen_capture_interval: Optional[float] = None
    screen_max_elements: Optional[int] = None
    stt_engine: Optional[str] = None
    whisper_model: Optional[str] = None
    step_timeout: Optional[float] = None
    max_steps_per_plan: Optional[int] = None
    max_retries_per_step: Optional[int] = None
    max_recovery_cycles: Optional[int] = None


class TranscribeResponse(BaseModel):
    ok: bool
    text: str = ""
    engine: str = ""
    error: Optional[str] = None
