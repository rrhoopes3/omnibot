from __future__ import annotations

import asyncio
from pathlib import Path
import re

from omnibot.agents.coder import CoderAgent
from omnibot.agents.reflex import ReflexAgent
from omnibot.agents.researcher import ResearcherAgent
from omnibot.core.agent_runtime import AgentContext, BaseAgent
from omnibot.core.event_bus import EventBus
from omnibot.core.memory_fabric import MemoryFabric
from omnibot.core.presence_layer import PresenceLayer
from omnibot.core.tool_bus import ToolBus
from omnibot.models.registry import ModelRegistry
from omnibot.schemas.events import AgentResult, ArbiterDecision, Task


class CoordinationKernel:
    """Intent router, parallel runner, arbiter, and memory writer."""

    def __init__(self, *, db_path: str | Path = "omnibot.db", workspace: str | Path = "."):
        self.event_bus = EventBus(db_path)
        self.memory = MemoryFabric(db_path)
        self.models = ModelRegistry()
        self.tools = ToolBus(self.event_bus, workspace)
        self.presence = PresenceLayer()
        self.agents: list[BaseAgent] = [ReflexAgent(), ResearcherAgent(), CoderAgent()]

    async def init(self) -> None:
        await self.event_bus.init()
        await self.memory.init()

    async def handle_request(self, user_request: str) -> dict:
        user_event = await self.event_bus.emit(
            "user.requested",
            actor="user",
            source="chat",
            payload={"request": user_request},
        )
        task = Task(user_request=user_request)
        task_event = await self.event_bus.emit(
            "task.created",
            actor="coordination_kernel",
            source="coordination_kernel",
            task_id=task.task_id,
            causal_parent_ids=[user_event.event_id],
            payload=task.model_dump(),
        )
        await self._status(task.task_id, "thinking", [task_event.event_id])

        ctx = AgentContext(
            task_id=task.task_id,
            request=user_request,
            parent_event_id=task_event.event_id,
            event_bus=self.event_bus,
            memory=self.memory,
            tools=self.tools,
            models=self.models,
        )

        await self._status(task.task_id, "working", [task_event.event_id])
        results = await asyncio.gather(*(agent.run(ctx) for agent in self.agents))
        decision = await self._arbitrate(task.task_id, user_request, results)

        arbiter_event = await self.event_bus.emit(
            "arbiter.decided",
            actor="arbiter",
            source="coordination_kernel",
            task_id=task.task_id,
            causal_parent_ids=decision.source_event_ids,
            payload=decision.model_dump(),
        )
        memory = await self.memory.remember(
            f"Request: {user_request}\nDecision: {decision.final_answer}\nRationale: {decision.rationale}",
            source_event_id=arbiter_event.event_id,
            task_id=task.task_id,
            kind="episodic",
            confidence=decision.confidence,
            metadata={"selected_agents": decision.selected_agents},
        )
        memory_event = await self.event_bus.emit(
            "memory.written",
            actor="memory_fabric",
            source="memory_fabric",
            task_id=task.task_id,
            causal_parent_ids=[arbiter_event.event_id],
            payload=memory.model_dump(),
        )
        await self._status(task.task_id, "done", [memory_event.event_id])

        response = self.presence.compose(user_request, decision, results)
        response_event = await self.event_bus.emit(
            "presence.responded",
            actor="presence_layer",
            source="presence_layer",
            task_id=task.task_id,
            causal_parent_ids=[arbiter_event.event_id],
            payload={"response": response},
        )
        return {
            "task_id": task.task_id,
            "response": response,
            "decision": decision.model_dump(),
            "agents": [r.model_dump() for r in results],
            "events": [e.model_dump() for e in await self.event_bus.replay(task_id=task.task_id)],
            "response_event_id": response_event.event_id,
        }

    async def _status(self, task_id: str, status: str, parents: list[str]) -> None:
        await self.event_bus.emit(
            "task.status",
            actor="coordination_kernel",
            source="coordination_kernel",
            task_id=task_id,
            causal_parent_ids=parents,
            payload={"status": status},
        )

    async def _arbitrate(
        self,
        task_id: str,
        user_request: str,
        results: list[AgentResult],
    ) -> ArbiterDecision:
        ranked = sorted(results, key=lambda r: (r.confidence, len(r.evidence)), reverse=True)
        selected = ranked[:2]
        rejected = [
            {"agent": r.agent_name, "confidence": r.confidence, "reason": "Lower confidence or less direct evidence."}
            for r in ranked[2:]
        ]
        final_answer = self._synthesize(user_request, selected, results)
        rationale = (
            f"Selected {', '.join(r.agent_name for r in selected)} because they provided the strongest "
            "combination of direct evidence, tool use, and task classification. "
            f"Rejected {', '.join(r.agent_name for r in ranked[2:]) or 'none'} as secondary context."
        )
        confidence = round(sum(r.confidence for r in selected) / max(1, len(selected)), 2)
        return ArbiterDecision(
            task_id=task_id,
            selected_agents=[r.agent_name for r in selected],
            rejected_alternatives=rejected,
            rationale=rationale,
            confidence=confidence,
            final_answer=final_answer,
            source_event_ids=[event_id for r in results for event_id in r.event_ids],
        )

    def _synthesize(self, user_request: str, selected: list[AgentResult], all_results: list[AgentResult]) -> str:
        coder = next((r for r in all_results if r.agent_name == "coder"), None)
        reflex = next((r for r in all_results if r.agent_name == "reflex"), None)
        debug_request = bool(re.search(r"\b(test|pytest|failing|fail|bug|traceback|fix)\b", user_request, re.I))

        lines = [f"I treated this as: {reflex.summary if reflex else user_request}", ""]
        if coder and coder.evidence:
            lines.append("What I found:")
            for item in coder.evidence[:3]:
                snippet = item.strip()
                if len(snippet) > 1200:
                    snippet = snippet[:1200] + "... [truncated]"
                lines.append(f"- {snippet}")
            lines.append("")
            if debug_request:
                lines.append("Proposed next move:")
                lines.append(
                    "Use the test output and referenced file content above as the fix target. "
                    "v0.1 stops at diagnosis/proposal; enabling automatic edits should be a Tier 3 permission."
                )
            else:
                lines.append("Architecture direction:")
                lines.append(
                    "The referenced material is pointing toward an event-driven coordination substrate: "
                    "parallel specialist agents, explicit arbitration, memory with provenance, scoped tools, "
                    "and a presence layer that turns the work into one legible response."
                )
        else:
            lines.append("The agents did not find direct code evidence, so I would ask for the failing file or stack trace next.")

        lines.append("")
        lines.append("Sources used:")
        for result in selected:
            if result.sources:
                lines.append(f"- {result.agent_name}: {', '.join(result.sources[:4])}")
        return "\n".join(lines)
