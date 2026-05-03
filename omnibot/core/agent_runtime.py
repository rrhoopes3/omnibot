from __future__ import annotations

import re
from abc import ABC, abstractmethod

from omnibot.core.event_bus import EventBus
from omnibot.core.memory_fabric import MemoryFabric
from omnibot.core.tool_bus import ToolBus
from omnibot.models.registry import ModelRegistry
from omnibot.schemas.events import AgentResult


class AgentContext:
    def __init__(
        self,
        *,
        task_id: str,
        request: str,
        parent_event_id: str,
        event_bus: EventBus,
        memory: MemoryFabric,
        tools: ToolBus,
        models: ModelRegistry,
    ):
        self.task_id = task_id
        self.request = request
        self.parent_event_id = parent_event_id
        self.event_bus = event_bus
        self.memory = memory
        self.tools = tools
        self.models = models


class BaseAgent(ABC):
    name = "base"
    role = "base"

    async def run(self, ctx: AgentContext) -> AgentResult:
        started = await ctx.event_bus.emit(
            "agent.started",
            actor=self.name,
            source="agent_runtime",
            task_id=ctx.task_id,
            causal_parent_ids=[ctx.parent_event_id],
            payload={"agent": self.name, "role": self.role},
        )
        try:
            result = await self._run(ctx)
        except Exception as exc:
            result = AgentResult(
                agent_name=self.name,
                role=self.role,
                summary=f"{self.name} failed: {type(exc).__name__}: {exc}",
                confidence=0.0,
                error=str(exc),
            )
        completed = await ctx.event_bus.emit(
            "agent.completed",
            actor=self.name,
            source="agent_runtime",
            task_id=ctx.task_id,
            causal_parent_ids=[started.event_id],
            payload=result.model_dump(),
        )
        result.event_ids.extend([started.event_id, completed.event_id])
        return result

    @abstractmethod
    async def _run(self, ctx: AgentContext) -> AgentResult:
        raise NotImplementedError


def referenced_paths(text: str) -> list[str]:
    candidates = re.findall(r"[\w./\\:-]+\.(?:py|txt|md|json|toml|yaml|yml)", text)
    return list(dict.fromkeys(candidates))
