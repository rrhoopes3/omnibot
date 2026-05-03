from __future__ import annotations

from omnibot.core.agent_runtime import AgentContext, BaseAgent
from omnibot.schemas.events import AgentResult


class ResearcherAgent(BaseAgent):
    name = "researcher"
    role = "context_research"

    async def _run(self, ctx: AgentContext) -> AgentResult:
        memories = await ctx.memory.recall(ctx.request, limit=5)
        search = await ctx.tools.execute(
            "web_search",
            {"query": ctx.request[:240]},
            task_id=ctx.task_id,
            causal_parent_ids=[ctx.parent_event_id],
            actor=self.name,
        )
        evidence = [m.content for m in memories[:3]]
        evidence.append(search.get("summary", "No external search summary."))
        return AgentResult(
            agent_name=self.name,
            role=self.role,
            summary=(
                "Checked relevant memory and queried the configured search provider chain "
                f"({search.get('provider', 'no provider returned results')})."
            ),
            confidence=0.58 if memories else 0.42,
            sources=[m.memory_id for m in memories] + ["tool:web_search"],
            evidence=evidence,
            tool_calls=["web_search"],
        )
