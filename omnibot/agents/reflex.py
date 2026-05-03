from __future__ import annotations

from omnibot.core.agent_runtime import AgentContext, BaseAgent, referenced_paths
from omnibot.schemas.events import AgentResult


class ReflexAgent(BaseAgent):
    name = "reflex"
    role = "classification"

    async def _run(self, ctx: AgentContext) -> AgentResult:
        paths = referenced_paths(ctx.request)
        memories = await ctx.memory.recall(ctx.request, limit=3)
        needs_code = any(path.endswith(".py") for path in paths) or any(
            word in ctx.request.lower() for word in ("test", "bug", "failing", "traceback")
        )
        summary = (
            f"Intent: {'debug/code assistance' if needs_code else 'general assistance'}. "
            f"Referenced paths: {', '.join(paths) if paths else 'none'}. "
            f"Relevant memories: {len(memories)}."
        )
        return AgentResult(
            agent_name=self.name,
            role=self.role,
            summary=summary,
            confidence=0.78,
            sources=[m.memory_id for m in memories],
            evidence=[m.content for m in memories[:2]],
        )
