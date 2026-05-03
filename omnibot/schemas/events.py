from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


EventType = Literal[
    "user.requested",
    "task.created",
    "task.status",
    "agent.started",
    "agent.completed",
    "tool.called",
    "tool.completed",
    "arbiter.decided",
    "memory.written",
    "presence.responded",
    "error",
]


class TaskStatus(str, Enum):
    QUEUED = "queued"
    THINKING = "thinking"
    WORKING = "working"
    DONE = "done"
    FAILED = "failed"


class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    type: EventType
    timestamp: str = Field(default_factory=now_iso)
    actor: str = "system"
    source: str = "omnibot"
    causal_parent_ids: list[str] = Field(default_factory=list)
    task_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    audit_hash: str | None = None


class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: new_id("task"))
    user_request: str
    status: TaskStatus = TaskStatus.QUEUED
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class AgentResult(BaseModel):
    agent_name: str
    role: str
    summary: str
    confidence: float = 0.5
    sources: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    tool_calls: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    error: str | None = None


class ArbiterDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: new_id("arb"))
    task_id: str
    selected_agents: list[str]
    rejected_alternatives: list[dict[str, Any]] = Field(default_factory=list)
    rationale: str
    confidence: float
    final_answer: str
    source_event_ids: list[str] = Field(default_factory=list)


class MemoryItem(BaseModel):
    memory_id: str = Field(default_factory=lambda: new_id("mem"))
    kind: Literal["episodic", "semantic", "working"] = "episodic"
    content: str
    source_event_id: str
    task_id: str | None = None
    embedding: list[float] = Field(default_factory=list)
    confidence: float = 0.7
    created_at: str = Field(default_factory=now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    tool_call_id: str = Field(default_factory=lambda: new_id("tool"))
    task_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: Literal["started", "completed", "blocked", "failed"] = "started"
    result: str = ""
    source_event_ids: list[str] = Field(default_factory=list)
